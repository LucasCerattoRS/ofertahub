"""
Mock da Amazon Product Advertising API.
ASINs estáveis da Amazon BR — priorizamos produtos Amazon-branded
(Echo, Kindle, Fire TV) que têm ciclo de vida longo e raramente são
desativados, reduzindo o risco de links mortos em produção.

Cobre todos os caminhos da lógica de filtragem: aprovados e rejeitados
por cada critério (desconto, nota, volume de avaliações, blacklist).
"""

import random

# Padrão legado do CDN da Amazon que aceita ASIN diretamente, sem hash de
# imagem. Funciona para a maioria dos produtos; se falhar, o disparador
# cai automaticamente para envio sem imagem (sendMessage). Troque por URLs
# reais extraídas da PA-API assim que as credenciais forem configuradas.
_IMG_CDN = "https://images-na.ssl-images-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg"


def _img(asin: str) -> str:
    return _IMG_CDN.format(asin=asin)


_PRODUTOS_MOCK = [
    # ── APROVADOS ──────────────────────────────────────────────────────────
    {
        "asin": "B09B8VC33K",   # Echo Dot 5ª Geração
        "titulo": "Echo Dot (5ª Geração) Smart Speaker com Alexa",
        "preco_atual": 199.00,
        "preco_original": 379.00,
        "nota": 4.7,
        "total_avaliacoes": 18420,
        "categoria": "Eletrônicos",
        "imagem_url": _img("B09B8VC33K"),
    },
    {
        "asin": "B0BJ3BNVDM",   # Fire TV Stick 4K Max 2ª Geração
        "titulo": "Fire TV Stick 4K Max com Alexa Voice Remote",
        "preco_atual": 269.00,
        "preco_original": 449.00,
        "nota": 4.6,
        "total_avaliacoes": 9870,
        "categoria": "Eletrônicos",
        "imagem_url": _img("B0BJ3BNVDM"),
    },
    {
        "asin": "B0BSXW3FGF",   # Kindle 11ª Geração
        "titulo": "Kindle (11ª Geração) 16 GB — o Kindle mais leve",
        "preco_atual": 299.00,
        "preco_original": 499.00,
        "nota": 4.7,
        "total_avaliacoes": 14650,
        "categoria": "E-readers",
        "imagem_url": _img("B0BSXW3FGF"),
    },
    {
        "asin": "B09TMF6745",   # Kindle Paperwhite 11ª Geração
        "titulo": "Kindle Paperwhite (11ª Geração) 8 GB — À prova d'água",
        "preco_atual": 379.00,
        "preco_original": 649.00,
        "nota": 4.8,
        "total_avaliacoes": 22310,
        "categoria": "E-readers",
        "imagem_url": _img("B09TMF6745"),
    },
    {
        "asin": "B09XS7JWHH",   # Sony WH-1000XM5
        "titulo": "Sony WH-1000XM5 Fone de Ouvido Bluetooth Noise Canceling",
        "preco_atual": 1299.00,
        "preco_original": 2199.00,
        "nota": 4.8,
        "total_avaliacoes": 7340,
        "categoria": "Áudio",
        "imagem_url": _img("B09XS7JWHH"),
    },
    {
        "asin": "B09KRDPQTZ",   # JBL Flip 6
        "titulo": "JBL Flip 6 Caixa de Som Bluetooth À Prova d'Água",
        "preco_atual": 499.00,
        "preco_original": 849.00,
        "nota": 4.6,
        "total_avaliacoes": 11230,
        "categoria": "Áudio",
        "imagem_url": _img("B09KRDPQTZ"),
    },
    {
        "asin": "B0874YJP92",   # Samsung T7 SSD Portátil 1TB
        "titulo": "SSD Externo Portátil Samsung T7 1TB USB 3.2",
        "preco_atual": 399.00,
        "preco_original": 699.00,
        "nota": 4.7,
        "total_avaliacoes": 16900,
        "categoria": "Periféricos",
        "imagem_url": _img("B0874YJP92"),
    },
    {
        "asin": "B07VGBBQ2Q",   # TP-Link Tapo C200
        "titulo": "Câmera de Segurança Wi-Fi TP-Link Tapo C200 Full HD 360°",
        "preco_atual": 159.00,
        "preco_original": 279.00,
        "nota": 4.4,
        "total_avaliacoes": 8650,
        "categoria": "Segurança",
        "imagem_url": _img("B07VGBBQ2Q"),
    },
    {
        "asin": "B08384MFKP",   # iRobot Roomba 692
        "titulo": "Robô Aspirador iRobot Roomba 692 Wi-Fi com Alexa",
        "preco_atual": 1399.00,
        "preco_original": 2499.00,
        "nota": 4.3,
        "total_avaliacoes": 3210,
        "categoria": "Eletrodomésticos",
        "imagem_url": _img("B08384MFKP"),
    },

    # ── REJEITADOS (cobrem todos os critérios de triagem) ──────────────────
    {
        "asin": "B0C3QBX3PT",
        "titulo": "Cabo USB-C sem Marca 1m Carga Rápida",   # blacklist: "sem marca"
        "preco_atual": 24.90,
        "preco_original": 39.90,
        "nota": 4.2,
        "total_avaliacoes": 310,
        "categoria": "Acessórios",
        "imagem_url": _img("B0C3QBX3PT"),
    },
    {
        "asin": "B0CJLVJQS3",
        "titulo": "Tablet Samsung Galaxy Tab A9+ 11'' 128GB",
        "preco_atual": 1599.00,
        "preco_original": 1749.00,  # desconto 8.6% — abaixo de 20%
        "nota": 4.5,
        "total_avaliacoes": 2140,
        "categoria": "Eletrônicos",
        "imagem_url": _img("B0CJLVJQS3"),
    },
    {
        "asin": "B0B9X9QGKZ",
        "titulo": "Fone de Ouvido In-Ear Importado S/ Garantia BR",
        "preco_atual": 79.90,
        "preco_original": 159.00,
        "nota": 3.1,               # nota abaixo de 4.0
        "total_avaliacoes": 890,
        "categoria": "Áudio",
        "imagem_url": _img("B0B9X9QGKZ"),
    },
    {
        "asin": "B0CKWQHX3R",
        "titulo": "Suporte Articulado para Monitor Dual",
        "preco_atual": 89.90,
        "preco_original": 159.00,
        "nota": 4.3,
        "total_avaliacoes": 28,    # abaixo do mínimo de 50
        "categoria": "Periféricos",
        "imagem_url": _img("B0CKWQHX3R"),
    },
]


FONTE_MOCK = "mock"
ASINS_MOCK = frozenset(p["asin"] for p in _PRODUTOS_MOCK)


def buscar_produtos(categoria: str = "geral", limite: int = 20) -> list[dict]:
    """Simula resposta paginada da API retornando produtos brutos."""
    amostra = random.sample(_PRODUTOS_MOCK, min(limite, len(_PRODUTOS_MOCK)))
    return [{**p, "fonte": FONTE_MOCK} for p in amostra]
