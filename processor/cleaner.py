from __future__ import annotations

from bson import ObjectId
from pyquery import PyQuery as pq

from shared.mongodb.functions import Mongo
from shared.postgresql.functions import PG
from shared.redys.functions import Redys
from shared.utils.logger import log

# ── Per-source parsers ────────────────────────────────────────────────────────
#
# Each parser receives the full MongoDB document and returns a dict ready
# for PostgreSQL insert (or None to skip).
# Add new sources here as they're added to sources/.


def _parse_detik_content(doc: dict) -> dict | None:
    raw_html = doc.get("raw", "")
    if not raw_html:
        log.warning("[ CLEANER ] detik content {} has empty raw — skipping", doc.get("article_id"))
        return None

    page = pq(raw_html)
    return {
        "source_id":   doc.get("article_id") or doc.get("url", ""),
        "source":      doc["source"],
        "keyword":     doc["keyword"],
        "url":         doc.get("url", ""),
        "article_id":  doc.get("article_id", ""),
        "title":       doc.get("title", ""),
        "author":      page.find('div[class="detail__author"]').text(),
        "media":       doc.get("media", ""),
        "content":     page.find(".detail__body-text").text(),
        "published_at": doc.get("published_at", ""),
        "mongo_id":    str(doc["_id"]),
    }


def _parse_detik_comment(doc: dict) -> list[dict]:
    raw = doc.get("raw", {})
    if not raw or not isinstance(raw, dict):
        return []

    base = {
        "source":          doc["source"],
        "keyword":         doc["keyword"],
        "article_id":      doc.get("article_id", ""),
        "content_url":     doc.get("content_url", ""),
        "mongo_parent_id": doc.get("parent_id", ""),
        "mongo_id":        str(doc["_id"]),
    }

    results = []

    # Parent comment
    comment_id = raw.get("id", "")
    if comment_id:
        results.append({
            **base,
            "source_id":    str(comment_id),
            "author":       raw.get("author", ""),
            "content":      raw.get("content", ""),
            "prokontra":    raw.get("prokontra", ""),
            "published_at": raw.get("create_date", ""),
        })

    # Child (reply) comments — each is its own row in PostgreSQL
    for child in raw.get("child", []) or []:
        child_id = child.get("id", "")
        if child_id:
            results.append({
                **base,
                "source_id":    str(child_id),
                "author":       child.get("author", ""),
                "content":      child.get("content", ""),
                "prokontra":    child.get("prokontra", ""),
                "published_at": child.get("create_date", ""),
            })

    return results


# Dispatch tables — add new sources here
_CONTENT_PARSERS = {
    "detik": _parse_detik_content,
}
_COMMENT_PARSERS = {
    "detik": _parse_detik_comment,
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
            "raw_documents",
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
