"""
Raio-X dos feeds RSS dos agregadores BR — diagnóstico estrutural.

Objetivo: descobrir onde os feeds estão (ou não) a pôr os links para
produtos Amazon hoje, revelando:
  1. Se o corpo devolvido é XML válido  → feed.bozo
  2. Quantas entradas o parser conseguiu extrair  → len(feed.entries)
  3. Que chaves cada entrada tem  → sorted(entry.keys())
  4. Dump JSON da primeira entrada para inspeção visual das URLs

Execução:
  python tests/raio_x_feed.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import feedparser
import requests

# Reusa os constants reais do coletor para o raio-x refletir fielmente
# o comportamento de produção (mesmo User-Agent, mesmo timeout, mesma lista).
_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAIZ / "src"))

from coletor_ativo import (  # noqa: E402
    _FEEDS_DESCOBERTA,
    _HEADERS_BASE,
    _TIMEOUT_HTTP,
    _USER_AGENTS,
)

# Truncagem de strings longas (HTML de summary pode ter 10KB+).
_MAX_STR = 1500


def _plain(obj):
    """Converte recursivamente FeedParserDict/listas/tuplos em JSON-nativo."""
    if hasattr(obj, "keys"):
        return {k: _plain(obj[k]) for k in obj.keys()}
    if isinstance(obj, (list, tuple)):
        return [_plain(x) for x in obj]
    if isinstance(obj, str) and len(obj) > _MAX_STR:
        return obj[:_MAX_STR] + f"... [+{len(obj) - _MAX_STR} chars truncados]"
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return str(obj)


def raio_x(feed_url: str) -> None:
    print(f"\n{'═' * 72}")
    print(f"ALVO: {feed_url}")
    print("═" * 72)

    try:
        resp = requests.get(
            feed_url,
            headers={**_HEADERS_BASE, "User-Agent": _USER_AGENTS[0]},
            timeout=_TIMEOUT_HTTP,
        )
    except requests.RequestException as exc:
        print(f"✗ Falha HTTP: {exc}")
        return

    print(f"HTTP status      : {resp.status_code}")
    print(f"Content-Type     : {resp.headers.get('Content-Type', '?')}")
    print(f"Tamanho (bytes)  : {len(resp.content)}")

    feed = feedparser.parse(resp.content)
    print(f"feed.bozo        : {feed.bozo}")
    if feed.bozo and getattr(feed, "bozo_exception", None):
        exc = feed.bozo_exception
        print(f"  └─ exception   : {type(exc).__name__}: {exc}")
    print(f"feed.version     : {feed.version or '(vazio)'}")
    print(f"len(feed.entries): {len(feed.entries)}")

    if not feed.entries:
        print("\n(Sem entradas — a mostrar os primeiros 600 bytes do corpo cru:)")
        print("-" * 72)
        print(resp.content[:600].decode("utf-8", errors="replace"))
        print("-" * 72)
        return

    primeira = feed.entries[0]
    print("\n── Chaves da primeira entrada ──────────────────────────────────────")
    print(sorted(primeira.keys()))

    print("\n── Dump JSON da primeira entrada ───────────────────────────────────")
    print(json.dumps(_plain(primeira), indent=2, ensure_ascii=False))


def main() -> int:
    for feed_url in _FEEDS_DESCOBERTA:
        raio_x(feed_url)
    print("\n" + "═" * 72)
    print("FIM DO RAIO-X. Procurar padrões:")
    print("  • chaves tipo 'link', 'links', 'enclosures', 'media_content'")
    print("  • URLs com /dp/, /gp/product/, amazon.com.br ou shorteners (pelan.do)")
    print("═" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
