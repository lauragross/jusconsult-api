import os
import sqlite3
from flask import Request

# Caminho do banco (permite override por variável de ambiente)
DB_PATH = os.getenv("DATAJUD_DB_PATH", "datajud_processos.db")


def get_conn() -> sqlite3.Connection:
    """
    Abre conexão SQLite com row_factory em dict-like.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Banco não encontrado em {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows):
    """
    Converte lista de sqlite3.Row em lista de dict.
    """
    return [dict(r) for r in rows]


def get_pagination_params(request: Request):
    """
    Extrai limit/offset da query string com sanidade.
    """
    try:
        limit = int(request.args.get("limit", 10000))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        limit, offset = 100, 0
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    return limit, offset
