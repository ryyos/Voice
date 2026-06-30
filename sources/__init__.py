import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pyquery import PyQuery

from shared.config import settings
from shared.utils import ProcessMonitor, Endecode
from shared.mongodb.functions import Mongo
from shared.redys import Redys


class BaseSource(ABC):
    """
    Base class for all scraper plugins.

    Subclasses must implement three focused methods:
      - collect_urls   : scrape search result pages → list of content metadata dicts
      - fetch_detail   : fetch content page → dict with article_id + raw field
      - fetch_comments : fetch all comment pages → list of raw API objects

    All data is saved to MongoDB raw_documents (single collection, insert-only).
    Parsing/cleaning happens in the cleaning service, NOT here.

    Data flow:
        collect_urls()
            → fetch_detail()  → raw_documents {type: "content", raw: "<html>"}
                → fetch_comments() → raw_documents {type: "comment", raw: {...}, parent_id}
    """

    MAX_COMMENT_PAGES: int = 10  # override per source if needed

    @abstractmethod
    async def collect_urls(self, keyword: str, interval: str) -> list[dict]:
        """Scrape all search result pages. Return list of content metadata dicts."""
        ...

    @abstractmethod
    async def fetch_detail(self, content: dict) -> dict:
        """
        Fetch content page. Return dict containing at minimum:
          - article_id : str — needed immediately for the comment API
          - raw        : str/dict — raw payload for the cleaning service
        """
        ...

    @abstractmethod
    async def fetch_comments(self, content: dict) -> list[dict]:
        """
        Fetch all comment pages. Return list of raw API objects (not parsed).
        Each object becomes one document in raw_documents.
        """
        ...

    async def process(self, quest: dict, monitor: ProcessMonitor) -> int:
        """
        Default orchestration — do NOT override unless the source needs custom flow.

        Stage 1: collect_urls   (sequential pages)
        Stage 2: fetch_detail   (all contents concurrent via create_task)
                 → save raw content to MongoDB immediately, capture _id
        Stage 3: fetch_comments (fired immediately per content as detail completes)
                 → save raw comments to MongoDB, each linked via parent_id

        Returns total number of documents saved across contents + comments.
        """
        keyword: str = quest["keyword"]
        force: bool  = quest["force"]
        interval: str = quest.get("interval", "30d")
        source = self.__class__.__name__.replace("Source", "").lower()

        contents = await self.collect_urls(keyword, interval)
        if not contents:
            return 0

        detail_tid  = monitor.add_detail_task(f"[{source}] contents", total=len(contents))
        comment_tid = monitor.add_comment_task(f"[{source}] comments", total=len(contents))

        detail_tasks = [
            asyncio.create_task(self.fetch_detail(item))
            for item in contents
            if not Redys.cache_exists(Endecode.md5(item["url"])) or force
        ]

        comment_tasks: list[asyncio.Task] = []
        saved_contents = 0

        for coro in asyncio.as_completed(detail_tasks):
            content = await coro
            monitor.advance_detail(detail_tid)

            # Save raw content and capture its MongoDB _id for parent_id in comments.
            content_mongo_id = await self._save_content(content, keyword=keyword, source=source)
            saved_contents += 1

            # Mark URL as scraped so future runs skip it (unless force=True).
            await asyncio.to_thread(Redys.cache_set, Endecode.md5(content["url"]))

            comment_tasks.append(
                asyncio.create_task(
                    self._fetch_and_save_comments(
                        content, keyword, source, comment_tid, monitor,
                        parent_id=content_mongo_id,
                    )
                )
            )

        comment_counts: list[int] = await asyncio.gather(*comment_tasks)
        return saved_contents + sum(comment_counts)

    # ------------------------------------------------------------------
    # Internal helpers — not part of the public plugin interface
    # ------------------------------------------------------------------

    async def _save_content(
        self, content: dict, *, keyword: str, source: str
    ) -> str | None:
        """
        Save raw content to MongoDB raw_documents.
        Returns the inserted MongoDB _id (str) so comments can reference it via parent_id.
        """
        doc = {
            "type": "content",
            "source": source,
            "keyword": keyword,
            "url": content.get("url", ""),
            "article_id": content.get("article_id", ""),
            "title": content.get("title", ""),
            "media": content.get("media", ""),
            "desc": content.get("desc", ""),
            "published_at": content.get("date", {}).get("text", ""),
            "raw": content.get("raw", ""),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        return await asyncio.to_thread(Mongo.insert_one, settings.mongo_collection, doc)

    async def _fetch_and_save_comments(
        self,
        content: dict,
        keyword: str,
        source: str,
        task_id: int,
        monitor: ProcessMonitor,
        *,
        parent_id: str | None,
    ) -> int:
        """
        Fetch and save raw comments for one content item.
        Each raw API object from fetch_comments becomes one document in raw_documents.
        """
        comments = await self.fetch_comments(content)
        monitor.advance_comment(task_id)

        if not comments:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        docs = [
            {
                "type": "comment",
                "source": source,
                "keyword": keyword,
                "article_id": content.get("article_id", ""),
                "content_url": content.get("url", ""),
                "parent_id": parent_id,
                "raw": comment,
                "fetched_at": now,
            }
            for comment in comments
        ]
        return await asyncio.to_thread(Mongo.insert_many, settings.mongo_collection, docs)


# Import plugins AFTER BaseSource is defined so decorators can reference it.
# Each new source file must be added to this list.
from sources.news import detik      # noqa: F401
from sources.socmed import youtube  # noqa: F401
