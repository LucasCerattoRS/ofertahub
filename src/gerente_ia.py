"""
OfertaHub — Fase 1: O Cérebro (v2)
Gerente IA: motor de triagem com Score analítico e blacklist.

Fórmula: Score = (Wp * P) + (Wa * A) + (Wv * log10(V)) - C_penalidade
  P  = min(desconto_pct / 80, 1.0)   — desconto normalizado
  A  = nota / 5.0                     — avaliação normalizada
  V  = total_avaliacoes               — volume bruto
  C  = soma de penalidades dinâmicas  — volatilidade, histórico insuficiente
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import db
import trava_fonte
from config import AFFILIATE_TAG, BLACKLIST, FILTRO, PENALIDADES, SCORE_PESOS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("gerente_ia")


# ── Modelo de saída padronizado ────────────────────────────────────────────

@dataclass
class Oferta:
    asin: str
    produto: str
    preco_real: float
    preco_original: float
    desconto_pct: float
    nota_avaliacao: float
    total_avaliacoes: int
    categoria: str
    score_oferta: float
    link_afiliado: str
    imagem_url: str = ""

    def to_dict(self) -> dict:
        return {
            "ASIN":              self.asin,
            "Produto":           self.produto,
            "Preço Real":        f"R$ {self.preco_real:.2f}",
            "Preço Original":    f"R$ {self.preco_original:.2f}",
            "Desconto":          f"{self.desconto_pct:.1f}%",
            "Nota de Avaliação": self.nota_avaliacao,
            "Total de Avaliações": self.total_avaliacoes,
            "Categoria":         self.categoria,
            "Score Oferta":      round(self.score_oferta, 2),
            "Link de Afiliado":  self.link_afiliado,
            "Imagem URL":        self.imagem_url,
        }


# ── Utilitários ────────────────────────────────────────────────────────────

def _calcular_desconto(preco_atual: float, preco_original: float) -> float:
    if preco_original <= 0:
        return 0.0
    return ((preco_original - preco_atual) / preco_original) * 100


def _construir_link_afiliado(asin: str, tag: str) -> str:
    return f"https://www.amazon.com.br/dp/{asin}?tag={tag}"


def _calcular_score(desconto_pct: float, nota: float, total_aval: int, asin: str) -> float:
    """
    Score = (Wp * P) + (Wa * A) + (Wv * log10(V)) - C_penalidade

    Penalidades dinâmicas (consultam o histórico de preços no SQLite):
      - volatilidade_alta    : amplitude > 30% no histórico recente
      - historico_insuficiente: menos de 3 registros disponíveis
    """
    Wp, Wa, Wv = SCORE_PESOS["Wp"], SCORE_PESOS["Wa"], SCORE_PESOS["Wv"]

    P = min(desconto_pct / 80.0, 1.0)
    A = nota / 5.0
    V = math.log10(max(total_aval, 1))

    score_bruto = (Wp * P) + (Wa * A) + (Wv * V)

    # ── Penalidades baseadas no histórico de preços ────────────────────────
    penalidade = 0.0
    historico = db.get_historico_precos(asin, limite=10)

    if len(historico) < 3:
        penalidade += PENALIDADES["historico_insuficiente"]
    else:
        preco_max_hist = max(historico)
        preco_min_hist = min(historico)
        if preco_min_hist > 0:
            amplitude = (preco_max_hist - preco_min_hist) / preco_min_hist
            if amplitude > 0.30:
                penalidade += PENALIDADES["volatilidade_alta"]

    return max(0.0, round(score_bruto - penalidade, 2))


# ── Triagem (filtros de pré-aprovação) ────────────────────────────────────

def _produto_aprovado(produto: dict) -> tuple[bool, str]:
    """Retorna (aprovado, motivo_rejeicao). Curto-circuito na primeira falha."""
    titulo     = produto.get("titulo", "")
    categoria  = produto.get("categoria", "")
    preco_atual    = produto.get("preco_atual", 0)
    preco_original = produto.get("preco_original", 0)
    nota           = produto.get("nota", 0)
    total_aval     = produto.get("total_avaliacoes", 0)

    # Blacklist de marcas (busca por substring no título)
    titulo_lower = titulo.lower()
    for marca in BLACKLIST["marcas_bloqueadas"]:
        if marca.lower() in titulo_lower:
            return False, f"marca bloqueada ('{marca}')"

    # Blacklist de categorias
    if categoria in BLACKLIST["categorias_bloqueadas"]:
        return False, f"categoria bloqueada ('{categoria}')"

    desconto = _calcular_desconto(preco_atual, preco_original)

    if desconto < FILTRO["desconto_minimo_pct"]:
        return False, f"desconto insuficiente ({desconto:.1f}% < {FILTRO['desconto_minimo_pct']}%)"

    if nota < FILTRO["nota_minima"]:
        return False, f"nota abaixo do mínimo ({nota} < {FILTRO['nota_minima']})"

    if total_aval < FILTRO["avaliacoes_minimas"]:
        return False, f"avaliações insuficientes ({total_aval} < {FILTRO['avaliacoes_minimas']})"

    preco_max = FILTRO.get("preco_maximo")
    if preco_max is not None and preco_atual > preco_max:
        return False, f"preço acima do limite (R$ {preco_atual:.2f} > R$ {preco_max:.2f})"

    return True, ""


# ── Interface pública ──────────────────────────────────────────────────────

def processar_ofertas(produtos_brutos: list[dict]) -> list[Oferta]:
    """
    Ingere produtos brutos, registra preço no histórico, aplica triagem
    e retorna Ofertas aprovadas ordenadas por Score (maior primeiro).
    """
    aprovadas: list[Oferta] = []

    for p in produtos_brutos:
        titulo = p.get("titulo", "Desconhecido")
        asin   = p.get("asin", "")

        # Registra preço atual no histórico antes de qualquer filtro
        if asin:
            db.registrar_preco(asin, p.get("preco_atual", 0))

        aprovado, motivo = _produto_aprovado(p)
        if not aprovado:
            logger.info("REJEITADO  | %-55s | %s", titulo[:55], motivo)
            continue

        desconto = _calcular_desconto(p["preco_atual"], p["preco_original"])
        score    = _calcular_score(desconto, p["nota"], p["total_avaliacoes"], asin)
        link     = _construir_link_afiliado(asin, AFFILIATE_TAG)

        oferta = Oferta(
            asin             = asin,
            produto          = titulo,
            preco_real       = p["preco_atual"],
            preco_original   = p["preco_original"],
            desconto_pct     = desconto,
            nota_avaliacao   = p["nota"],
            total_avaliacoes = p["total_avaliacoes"],
            categoria        = p.get("categoria", "Geral"),
            score_oferta     = score,
            link_afiliado    = link,
            imagem_url       = p.get("imagem_url", ""),
        )
        aprovadas.append(oferta)
        logger.info("APROVADO   | %-55s | score=%.1f  desconto=%.1f%%", titulo[:55], score, desconto)

    aprovadas.sort(key=lambda o: o.score_oferta, reverse=True)
    return aprovadas


def exportar_json(ofertas: list[Oferta], indent: int = 2) -> str:
    return json.dumps([o.to_dict() for o in ofertas], ensure_ascii=False, indent=indent)


# ── Entrypoint ─────────────────────────────────────────────────────────────

def main() -> None:
    db.inicializar_banco()

    from pipeline import obter_fonte   # falha alto se PA-API ausente; nunca usa mock
    buscar_produtos = obter_fonte()

    produtos_brutos = buscar_produtos(limite=20)
    trava_fonte.exigir_produtos_reais(produtos_brutos)
    logger.info("Produtos recebidos: %d", len(produtos_brutos))

    ofertas = processar_ofertas(produtos_brutos)

    logger.info("─" * 60)
    logger.info("Ofertas aprovadas: %d / %d", len(ofertas), len(produtos_brutos))
    logger.info("─" * 60)

    resultado_json = exportar_json(ofertas)
    saida_path = Path(__file__).parent / "ofertas_aprovadas.json"
    saida_path.write_text(resultado_json, encoding="utf-8")
    logger.info("Resultado salvo em: %s", saida_path)


if __name__ == "__main__":
    main()
