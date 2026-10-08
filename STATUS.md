# 💾 Save Point — OfertaHub

**Status:** Em produção (100% autônomo, mock data), publicado sob MIT em [github.com/LucasCerattoRS/Hub-de-Ofertas](https://github.com/LucasCerattoRS/Hub-de-Ofertas).

Pausado aguardando liberação das credenciais da Amazon Product Advertising API para sair do mock.

---

## ✅ Fases concluídas

### Fase 1 — Cérebro
- [`gerente_ia.py`](src/gerente_ia.py): fórmula `Score = (Wp·P) + (Wa·A) + (Wv·log₁₀V) − C_penalidade` (pesos 40/40/4).
- Penalidades dinâmicas: volatilidade >30% no histórico (−8), histórico <3 registros (−3).
  O histórico é contado em **dias** (último preço de cada dia): com o timer a cada 30 min, contar linhas
  cruas fazia "10 registros" valerem 5 horas (corrigido em 08/10/2026, `tests/test_historico.py`).
- Pré-filtros: desconto ≥20%, nota ≥4.0, ≥50 avaliações, blacklist de marcas.
- [`mock_api.py`](src/mock_api.py) com 14 produtos reais da Amazon BR cobrindo todos os caminhos de triagem.

### Fase 2 — Disparo
- [`disparador_telegram.py`](src/disparador_telegram.py): DMs segmentadas por categoria, `MarkdownV2` com regex de escape seguro (URL nunca passa pelo escape), botão inline `🛒 Comprar na Amazon`.
- Hierarquia de exceções correta: `Forbidden` → marca inativo; `BadRequest` / `TelegramError` → apenas logam.

### Fase 3 — Assinatura
- [`db.py`](src/db.py): SQLite WAL com 3 tabelas (`users`, `historico_precos`, `ofertas_enviadas`) + `UNIQUE INDEX` para deduplicação diária.
- [`bot_interativo.py`](src/bot_interativo.py): `/start`, `/filtros` (teclado inline 2 colunas ✅/⬜), `/minhas_categorias`, `/cancelar`.

### Fase 4 — Automação systemd (Fedora 43)
- [`deploy/ofertahub-bot.service`](deploy/ofertahub-bot.service): `Type=simple` + `Restart=on-failure` (polling contínuo).
- [`deploy/ofertahub.service`](deploy/ofertahub.service): `Type=oneshot` (pipeline).
- [`deploy/ofertahub.timer`](deploy/ofertahub.timer): **a cada 30 min**, `Persistent=true`, `OnBootSec=2min`.
- `loginctl enable-linger` mantém tudo vivo após logout.

### Fase 5 — Release
- `.gitignore`, [`config.example.py`](src/config.example.py), [`requirements.txt`](requirements.txt), [`README.md`](README.md) com diagrama ASCII.
- Licença MIT (Copyright © 2026 Lukas Tcheratto D'agnese).
- StoreID real `ofertahub0f0-20` propagado em [`config.example.py`](src/config.example.py).

---

## 🛑 Onde paramos

Tudo funcional em modo mock. `config.py` local tem `partner_tag = "ofertahub0f0-20"` e `access_key`/`secret_key` em branco — o sistema cai automaticamente para `mock_api.py`.

## 🚀 Próximos passos

1. **Fase 6 — PA-API real:** criar `amazon_api.py` expondo `buscar_produtos(categoria, limite)` e preencher `access_key`/`secret_key` em `config.py`. `gerente_ia.main()` já detecta credenciais e troca o import automaticamente.
2. **Fase 7 — Frontend:** PWA Next.js consumindo `ofertahub.db` (ou o JSON) para indexação SEO.
3. **Fase 8 — Automação e Multi-canal:** Utilizar o hub n8n (servidor MCP já configurado e ativo) para criar fluxos de distribuição visual para WhatsApp, Discord e Google Sheets, reduzindo a necessidade de scripts de disparo manuais.

---

## 🌳 Árvore (pós-refactor)

```
ProjeoEmprendimento/
├── src/                       # núcleo Python (antigo BackEnd/AI/)
│   ├── bot_interativo.py
│   ├── config.example.py
│   ├── config.py              # IGNORADO
│   ├── db.py
│   ├── disparador_telegram.py
│   ├── gerente_ia.py
│   ├── mock_api.py
│   ├── pipeline.py
│   └── ofertahub.db           # IGNORADO (runtime)
├── deploy/
│   ├── ofertahub.service
│   ├── ofertahub.timer
│   └── ofertahub-bot.service
├── design-system/             # Design System (MASTER.md + componentes)
│   ├── MASTER.md
│   └── components/
│       ├── ProductCard.tsx
│       └── TestGallery.tsx
├── .venv/                     # IGNORADO
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── STATUS.md
```

---

## 💻 Cheat Sheet (Fedora)

```bash
# Próximo disparo do pipeline (deve mostrar ~30min)
systemctl --user list-timers ofertahub.timer

# Status do bot
systemctl --user status ofertahub-bot.service

# Forçar ciclo manual
systemctl --user start ofertahub.service

# Logs ao vivo
journalctl --user -u ofertahub-bot -f
journalctl --user -u ofertahub -n 50 --no-pager

# Pausar / retomar automação
systemctl --user stop ofertahub.timer
systemctl --user start ofertahub.timer

# Confirmar StoreID nos links gerados
grep -o 'tag=[^"]*' src/ofertas_aprovadas.json | sort -u
# → tag=ofertahub0f0-20
```
