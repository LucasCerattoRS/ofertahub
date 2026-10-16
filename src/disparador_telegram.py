"""
OfertaHub — Disparador Segmentado (Telegram)
Lê ofertas_aprovadas.json, consulta o SQLite para identificar quais usuários
assinaram cada categoria e envia DMs individuais com botão inline de compra.

Isolamento de falhas: um usuário bloqueado não para o loop — é marcado inativo.
Deduplicação: o mesmo produto não é reenviado ao mesmo usuário no mesmo dia.
"""

import asyncio
import json
import logging
import re
from pathlib import Path

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError

import db
import trava_fonte
from config import TELEGRAM_TOKEN

# Regex compilada dos 19 caracteres reservados pelo MarkdownV2.
# Usada APENAS no corpo de texto — URLs do InlineKeyboardButton nunca passam aqui.
_MDV2_RE = re.compile(r'([_*\[\]()~`>#+=|{}.!\-\\])')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DISPARADOR] %(message)s",
)
logger = logging.getLogger("disparador")

_JSON_PATH = Path(__file__).parent / "ofertas_aprovadas.json"


# ── Formatação ─────────────────────────────────────────────────────────────

def _esc(texto: str) -> str:
    """Escapa texto para MarkdownV2. NUNCA chamar com URLs — corromperia o link."""
    return _MDV2_RE.sub(r'\\\1', str(texto))


def _teclado_compra(link: str) -> InlineKeyboardMarkup:
    # URL passa diretamente para o parâmetro `url` — sem qualquer escape.
    # O Telegram trata esse campo como string pura, não como MarkdownV2.
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(text="🛒  Comprar na Amazon", url=link)
    ]])


def formatar_mensagem(oferta: dict) -> str:
    score = oferta.get("Score Oferta", 0)
    fogo  = "🔥" * max(1, int(score // 20))
    return (
        f"🚨 *OFERTA DETECTADA* 🚨\n\n"
        f"📦 *{_esc(oferta['Produto'])}*\n\n"
        f"💳 De: ~{_esc(oferta['Preço Original'])}~\n"
        f"💰 *Por: {_esc(oferta['Preço Real'])}*  \\({_esc(oferta['Desconto'])} OFF\\)\n\n"
        f"⭐ Nota: *{_esc(oferta['Nota de Avaliação'])}* / 5\\.0\n"
        f"🗣️ Avaliações: {_esc(oferta['Total de Avaliações'])}\n"
        f"🏆 Score IA: {_esc(score)} {fogo}"
    )


# ── Envio com fallback sendPhoto → sendMessage ────────────────────────────

async def _enviar_com_fallback(
    bot: Bot,
    user_id: int,
    texto: str,
    teclado: InlineKeyboardMarkup,
    imagem_url: str,
) -> bool:
    """
    Tenta sendPhoto (imagem + caption). Se a URL for inválida/inacessível
    — BadRequest típico: "wrong type of the web page content" ou
    "failed to get HTTP URL content" — cai para sendMessage puro.
    Forbidden e outros TelegramError propagam para o handler externo.

    Retorna True se qualquer via conseguiu entregar a mensagem.
    """
    if imagem_url:
        try:
            await bot.send_photo(
                chat_id=user_id,
                photo=imagem_url,
                caption=texto,                    # caption aceita MarkdownV2 (até 1024 chars)
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=teclado,
            )
            return True
        except BadRequest as exc:
            # URL quebrada, formato não suportado, etc. — fallback textual.
            logger.warning("sendPhoto falhou (%s) — tentando sendMessage.", exc)

    try:
        await bot.send_message(
            chat_id=user_id,
            text=texto,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=teclado,
            disable_web_page_preview=False,
        )
        return True
    except BadRequest as exc:
        # Erro de formatação do próprio texto — não reenviar.
        logger.error("BadRequest para user %d: %s", user_id, exc)
        return False


# ── Loop de disparo segmentado ─────────────────────────────────────────────

async def disparar_ofertas() -> None:
    bot = Bot(token=TELEGRAM_TOKEN)

    try:
        ofertas: list[dict] = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("ofertas_aprovadas.json não encontrado — execute o pipeline primeiro.")
        return

    if not ofertas:
        logger.info("Nenhuma oferta no JSON para disparar.")
        return

    trava_fonte.exigir_ofertas_reais(ofertas)   # nunca publicar ofertas fictícias

    total_enviados = 0

    for oferta in ofertas:
        categoria = oferta.get("Categoria", "")
        asin      = oferta.get("ASIN", "")
        usuarios  = db.get_usuarios_por_categoria(categoria)

        if not usuarios:
            logger.info("Sem assinantes para '%s' — pulando.", categoria)
            continue

        texto     = formatar_mensagem(oferta)
        teclado   = _teclado_compra(oferta["Link de Afiliado"])
        imagem    = oferta.get("Imagem URL") or ""

        for user_id in usuarios:
            if asin and db.ja_enviado_hoje(user_id, asin):
                logger.debug("Já enviado hoje para %d: %s", user_id, asin)
                continue

            try:
                enviado = await _enviar_com_fallback(bot, user_id, texto, teclado, imagem)
                if enviado:
                    if asin:
                        db.registrar_envio(user_id, asin)
                    total_enviados += 1
                    logger.info("Enviado → %d | %s", user_id, oferta["Produto"][:45])
                await asyncio.sleep(0.05)   # respeita rate limit do Telegram (30 msg/s para DMs)

            except Forbidden:
                # Usuário bloqueou o bot — marcamos inativo para não tentar novamente
                logger.warning("User %d bloqueou o bot — marcando inativo.", user_id)
                db.marcar_inativo(user_id)

            except TelegramError as exc:
                # Erro de rede, flood control, etc. — tenta no próximo ciclo
                logger.error("TelegramError para user %d: %s", user_id, exc)

    logger.info("Disparo concluído: %d mensagem(ns) enviada(s).", total_enviados)


if __name__ == "__main__":
    db.inicializar_banco()
    asyncio.run(disparar_ofertas())
