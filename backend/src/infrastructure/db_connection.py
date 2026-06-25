"""Centralized synchronous SQLite connection helper.

Replaces all pymysql.connect(**settings.db_params) calls across the codebase.
Provides both plain tuple cursor and dict-like Row cursor modes.
"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Generator

from src.config import settings


def _ensure_db_dir():
    """Ensure the database directory exists."""
    db_dir = os.path.dirname(settings.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Get a plain sqlite3 connection (rows as tuples).

    Usage:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT ...", (param,))
            rows = cur.fetchall()
        finally:
            conn.close()
    """
    _ensure_db_dir()
    conn = sqlite3.connect(settings.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_dict_connection() -> sqlite3.Connection:
    """Get a sqlite3 connection with Row factory (rows as dict-like objects).

    Usage:
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT ...", (param,))
            row = cur.fetchone()
            # row["column_name"] works
        finally:
            conn.close()
    """
    _ensure_db_dir()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def db_cursor() -> Generator[sqlite3.Cursor, None, None]:
    """Context manager for quick DB operations (auto-commit, auto-close).

    Usage:
        with db_cursor() as cur:
            cur.execute("SELECT ...", (param,))
            rows = cur.fetchall()
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


@contextmanager
def db_dict_cursor() -> Generator[sqlite3.Cursor, None, None]:
    """Context manager for quick DB operations with dict-like rows.

    Usage:
        with db_dict_cursor() as cur:
            cur.execute("SELECT ...", (param,))
            row = cur.fetchone()
            # row["column_name"] works
    """
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()
