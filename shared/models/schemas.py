from typing import Optional
from typing_extensions import TypedDict


class RawDocument(TypedDict):
    """Document as stored in MongoDB (raw zone)."""
    source: str        # e.g. "detik", "reddit"
    keyword: str
    url: str
    title: str
    content: str
    published_at: Optional[str]  # ISO 8601, None if not available
    fetched_at: str               # ISO 8601


class ClassifiedDocument(TypedDict):
    """Record as stored in PostgreSQL (structured zone)."""
    source: str
    keyword: str
    url: str
    title: str
    sentiment: str   # "positive" | "negative" | "neutral"
    stance: str      # source/topic-specific label
    summary: str
    classified_at: str  # ISO 8601
