from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor

from shared.config import settings
from shared.utils.logger import log
from .connection import PGConnection

# ── DDL — tables created on first run ────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS contents (
    id          BIGSERIAL PRIMARY KEY,
    source_id   TEXT        NOT NULL,
    source      TEXT        NOT NULL,
    keyword     TEXT        NOT NULL,
    url         TEXT,
    article_id  TEXT,
    title       TEXT,
    author      TEXT,
    media       TEXT,
    content     TEXT,
    published_at TEXT,
    mongo_id    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source, source_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id              BIGSERIAL PRIMARY KEY,
    source_id       TEXT        NOT NULL,
    source          TEXT        NOT NULL,
    keyword         TEXT        NOT NULL,
    article_id      TEXT,
    content_url     TEXT,
    mongo_parent_id TEXT,
    mongo_id        TEXT,
    author          TEXT,
    content         TEXT,
    prokontra       TEXT,
    published_at    TEXT,
    sentiment       TEXT,
    engine          TEXT,
    confidence      FLOAT,
    ai_processed    BOOLEAN     DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source, source_id)
);
"""


class PG:
    """
    PostgreSQL warehouse client — mirrors the Mongo class pattern.

    Usage:
        PG.ensure_tables()
        PG.insert_content({...})
        PG.insert_comments([{...}, ...])
        PG.update_sentiment(source_id="123", source="detik", sentiment="positive", engine="indobert", confidence=0.92)
        rows = PG.fetchall("SELECT * FROM comments WHERE ai_processed = false LIMIT 100")
    """

    _conn: PGConnection | None = None

    @classmethod
    def _get(cls) -> PGConnection:
        if cls._conn is None:
            cls._conn = PGConnection(settings.postgres_dsn)
        return cls._conn

    @classmethod
    @contextmanager
    def _cursor(cls) -> Generator:
        conn = cls._get().get()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cls._get().put(conn)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @classmethod
    def ensure_tables(cls) -> None:
        """Create tables if they don't exist. Safe to call on every startup."""
        with cls._cursor() as cur:
            cur.execute(_DDL)
        log.info("[ POSTGRESQL ] tables ensured")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @classmethod
    def insert_content(cls, data: dict) -> bool:
        """Insert one content row. Silently skips on duplicate (source, source_id)."""
        sql = """
            INSERT INTO contents
                (source_id, source, keyword, url, article_id, title, author,
                 media, content, published_at, mongo_id)
            VALUES
                (%(source_id)s, %(source)s, %(keyword)s, %(url)s, %(article_id)s,
                 %(title)s, %(author)s, %(media)s, %(content)s, %(published_at)s,
                 %(mongo_id)s)
            ON CONFLICT (source, source_id) DO NOTHING
        """
        try:
            with cls._cursor() as cur:
                cur.execute(sql, data)
                inserted = cur.rowcount > 0
            if inserted:
                log.debug("[ POSTGRESQL ] content inserted → {}", data.get("source_id"))
            return inserted
        except Exception as e:
            log.error("[ POSTGRESQL ] insert_content failed → {}", e)
            return False

    @classmethod
    def insert_comments(cls, rows: list[dict]) -> int:
        """Batch-insert comments. Skips duplicates. Returns number actually inserted."""
        if not rows:
            return 0
        sql = """
            INSERT INTO comments
                (source_id, source, keyword, article_id, content_url,
                 mongo_parent_id, mongo_id, author, content, prokontra, published_at)
            VALUES %s
            ON CONFLICT (source, source_id) DO NOTHING
        """
        values = [
            (
                r["source_id"], r["source"], r["keyword"], r.get("article_id"),
                r.get("content_url"), r.get("mongo_parent_id"), r.get("mongo_id"),
                r.get("author"), r.get("content"), r.get("prokontra"),
                r.get("published_at"),
            )
            for r in rows
        ]
        try:
            with cls._cursor() as cur:
                execute_values(cur, sql, values)
                count = cur.rowcount
            log.info("[ POSTGRESQL ] comments inserted → {}", count)
            return count
        except Exception as e:
            log.error("[ POSTGRESQL ] insert_comments failed → {}", e)
            return 0

    @classmethod
    def update_sentiment(
        cls,
        *,
        source_id: str,
        source: str,
        sentiment: str,
        engine: str,
        confidence: float,
    ) -> bool:
        sql = """
            UPDATE comments
            SET sentiment = %s, engine = %s, confidence = %s, ai_processed = TRUE
            WHERE source = %s AND source_id = %s
        """
        try:
            with cls._cursor() as cur:
                cur.execute(sql, (sentiment, engine, confidence, source, source_id))
                updated = cur.rowcount > 0
            log.debug("[ POSTGRESQL ] sentiment updated → {} {}", source, source_id)
            return updated
        except Exception as e:
            log.error("[ POSTGRESQL ] update_sentiment failed → {}", e)
            return False

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def fetchall(cls, sql: str, params: tuple | dict | None = None) -> list[dict]:
        try:
            with cls._cursor() as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            log.error("[ POSTGRESQL ] fetchall failed → {}", e)
            return []

    @classmethod
    def fetchone(cls, sql: str, params: tuple | dict | None = None) -> dict | None:
        try:
            with cls._cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            log.error("[ POSTGRESQL ] fetchone failed → {}", e)
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def close(cls) -> None:
        if cls._conn:
            cls._conn.close()
            cls._conn = None
