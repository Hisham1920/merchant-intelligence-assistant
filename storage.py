"""SQLite for local runs; PostgreSQL when DATABASE_URL is configured."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3


DATABASE = Path(os.environ.get("VERA_DB", str(Path(__file__).with_name("vera.sqlite3"))))


class PostgresConnection:
    """Support the small SQLite-style query surface already used by the bot."""

    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        self.connection = psycopg.connect(url, row_factory=dict_row, connect_timeout=5)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.connection.__exit__(exc_type, exc_value, traceback)

    def execute(self, query: str, params=()):
        if query.startswith("INSERT OR IGNORE INTO "):
            query = query.replace("INSERT OR IGNORE INTO ", "INSERT INTO ", 1)
            query += " ON CONFLICT DO NOTHING"
        return self.connection.execute(query.replace("?", "%s"), params)

    def executescript(self, script: str):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)


def backend():
    return "postgresql" if os.environ.get("DATABASE_URL") else "sqlite"


def connect():
    url = os.environ.get("DATABASE_URL")
    if url:
        return PostgresConnection(url)
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE, timeout=10)
    db.row_factory = sqlite3.Row
    return db
