from __future__ import annotations

import json as _json
from datetime import datetime

from bson import ObjectId
from pyquery import PyQuery as pq

from shared.config import settings
from shared.mongodb.functions import Mongo
from shared.postgresql.functions import PG
from shared.redys.functions import Redys
from shared.utils.logger import log

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts_to_iso(ts: int | float | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.utcfromtimestamp(float(ts)).isoformat()
    except Exception:
        return ""


def _load_raw(raw) -> dict:
    """Normalise raw field to dict regardless of whether it was stored as str or dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return _json.loads(raw)
        except Exception:
            pass
    return {}


# ── News content parsers (HTML) ───────────────────────────────────────────────

def _parse_detik_content(doc: dict) -> dict | None:
    raw_html = doc.get("raw", "")
    if not raw_html:
        log.warning("[ CLEANER ] detik content {} has empty raw — skipping", doc.get("content_id"))
        return None

    page = pq(raw_html)
    return {
        "source_id":    doc.get("content_id") or doc.get("url", ""),
        "source":       doc["source"],
        "keyword":      doc["keyword"],
        "url":          doc.get("url", ""),
        "content_id":   doc.get("content_id", ""),
        "title":        doc.get("title", ""),
        "author":       page.find('div[class="detail__author"]').text(),
        "media":        doc.get("media", ""),
        "content":      page.find(".detail__body-text").text(),
        "published_at": doc.get("published_at", ""),
        "mongo_id":     str(doc["_id"]),
    }


def _parse_cnn_content(doc: dict) -> dict | None:
    raw_html = doc.get("raw", "")
    if not raw_html:
        return None

    page = pq(raw_html)
    return {
        "source_id":    doc.get("content_id") or doc.get("url", ""),
        "source":       doc["source"],
        "keyword":      doc["keyword"],
        "url":          doc.get("url", ""),
        "content_id":   doc.get("content_id", ""),
        "title":        doc.get("title", ""),
        "author":       page.find('meta[name="author"]').attr("content") or "",
        "media":        doc.get("media", ""),
        "content":      page.find(".detail-text, .content-detail, .detail__body-text").text(),
        "published_at": doc.get("published_at", ""),
        "mongo_id":     str(doc["_id"]),
    }


def _parse_liputan6_content(doc: dict) -> dict | None:
    raw_html = doc.get("raw", "")
    if not raw_html:
        return None

    page = pq(raw_html)
    return {
        "source_id":    doc.get("content_id") or doc.get("url", ""),
        "source":       doc["source"],
        "keyword":      doc["keyword"],
        "url":          doc.get("url", ""),
        "content_id":   doc.get("content_id", ""),
        "title":        page.find('meta[property="og:title"]').attr("content") or doc.get("title", ""),
        "author":       doc.get("author", "") or page.find('meta[name="author"]').attr("content") or "",
        "media":        doc.get("media", ""),
        "content":      page.find(".article-content-body, .read-page--content").text(),
        "published_at": doc.get("published_at", ""),
        "mongo_id":     str(doc["_id"]),
    }


def _parse_merdeka_content(doc: dict) -> dict | None:
    raw_html = doc.get("raw", "")
    if not raw_html:
        return None

    page = pq(raw_html)
    return {
        "source_id":    doc.get("content_id") or doc.get("url", ""),
        "source":       doc["source"],
        "keyword":      doc["keyword"],
        "url":          doc.get("url", ""),
        "content_id":   doc.get("content_id", ""),
        "title":        page.find('meta[property="og:title"]').attr("content") or doc.get("title", ""),
        "author":       doc.get("author", "") or page.find('meta[name="author"]').attr("content") or "",
        "media":        doc.get("media", ""),
        "content":      page.find(".article-body-content, .content-detail").text(),
        "published_at": doc.get("published_at", ""),
        "mongo_id":     str(doc["_id"]),
    }


# ── News comment parsers (Detik/CNN GraphQL — same schema) ───────────────────

def _parse_graphql_comments(doc: dict) -> list[dict]:
    """
    Shared parser for Detik and CNN comment documents.
    Both use the same GraphQL API response shape.
    """
    raw = doc.get("raw", {})
    if not raw or not isinstance(raw, dict):
        return []

    base = {
        "source":          doc["source"],
        "keyword":         doc["keyword"],
        "content_id":      doc.get("content_id", ""),
        "content_url":     doc.get("content_url", ""),
        "mongo_parent_id": doc.get("parent_id", ""),
        "mongo_id":        str(doc["_id"]),
    }

    results = []

    def _author_str(a) -> str:
        if isinstance(a, dict):
            return a.get("name", "")
        return str(a or "")

    comment_id = raw.get("id", "")
    if comment_id:
        results.append({
            **base,
            "source_id":    str(comment_id),
            "author":       _author_str(raw.get("author")),
            "content":      raw.get("content", ""),
            "prokontra":    str(raw.get("prokontra") or ""),
            "published_at": raw.get("create_date", ""),
        })

    for child in raw.get("child", []) or []:
        child_id = child.get("id", "")
        if child_id:
            results.append({
                **base,
                "source_id":    str(child_id),
                "author":       _author_str(child.get("author")),
                "content":      child.get("content", ""),
                "prokontra":    str(child.get("prokontra") or ""),
                "published_at": child.get("create_date", ""),
            })

    return results


# ── YouTube parsers ───────────────────────────────────────────────────────────

def _parse_youtube_content(doc: dict) -> dict | None:
    raw = _load_raw(doc.get("raw", {}))
    return {
        "source_id":    doc.get("content_id") or doc.get("url", ""),
        "source":       doc["source"],
        "keyword":      doc["keyword"],
        "url":          doc.get("url", ""),
        "content_id":   doc.get("content_id", ""),
        "title":        doc.get("title", "") or raw.get("title", ""),
        "author":       raw.get("uploader", ""),
        "media":        doc.get("media", "") or raw.get("uploader", ""),
        "content":      raw.get("description", ""),
        "published_at": doc.get("published_at", "") or raw.get("uploadDate", ""),
        "mongo_id":     str(doc["_id"]),
    }


def _parse_youtube_comment(doc: dict) -> list[dict]:
    raw = doc.get("raw", {})
    if not raw or not isinstance(raw, dict):
        return []

    comment_id = raw.get("commentId", "")
    if not comment_id:
        return []

    return [{
        "source_id":       comment_id,
        "source":          doc["source"],
        "keyword":         doc["keyword"],
        "content_id":      doc.get("content_id", ""),
        "content_url":     doc.get("content_url", ""),
        "mongo_parent_id": doc.get("parent_id", ""),
        "mongo_id":        str(doc["_id"]),
        "author":          raw.get("author", ""),
        "content":         raw.get("commentText", ""),
        "prokontra":       None,
        "published_at":    str(raw.get("commentedTime", "") or raw.get("published", "") or raw.get("publishedDate", "")),
    }]


# ── Reddit parsers ────────────────────────────────────────────────────────────

def _parse_reddit_content(doc: dict) -> dict | None:
    post = _load_raw(doc.get("raw", {}))
    return {
        "source_id":    doc.get("content_id") or post.get("id") or doc.get("url", ""),
        "source":       doc["source"],
        "keyword":      doc["keyword"],
        "url":          doc.get("url", ""),
        "content_id":   doc.get("content_id", ""),
        "title":        doc.get("title", "") or post.get("title", ""),
        "author":       post.get("author", ""),
        "media":        doc.get("media", ""),
        "content":      post.get("selftext", ""),
        "published_at": doc.get("published_at", "") or _ts_to_iso(post.get("created_utc")),
        "mongo_id":     str(doc["_id"]),
    }


def _parse_reddit_comment(doc: dict) -> list[dict]:
    raw = doc.get("raw", {})
    if not raw or not isinstance(raw, dict):
        return []

    comment_id = raw.get("id", "")
    if not comment_id:
        return []

    return [{
        "source_id":       comment_id,
        "source":          doc["source"],
        "keyword":         doc["keyword"],
        "content_id":      doc.get("content_id", ""),
        "content_url":     doc.get("content_url", ""),
        "mongo_parent_id": doc.get("parent_id", ""),
        "mongo_id":        str(doc["_id"]),
        "author":          raw.get("author", ""),
        "content":         raw.get("body", ""),
        "prokontra":       None,
        "published_at":    _ts_to_iso(raw.get("created_utc")),
    }]


# ── Dispatch tables ───────────────────────────────────────────────────────────

_CONTENT_PARSERS = {
    "detik":    _parse_detik_content,
    "cnn":      _parse_cnn_content,
    "liputan6": _parse_liputan6_content,
    "merdeka":  _parse_merdeka_content,
    "youtube":  _parse_youtube_content,
    "reddit":   _parse_reddit_content,
}

_COMMENT_PARSERS = {
    "detik":   _parse_graphql_comments,
    "cnn":     _parse_graphql_comments,
    "youtube": _parse_youtube_comment,
    "reddit":  _parse_reddit_comment,
}


# ── Cleaner ───────────────────────────────────────────────────────────────────


class Cleaner:
    """
    Reads raw_documents from MongoDB (paginated via _id checkpoint in Valkey),
    parses the raw field per source+type, and inserts cleaned rows into PostgreSQL.

    Checkpoint key: "cleaner:checkpoint" → last processed MongoDB ObjectId (str).
    Mongo has no status flags — checkpoint is the only state.
    """

    BATCH_SIZE = 200

    def run(self) -> int:
        """Process all pending documents. Returns total rows inserted into PostgreSQL."""
        PG.ensure_tables()

        checkpoint = Redys.get_checkpoint()
        query = {"_id": {"$gt": ObjectId(checkpoint)}} if checkpoint else {}
        log.info("[ CLEANER ] starting — checkpoint={}", checkpoint or "beginning")

        total_contents = 0
        total_comments = 0
        last_id: str | None = None

        for doc in Mongo.find_iter(
            settings.mongo_collection,
            query,
            sort=[("_id", 1)],
            batch_size=self.BATCH_SIZE,
        ):
            dtype  = doc.get("type", "")
            source = doc.get("source", "")
            last_id = str(doc["_id"])

            try:
                if dtype == "content":
                    parser = _CONTENT_PARSERS.get(source)
                    if not parser:
                        log.warning("[ CLEANER ] no content parser for source '{}'", source)
                    else:
                        parsed = parser(doc)
                        if parsed and PG.insert_content(parsed):
                            total_contents += 1

                elif dtype == "comment":
                    parser = _COMMENT_PARSERS.get(source)
                    if not parser:
                        log.warning("[ CLEANER ] no comment parser for source '{}'", source)
                    else:
                        rows = parser(doc)
                        if rows:
                            total_comments += PG.insert_comments(rows)

            except Exception as e:
                log.error("[ CLEANER ] error processing {} {} → {}", dtype, last_id, e)

            # Update checkpoint after every document so a crash doesn't lose progress.
            if last_id:
                Redys.set_checkpoint(last_id)

        log.info(
            "[ CLEANER ] done — contents={} comments={} last_id={}",
            total_contents, total_comments, last_id or "none",
        )
        return total_contents + total_comments
