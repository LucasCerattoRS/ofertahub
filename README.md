# OfertaHub

> Sistema autônomo de curadoria de ofertas da Amazon Brasil, com filtragem algorítmica por IA e entrega personalizada via Telegram.

O **OfertaHub** é um motor de recomendação que aplica uma fórmula de *Score* analítica (desconto, qualidade, volume e penalidades) para separar ofertas genuinamente vantajosas do ruído promocional. Usuários assinam categorias de interesse em um bot interativo, e a cada ciclo programado recebem por mensagem direta apenas os produtos aprovados — com botão de compra nativo do Telegram.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Telegram API                               │
└──────────────┬──────────────────────────────────────┬───────────────┘
               │                                      │
       polling │                                      │ DMs com botão inline
               ▼                                      ▲
┌──────────────────────────────┐        ┌─────────────────────────────┐
│  bot_interativo.py           │        │  disparador_telegram.py     │
│  (processo contínuo)         │        │  (chamado pelo pipeline)    │
│  /start /filtros /cancelar   │        │  Segmentação por categoria  │
└──────────────┬───────────────┘        └──────────────┬──────────────┘
               │                                       │
               │                                       │
               ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SQLite (WAL mode) — ofertahub.db               │
│   users  •  historico_precos  •  ofertas_enviadas                   │
└─────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │
                                   │
                ┌──────────────────┴──────────────────┐
                │  pipeline.py                        │
                │  (systemd timer — a cada 30 min)    │
                │  1. mock_api / Amazon PA-API        │
                │  2. gerente_ia → Score + filtros    │
                │  3. ofertas_aprovadas.json          │
                │  4. disparador → DMs segmentadas    │
                └─────────────────────────────────────┘
```

### Componentes

| Arquivo | Responsabilidade |
|---|---|
| [`src/gerente_ia.py`](src/gerente_ia.py) | Motor de triagem. Fórmula: `Score = (Wp·P) + (Wa·A) + (Wv·log₁₀V) − C_penalidade` |
| [`src/db.py`](src/db.py) | Camada SQLite com WAL mode (concorrência segura entre bot e pipeline) |
| [`src/bot_interativo.py`](src/bot_interativo.py) | Bot Telegram long-polling — gerencia assinaturas via inline keyboard |
| [`src/disparador_telegram.py`](src/disparador_telegram.py) | Envio segmentado por categoria com deduplicação diária |
| [`src/pipeline.py`](src/pipeline.py) | Orquestrador — entrypoint do systemd timer |
| [`src/mock_api.py`](src/mock_api.py) | Mock da Amazon PA-API para testes offline |
| [`src/config.example.py`](src/config.example.py) | Template de configuração (credenciais fora do Git) |

### Stack

- **Python 3.14+**
- **SQLite 3** (modo WAL — leituras concorrentes sem bloqueio)
- **python-telegram-bot 22+** (async/await, Application builder)
- **systemd user units** (Type=simple para o bot, Type=oneshot + timer para o pipeline)

---

## Setup Local

### 1. Clonar e preparar o ambiente

```bash
git clone https://github.com/<seu-usuário>/ofertahub.git
cd ofertahub

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar credenciais

```bash
cd src
cp config.example.py config.py
```

Edite `config.py` e preencha:

- `TELEGRAM_TOKEN` — obtenha em [@BotFather](https://t.me/BotFather)
- `AMAZON_API` — cadastre-se no [Programa de Associados Amazon BR](https://affiliate-program.amazon.com.br/)

> Enquanto as credenciais da Amazon estiverem vazias, o sistema cai automaticamente para `mock_api.py` — ideal para desenvolvimento.

### 3. Inicializar o banco

```bash
python -c "import db; db.inicializar_banco()"
```

### 4. Validar manualmente

```bash
# Roda o ciclo completo uma vez: busca → filtra → envia
python pipeline.py

# Inicia o bot interativo (Ctrl+C para parar)
python bot_interativo.py
```

Abra o Telegram, envie `/start` para o bot e em seguida `/filtros` para escolher suas categorias.

---

## Deploy no Fedora via systemd

A automação usa **systemd user units** — sem precisar de root.

### 1. Instalar os units

Copie os dois arquivos do repositório para o diretório de units do usuário:

```bash
mkdir -p ~/.config/systemd/user

cp deploy/ofertahub.service     ~/.config/systemd/user/
cp deploy/ofertahub.timer       ~/.config/systemd/user/
cp deploy/ofertahub-bot.service ~/.config/systemd/user/
```

> **Ajuste os caminhos absolutos** em cada `.service` (`WorkingDirectory` e `ExecStart`) para apontar para a sua instalação.

### 2. Ativar os serviços

```bash
# Recarrega os units
systemctl --user daemon-reload

# Bot interativo (polling contínuo)
systemctl --user enable --now ofertahub-bot.service

# Pipeline periódico (a cada 30 min)
systemctl --user enable --now ofertahub.timer

# Permite que os serviços rodem mesmo com a sessão encerrada
loginctl enable-linger "$USER"
```

### 3. Monitorar

```bash
# Status
systemctl --user status ofertahub-bot.service
systemctl --user list-timers ofertahub.timer

# Logs ao vivo
journalctl --user -u ofertahub-bot -f
journalctl --user -u ofertahub     -f

# Disparo manual (sem esperar o timer)
systemctl --user start ofertahub.service
```

---

## Fórmula de Score — como é calibrada

```
Score = (Wp × P) + (Wa × A) + (Wv × log₁₀(V)) − C_penalidade

  Wp = 40    P = min(desconto_pct / 80, 1.0)
  Wa = 40    A = nota / 5.0
  Wv =  4    V = total_avaliacoes   (log₁₀ → até 5 p/ 100k avaliações)
  C  = 8  se amplitude do histórico de preços > 30%  (volatilidade_alta)
     + 3  se menos de 3 registros no histórico       (historico_insuficiente)
```

Teto teórico de 100 pontos. Produtos abaixo dos pré-filtros de `FILTRO` (desconto < 20%, nota < 4.0, avaliações < 50) são descartados antes do cálculo. Todos os pesos e limiares são ajustáveis em [`config.py`](src/config.example.py).

---

## Estrutura de Diretórios

```
ProjeoEmprendimento/
├── src/
│   ├── bot_interativo.py
│   ├── config.example.py       # versionado
│   ├── config.py               # IGNORADO — tokens locais
│   ├── db.py
│   ├── disparador_telegram.py
│   ├── gerente_ia.py
│   ├── mock_api.py
│   ├── pipeline.py
│   ├── ofertahub.db            # IGNORADO — banco local
│   └── ofertas_aprovadas.json  # IGNORADO — output de runtime
├── deploy/
│   ├── ofertahub.service
│   ├── ofertahub.timer
│   └── ofertahub-bot.service
├── .gitignore
├── README.md
└── requirements.txt
```

---

## Segurança

- `config.py` e `ofertahub.db` são bloqueados pelo `.gitignore` — **jamais faça commit desses arquivos**.
- O token do Telegram nunca é logado; apenas IDs numéricos de usuário aparecem nos logs.
- Usuários que bloquearem o bot são automaticamente marcados como inativos no SQLite (`Forbidden` handler).
- O modo WAL do SQLite garante que o bot e o pipeline possam ler/escrever simultaneamente sem corromper o banco.

---

## Licença

MIT — veja [LICENSE](LICENSE).
