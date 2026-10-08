"""
OfertaHub — Camada de Dados (SQLite)
Inicializa o banco e expõe funções CRUD usadas pelo bot interativo e pelo disparador.

WAL mode: permite leitura concorrente entre o bot (processo contínuo)
e o pipeline (processo periódico) sem bloqueio mútuo.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "ofertahub.db"


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Inicialização ──────────────────────────────────────────────────────────

def inicializar_banco() -> None:
    """Cria todas as tabelas se não existirem. Idempotente."""
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id_telegram          INTEGER PRIMARY KEY,
                nome                 TEXT    NOT NULL,
                categorias_inscritas TEXT    NOT NULL DEFAULT '[]',
                preco_maximo         REAL    DEFAULT NULL,
                ativo                INTEGER NOT NULL DEFAULT 1,
                criado_em            TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS historico_precos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                asin        TEXT    NOT NULL,
                preco       REAL    NOT NULL,
                coletado_em TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_historico_asin
                ON historico_precos(asin, coletado_em DESC);

            CREATE TABLE IF NOT EXISTS ofertas_enviadas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                id_telegram INTEGER NOT NULL,
                asin        TEXT    NOT NULL,
                enviado_em  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_envio_unico
                ON ofertas_enviadas(id_telegram, asin, date(enviado_em));
        """)


# ── Usuários ───────────────────────────────────────────────────────────────

def upsert_user(id_telegram: int, nome: str) -> None:
    """Registra novo usuário ou reativa um existente (ex: voltou a usar o bot)."""
    with _db() as conn:
        conn.execute("""
            INSERT INTO users (id_telegram, nome)
            VALUES (?, ?)
            ON CONFLICT(id_telegram) DO UPDATE
                SET nome = excluded.nome, ativo = 1
        """, (id_telegram, nome))


def get_categorias_user(id_telegram: int) -> list[str]:
    with _db() as conn:
        row = conn.execute(
            "SELECT categorias_inscritas FROM users WHERE id_telegram = ?",
            (id_telegram,),
        ).fetchone()
    return json.loads(row["categorias_inscritas"]) if row else []


def toggle_categoria(id_telegram: int, categoria: str) -> list[str]:
    """Adiciona ou remove uma categoria. Retorna a lista atualizada."""
    categorias = get_categorias_user(id_telegram)
    if categoria in categorias:
        categorias.remove(categoria)
    else:
        categorias.append(categoria)
    with _db() as conn:
        conn.execute(
            "UPDATE users SET categorias_inscritas = ? WHERE id_telegram = ?",
            (json.dumps(categorias, ensure_ascii=False), id_telegram),
        )
    return categorias


def limpar_categorias(id_telegram: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE users SET categorias_inscritas = '[]' WHERE id_telegram = ?",
            (id_telegram,),
        )


def marcar_inativo(id_telegram: int) -> None:
    """Chamado quando o usuário bloqueia o bot — evita tentativas futuras."""
    with _db() as conn:
        conn.execute(
            "UPDATE users SET ativo = 0 WHERE id_telegram = ?",
            (id_telegram,),
        )


def get_usuarios_por_categoria(categoria: str) -> list[int]:
    """Retorna IDs de usuários ativos que assinaram a categoria informada."""
    with _db() as conn:
        rows = conn.execute(
            'SELECT id_telegram FROM users WHERE ativo = 1 AND categorias_inscritas LIKE ?',
            (f'%"{categoria}"%',),
        ).fetchall()
    return [r["id_telegram"] for r in rows]


# ── Histórico de Preços ────────────────────────────────────────────────────

def registrar_preco(asin: str, preco: float) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO historico_precos (asin, preco) VALUES (?, ?)",
            (asin, preco),
        )


def get_historico_precos(asin: str, limite: int = 10) -> list[float]:
    """Um preço por DIA (o último coletado no dia), do dia mais recente para trás.

    O timer roda a cada 30 min e cada rodada grava uma linha. Lendo linhas cruas, "os 10
    últimos" eram só as últimas 5 horas: a penalidade de histórico insuficiente sumia depois
    de 1h30 e a de volatilidade comparava preços da mesma tarde. Agrupando por dia, 10 = 10 dias.
    (No SQLite, a coluna `preco` ao lado de MAX() vem da mesma linha do máximo.)
    """
    with _db() as conn:
        rows = conn.execute(
            "SELECT date(coletado_em) AS dia, preco, MAX(coletado_em) "
            "FROM historico_precos WHERE asin = ? "
            "GROUP BY dia ORDER BY dia DESC LIMIT ?",
            (asin, limite),
        ).fetchall()
    return [r["preco"] for r in rows]


# ── Deduplicação de Envios ─────────────────────────────────────────────────

def ja_enviado_hoje(id_telegram: int, asin: str) -> bool:
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM ofertas_enviadas "
            "WHERE id_telegram = ? AND asin = ? AND date(enviado_em) = date('now')",
            (id_telegram, asin),
        ).fetchone()
    return row is not None


def registrar_envio(id_telegram: int, asin: str) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO ofertas_enviadas (id_telegram, asin) VALUES (?, ?)",
            (id_telegram, asin),
        )
