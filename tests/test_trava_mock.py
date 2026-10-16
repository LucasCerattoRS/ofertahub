"""
Prova offline de que oferta mock/fictícia NUNCA é publicada.
Sem rede, sem token; Telegram e banco são substituídos.

  python -m unittest tests/test_trava_mock.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

if not (_SRC / "config.py").exists():
    spec = importlib.util.spec_from_file_location("config", _SRC / "config.example.py")
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    sys.modules["config"] = config

import db  # noqa: E402
import disparador_telegram  # noqa: E402
import mock_api  # noqa: E402
import pipeline  # noqa: E402
import trava_fonte  # noqa: E402

CFG_VAZIA = {"access_key": "", "secret_key": "", "partner_tag": ""}
CFG_OK = {"access_key": "a", "secret_key": "b", "partner_tag": "t-20"}


class TravaMock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = (db.DB_PATH, pipeline._JSON_PATH, disparador_telegram._JSON_PATH)
        db.DB_PATH = Path(self.tmp.name) / "o.db"
        pipeline._JSON_PATH = Path(self.tmp.name) / "o.json"
        disparador_telegram._JSON_PATH = pipeline._JSON_PATH

    def tearDown(self):
        db.DB_PATH, pipeline._JSON_PATH, disparador_telegram._JSON_PATH = self._orig
        self.tmp.cleanup()

    def test_pipeline_com_mock_nao_publica(self):
        # Fonte mock injetada: tem que falhar alto e não gerar JSON.
        with self.assertRaises(trava_fonte.PublicacaoBloqueada):
            pipeline.etapa_coleta_e_filtragem(mock_api.buscar_produtos)
        self.assertFalse(pipeline._JSON_PATH.exists())

    def test_pipeline_sem_pa_api_nao_cai_para_mock(self):
        cfg = types.SimpleNamespace(AMAZON_API=CFG_VAZIA)
        with mock.patch.dict(sys.modules, {"config": cfg}), \
                self.assertLogs("trava_fonte", "CRITICAL") as cap:
            with self.assertRaises(trava_fonte.PublicacaoBloqueada):
                pipeline.etapa_coleta_e_filtragem()
        self.assertIn("PA-API não configurada", cap.output[0])

    def test_pa_api_configurada_mas_sem_modulo_bloqueia(self):
        cfg = types.SimpleNamespace(AMAZON_API=CFG_OK)
        with mock.patch.dict(sys.modules, {"config": cfg, "amazon_api": None}):
            with self.assertRaises(trava_fonte.PublicacaoBloqueada):
                pipeline.obter_fonte()

    def test_disparo_recusa_json_com_asin_mock(self):
        # JSON velho de ciclo anterior com dados fictícios.
        asin = sorted(mock_api.ASINS_MOCK)[0]
        pipeline._JSON_PATH.write_text(json.dumps([{
            "ASIN": asin, "Produto": "x", "Categoria": "Eletrônicos",
            "Link de Afiliado": f"https://www.amazon.com.br/dp/{asin}?tag=t-20",
        }]), encoding="utf-8")
        bot = mock.MagicMock()
        with mock.patch.object(disparador_telegram, "Bot", return_value=bot), \
                mock.patch.object(db, "get_usuarios_por_categoria", return_value=[1]):
            with self.assertRaises(trava_fonte.PublicacaoBloqueada):
                asyncio.run(disparador_telegram.disparar_ofertas())
        bot.send_photo.assert_not_called()
        bot.send_message.assert_not_called()

    def test_main_do_pipeline_nao_dispara_com_mock(self):
        with mock.patch.object(pipeline, "obter_fonte",
                               return_value=mock_api.buscar_produtos), \
                mock.patch.object(pipeline, "disparar_ofertas") as disp:
            with self.assertRaises(trava_fonte.PublicacaoBloqueada):
                asyncio.run(pipeline.main())
        disp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
