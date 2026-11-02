from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "knowledge.db"


def get_db_path() -> Path:
    return Path(os.environ.get("KNOWLEDGE_DB", DEFAULT_DB_PATH)).expanduser().resolve()


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    content,
    content = 'documents',
    content_rowid = 'id',
    tokenize = 'unicode61'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO documents_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;
"""


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    owns_connection = conn is None
    if conn is None:
        conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    except Exception:
        if owns_connection:
            conn.close()
        raise
    return conn


def _sanitize_query(query: str) -> str:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    return " OR ".join(f'"{token}"' for token in tokens)


def search(
    query: str,
    limit: int = 5,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return []

    limit = max(1, min(int(limit), 50))
    owns_connection = conn is None
    if conn is None:
        conn = init_db()

    sql = """
        SELECT
            d.id,
            d.title,
            d.path,
            snippet(documents_fts, 1, '« ', ' »', '…', 24) AS snippet,
            bm25(documents_fts) AS rank
        FROM documents_fts
        JOIN documents d ON d.id = documents_fts.rowid
        WHERE documents_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """

    try:
        rows = conn.execute(sql, (query, limit)).fetchall()
    except sqlite3.OperationalError:
        fallback = _sanitize_query(query)
        if not fallback:
            rows = []
        else:
            rows = conn.execute(sql, (fallback, limit)).fetchall()
    finally:
        if owns_connection:
            conn.close()

    return [dict(row) for row in rows]


def count_documents(conn: sqlite3.Connection | None = None) -> int:
    owns_connection = conn is None
    if conn is None:
        conn = init_db()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
    finally:
        if owns_connection:
            conn.close()


def clear_documents(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM documents")
    conn.commit()


def insert_documents(
    documents: list[tuple[str, str, str]],
    conn: sqlite3.Connection,
    batch_size: int = 500,
) -> int:
    inserted = 0
    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]
        conn.executemany(
            "INSERT INTO documents (title, path, content) VALUES (?, ?, ?)",
            batch,
        )
        conn.commit()
        inserted += len(batch)
    return inserted
