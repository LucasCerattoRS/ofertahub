# RETOMADA — OfertaHub (08/10/2026)

Retomada feita só lendo o código e rodando testes offline. **Produção não foi tocada**:
nenhum bot rodou com token real, nenhum segredo foi lido ou alterado.

## Estado em uma frase

Bot Telegram de ofertas da Amazon BR, em produção numa máquina Fedora via systemd,
**rodando 100% com dados mock** (`src/mock_api.py`) porque a Amazon PA-API nunca foi liberada.
O coletor real (`src/coletor_ativo.py`, RSS + scraping) está congelado: os feeds RSS dão 404 e a
Amazon devolve CAPTCHA.

## Como roda

| Peça | Arquivo | Como é disparada |
|------|---------|------------------|
| Bot interativo (`/start`, `/filtros`, `/minhas_categorias`, `/cancelar`) | `src/bot_interativo.py` | `ofertahub-bot.service`, `Type=simple`, long-polling contínuo, `Restart=on-failure` |
| Pipeline (busca → Score → JSON → DMs) | `src/pipeline.py` → `gerente_ia.processar_ofertas` → `disparador_telegram.disparar_ofertas` | `ofertahub.timer` a cada **30 min** (`OnBootSec=2min`, `Persistent=true`) → `ofertahub.service` `Type=oneshot` |
| Banco | `src/ofertahub.db` (SQLite WAL; `users`, `historico_precos`, `ofertas_enviadas`) | criado por `db.inicializar_banco()` |
| Config/segredos | `src/config.py` (gitignored; modelo em `src/config.example.py`) | `TELEGRAM_TOKEN`, `AMAZON_API` |
| Manutenção | `deploy/revisao.sh` (reload + restart + status; `--clean` apaga `ofertas_enviadas`) | manual |

Fluxo de um ciclo: `mock_api.buscar_produtos(20)` (sorteia os 13 produtos fixos) → para cada
produto, grava o preço em `historico_precos` → pré-filtros (blacklist, desconto ≥ 20 %,
nota ≥ 4.0, ≥ 50 avaliações) → `Score = 40·P + 40·A + 4·log10(V) − penalidades` → ordena →
`ofertas_aprovadas.json` → para cada oferta, DM com foto (fallback texto) e botão de compra a
quem assinou a categoria, sem repetir o mesmo ASIN ao mesmo usuário no mesmo dia (UTC).

## Onde está hospedado (inferido)

- **Máquina local Fedora 43** do Lukas, systemd **user units** com `loginctl enable-linger`.
  Caminho nos units: `/home/lukascerattiagnese/Documentos/ProjeoEmprendimento/` (venv em `.venv/`).
- **Sem deploy automático**: não há `.github/workflows`, webhooks nem deployments no GitHub
  (conferido via API em 08/10). Um push na `main` só chega à produção se alguém fizer
  `git pull` na pasta acima e reiniciar os serviços (`deploy/revisao.sh`).
- O repositório GitHub é **público**. Nenhum token/credencial foi encontrado no histórico
  (varredura de todo `git log -p` por token Telegram, chave AWS e atribuições a
  `access_key`/`secret_key`/`TELEGRAM_TOKEN`).

## Testes

- Novo: `tests/test_pipeline_offline.py` (unittest, offline, banco temporário, usa
  `config.example.py` se não houver `config.py`). Rodar: `python -m unittest tests/test_pipeline_offline.py`.
- `tests/test_paralelo.py` e `tests/raio_x_feed.py` **não são testes unitários**: batem em
  httpbin.org e nos feeds reais; servem de diagnóstico manual.
- Rodado nesta retomada com Python 3.12 + `requirements.txt` (o README pede 3.14+, mas o código
  funciona em 3.12).

## Consertado nesta branch

1. **Pipeline quebrava em banco novo** — `pipeline.py` (o que o systemd roda) nunca chamava
   `db.inicializar_banco()`; só `gerente_ia.main()` e o bot chamavam. Numa instalação nova ou
   depois de apagar o `.db`, se o timer rodasse antes do bot, o ciclo morria com
   `sqlite3.OperationalError: no such table: historico_precos`. Agora a etapa 1 inicializa o
   banco (idempotente). Coberto por `tests/test_pipeline_offline.py`.
2. **README dizia timer de 60 min**; o `ofertahub.timer` é de 30 min. Corrigido.

## Riscos e bugs encontrados (não consertados)

1. **Usuários reais recebem ofertas fictícias.** Os preços do mock são inventados e fixos, mas
   saem como "🚨 OFERTA DETECTADA" com link de afiliado (`tag=ofertahub0f0-20`). Além de enganar o
   usuário, mostrar preço que não veio da PA-API vai contra as regras do Programa de Associados.
   É o maior risco do projeto hoje. Opções: pausar o timer (`systemctl --user stop ofertahub.timer`)
   ou marcar as mensagens como demonstração até a PA-API sair.
2. **Mesmas ofertas todo dia.** O mock é fixo e a deduplicação é diária: cada assinante recebe as
   mesmas ~9 ofertas por dia, todo dia (spam → bloqueios).
3. **`pipeline.py` ignora a PA-API mesmo com credenciais**: importa `mock_api` fixo. A troca
   automática por `amazon_api` só existe em `gerente_ia.main()`, que o systemd não roda.
   E `amazon_api.py` não existe.
4. **Penalidades de histórico ficam inertes com mock**: o preço nunca varia, então a
   "volatilidade" nunca dispara; "histórico insuficiente" só vale nos 2 primeiros ciclos.
   `historico_precos` cresce ~13 linhas a cada 30 min, sem limpeza (pequeno, mas sem fim).
5. **Busca de assinantes por `LIKE '%"Categoria"%'`** sobre JSON em texto: funciona com as
   categorias atuais, mas `_`/`%` num nome de categoria virariam curinga.
6. **Callback `filtro:<cat>` não é validado** contra `CATEGORIAS_DISPONIVEIS`, e o clique não
   cadastra o usuário se ele não existir na tabela (toggle vira no-op silencioso). Impacto baixo.
7. Coluna `users.preco_maximo` existe mas nada a usa.
8. **Ruído no repositório**: a mesma skill `ui-ux-pro-max` copiada em ~14 pastas de agentes
   (`.agent`, `.claude`, `.codex`, `.cursor`, `.github/prompts`…): ~390 dos ~420 arquivos.
   `design-system/` (TSX) não é usado pelo código Python.
9. `STATUS.md` cita o repo como `Hub-de-Ofertas`; hoje é `LucasCerattoRS/ofertahub`.

## Próximos passos sugeridos

1. Decidir sobre o risco 1: pausar o timer ou rotular as mensagens até haver dado real.
2. Se a PA-API for liberada: criar `src/amazon_api.py` com `buscar_produtos(categoria, limite)` e
   fazer `pipeline.py` escolher a fonte como `gerente_ia.main()` já faz.
3. Na máquina Fedora, para trazer esta correção: `git pull` em
   `~/Documentos/ProjeoEmprendimento` e `deploy/revisao.sh` (sem `--clean`).
4. Opcional: apagar as cópias duplicadas da skill e o `design-system/` se o frontend (Fase 7)
   não for retomado.
