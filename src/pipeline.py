"""
OfertaHub — Pipeline Completo
Orquestra: Gerente IA (coleta + filtragem) → Disparador (Telegram).
É este script que o systemd executa a cada ciclo.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Garante que os módulos do projeto sejam encontrados independente do cwd
sys.path.insert(0, str(Path(__file__).parent))

import db
from gerente_ia import processar_ofertas, exportar_json
from mock_api import buscar_produtos          # trocar por amazon_api quando PA-API for aprovada
from disparador_telegram import disparar_ofertas

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PIPELINE] %(message)s",
)
logger = logging.getLogger("pipeline")

_JSON_PATH = Path(__file__).parent / "ofertas_aprovadas.json"


def etapa_coleta_e_filtragem() -> int:
    """Roda o Gerente IA e persiste o JSON. Retorna qtd de ofertas aprovadas."""
    logger.info("▶ Etapa 1/2 — Coleta e filtragem (Gerente IA)")
    db.inicializar_banco()   # idempotente; sem isso, banco novo quebra em registrar_preco
    produtos_brutos = buscar_produtos(limite=20)
    logger.info("  Produtos recebidos da API: %d", len(produtos_brutos))

    ofertas = processar_ofertas(produtos_brutos)
    _JSON_PATH.write_text(exportar_json(ofertas), encoding="utf-8")

    logger.info("  Ofertas aprovadas: %d / %d", len(ofertas), len(produtos_brutos))
    return len(ofertas)


async def etapa_disparo() -> None:
    """Dispara as ofertas salvas no JSON para o canal do Telegram."""
    logger.info("▶ Etapa 2/2 — Disparo no Telegram")
    await disparar_ofertas()


async def main() -> None:
    logger.info("=" * 55)
    logger.info("OfertaHub Pipeline — início do ciclo")
    logger.info("=" * 55)

    aprovadas = etapa_coleta_e_filtragem()

    if aprovadas == 0:
        logger.info("Nenhuma oferta aprovada. Disparo cancelado.")
        return

    await etapa_disparo()
    logger.info("Ciclo finalizado com sucesso.")


if __name__ == "__main__":
    asyncio.run(main())
