"""
Trava de fonte de dados — impede publicar ofertas fictícias.

Ofertas do mock_api têm preço inventado mas saem com link de afiliado real:
enganam quem compra e violam o contrato do Amazon Associates. Este módulo
faz o pipeline FALHAR ALTO (exceção + log CRITICAL) em vez de publicar
quando a fonte é mock/fictícia ou quando a PA-API não está configurada.
"""

from __future__ import annotations

import logging

import mock_api

logger = logging.getLogger("trava_fonte")

_CAMPOS_PA_API = ("access_key", "secret_key", "partner_tag")


class PublicacaoBloqueada(RuntimeError):
    """Levantada quando a publicação seria feita com dados não reais."""


def _bloquear(motivo: str) -> None:
    logger.critical("🛑 PUBLICAÇÃO BLOQUEADA: %s", motivo)
    raise PublicacaoBloqueada(motivo)


def exigir_pa_api_configurada(amazon_api_cfg: dict | None) -> None:
    """Falha se faltar qualquer credencial da PA-API."""
    cfg = amazon_api_cfg or {}
    faltando = [k for k in _CAMPOS_PA_API if not str(cfg.get(k) or "").strip()]
    if faltando:
        _bloquear("PA-API não configurada (faltando: %s). Sem PA-API não há "
                  "fonte real de preços; nada será publicado." % ", ".join(faltando))


def _e_mock(item: dict) -> bool:
    return item.get("fonte") == mock_api.FONTE_MOCK


def exigir_produtos_reais(produtos: list[dict]) -> None:
    """Falha se algum produto bruto vier do mock/fictício."""
    mocks = [p.get("asin", "?") for p in produtos if _e_mock(p)]
    if mocks:
        _bloquear("fonte mock/fictícia detectada nos produtos coletados: %s"
                  % ", ".join(mocks[:5]))


def exigir_ofertas_reais(ofertas: list[dict]) -> None:
    """
    Falha se o JSON de ofertas contiver ASIN do mock (ex.: arquivo velho,
    gerado por um ciclo anterior com dados fictícios).
    """
    mocks = sorted({o.get("ASIN", "") for o in ofertas} & mock_api.ASINS_MOCK)
    if mocks:
        _bloquear("ofertas com ASIN de produto fictício (mock) no JSON: %s"
                  % ", ".join(mocks[:5]))
