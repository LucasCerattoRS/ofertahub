"""
Histórico de preços e penalidades do Score — sem rede, banco temporário.

Execução:
  python -m unittest tests/test_historico.py
"""

from __future__ import annotations

import importlib.util
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
import gerente_ia  # noqa: E402
from config import PENALIDADES, SCORE_PESOS  # noqa: E402


class HistoricoPorDia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._db_path = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "ofertahub.db"
        db.inicializar_banco()

    def tearDown(self):
        db.DB_PATH = self._db_path
        self.tmp.cleanup()

    def _grava(self, asin: str, preco: float, quando: str) -> None:
        with db._db() as conn:
            conn.execute(
                "INSERT INTO historico_precos (asin, preco, coletado_em) VALUES (?, ?, ?)",
                (asin, preco, quando),
            )

    def test_varias_coletas_no_mesmo_dia_contam_como_um_dia(self):
        # 10 rodadas do timer (a cada 30 min) na mesma tarde = 1 dia de histórico.
        for i in range(10):
            self._grava("B0X", 100.0 + i, f"2026-10-08 {12 + i // 2:02d}:{30 * (i % 2):02d}:00")
        self.assertEqual(db.get_historico_precos("B0X"), [109.0])

    def test_um_preco_por_dia_o_ultimo_do_dia_do_mais_recente_para_tras(self):
        self._grava("B0X", 90.0, "2026-10-06 09:00:00")
        self._grava("B0X", 95.0, "2026-10-06 21:00:00")
        self._grava("B0X", 80.0, "2026-10-07 10:00:00")
        self._grava("B0X", 85.0, "2026-10-08 08:00:00")
        self.assertEqual(db.get_historico_precos("B0X"), [85.0, 80.0, 95.0])
        self.assertEqual(db.get_historico_precos("B0X", limite=2), [85.0, 80.0])

    def test_penalidade_de_historico_insuficiente_dura_ate_o_terceiro_dia(self):
        base = (SCORE_PESOS["Wp"] * 0.5) + (SCORE_PESOS["Wa"] * 0.9) + (SCORE_PESOS["Wv"] * 2)
        for h in range(6):  # 6 coletas no mesmo dia: antes da correção isso já zerava a penalidade
            self._grava("B0Y", 100.0, f"2026-10-08 {8 + h:02d}:00:00")
        score = gerente_ia._calcular_score(40.0, 4.5, 100, "B0Y")
        self.assertEqual(score, round(base - PENALIDADES["historico_insuficiente"], 2))
        self._grava("B0Y", 100.0, "2026-10-07 12:00:00")
        self._grava("B0Y", 100.0, "2026-10-06 12:00:00")
        self.assertEqual(gerente_ia._calcular_score(40.0, 4.5, 100, "B0Y"), round(base, 2))

    def test_volatilidade_compara_dias_diferentes(self):
        self._grava("B0Z", 100.0, "2026-10-06 12:00:00")
        self._grava("B0Z", 140.0, "2026-10-07 12:00:00")  # +40% entre dias
        self._grava("B0Z", 120.0, "2026-10-08 12:00:00")
        base = (SCORE_PESOS["Wp"] * 0.5) + (SCORE_PESOS["Wa"] * 0.9) + (SCORE_PESOS["Wv"] * 2)
        self.assertEqual(gerente_ia._calcular_score(40.0, 4.5, 100, "B0Z"),
                         round(base - PENALIDADES["volatilidade_alta"], 2))


if __name__ == "__main__":
    unittest.main()
