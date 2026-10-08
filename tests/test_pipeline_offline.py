"""
Testes offline do pipeline — sem rede, sem token, sem tocar o banco de produção.

Usa um banco SQLite temporário e, se não existir src/config.py (gitignored),
carrega src/config.example.py no lugar.

Execução:
  python -m unittest tests/test_pipeline_offline.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

if not (_SRC / "config.py").exists():
    spec = importlib.util.spec_from_file_location("config", _SRC / "config.example.py")
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    sys.modules["config"] = config

import db  # noqa: E402
import pipeline  # noqa: E402


class PipelineOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._db_path, self._json_path = db.DB_PATH, pipeline._JSON_PATH
        db.DB_PATH = Path(self.tmp.name) / "ofertahub.db"
        pipeline._JSON_PATH = Path(self.tmp.name) / "ofertas_aprovadas.json"

    def tearDown(self):
        db.DB_PATH, pipeline._JSON_PATH = self._db_path, self._json_path
        self.tmp.cleanup()

    def test_coleta_em_banco_novo_nao_quebra(self):
        # Regressão: pipeline.py rodava antes de qualquer inicializar_banco()
        # e caía com "no such table: historico_precos" numa instalação nova.
        aprovadas = pipeline.etapa_coleta_e_filtragem()

        # mock_api tem 9 produtos aprovados e 4 rejeitados (um por critério).
        self.assertEqual(aprovadas, 9)
        ofertas = json.loads(pipeline._JSON_PATH.read_text(encoding="utf-8"))
        scores = [o["Score Oferta"] for o in ofertas]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all("tag=" in o["Link de Afiliado"] for o in ofertas))


if __name__ == "__main__":
    unittest.main()
