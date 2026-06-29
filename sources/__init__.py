import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pyquery import PyQuery

from shared.utils import File
from shared.utils.monitor import ProcessMonitor
from shared.mongodb.functions import Mongo


class BaseSource(ABC):
    """
    Base class for all scraper plugins.

    Subclasses must implement three focused methods:
      - collect_urls   : scrape search result pages → list of article metadata dicts
      - fetch_detail   : fetch full article content for one URL
      - fetch_comments : fetch all comments for one article

    The default process() orchestrates these stages with proper async concurrency
    and saves results to MongoDB as each piece arrives (streaming write).

    Data flow:
        collect_urls()
            → fetch_detail()  → save to "articles" collection immediately
                → fetch_comments() → save to "comments" collection immediately
    """

    @abstractmethod
    async def collect_urls(self, keyword: str, interval: str) -> list[dict]:
        """Scrape all search result pages. Return list of article metadata dicts."""
        ...

    @abstractmethod
    async def fetch_detail(self, article: dict) -> dict:
        """Fetch full article content for one article. Return enriched article dict."""
        ...

    @abstractmethod
    async def fetch_comments(self, article: dict) -> list[dict]:
        """Fetch all comments for one article. Return list of comment dicts."""
        ...

    async def process(self, quest: dict, monitor: ProcessMonitor) -> int:
        """
        Default orchestration — do NOT override unless the source needs custom flow.

        Stage 1: collect_urls   (sequential pages)
        Stage 2: fetch_detail   (all articles concurrent via create_task)
                 → save article to MongoDB immediately after each detail arrives
        Stage 3: fetch_comments (fired immediately per article as detail completes)
                 → save comments to MongoDB immediately after each batch arrives

        Returns total number of documents saved across articles + comments.
        """
        keyword  = quest["keyword"]
        interval = quest.get("interval", "30d")
        source   = self.__class__.__name__.replace("Source", "").lower()

        articles = await self.collect_urls(keyword, interval)
        if not articles:
            return 0

        detail_tid  = monitor.add_detail_task(f"[{source}] articles", total=len(articles))
        comment_tid = monitor.add_comment_task(f"[{source}] comments", total=len(articles))

        detail_tasks = [asyncio.create_task(self.fetch_detail(art)) for art in articles]

        comment_tasks: list[asyncio.Task] = []
        saved_articles = 0

        for coro in asyncio.as_completed(detail_tasks):
            article = await coro
            monitor.advance_detail(detail_tid)

            # Save article to MongoDB immediately — don't wait for its comments.
            await self._save_article(article, keyword=keyword, source=source)
            saved_articles += 1

            # Fire comment task right away — races concurrently with other sources.
            comment_tasks.append(
                asyncio.create_task(
                    self._fetch_and_save_comments(article, keyword, source, comment_tid, monitor)
                )
            )

        comment_counts: list[int] = await asyncio.gather(*comment_tasks)
        return saved_articles + sum(comment_counts)

    # ------------------------------------------------------------------
    # Internal helpers — not part of the public plugin interface
    # ------------------------------------------------------------------

    async def _save_article(self, article: dict, *, keyword: str, source: str) -> None:
        doc = {
            **article,
            "source":       source,
            "keyword":      keyword,
            "content_type": "article",
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        }
        # await asyncio.to_thread(Mongo.insert_one, "articles", doc)
        await asyncio.to_thread(File.write_json, "articles", doc)

    async def _fetch_and_save_comments(
        self,
        article: dict,
        keyword: str,
        source: str,
        task_id: int,
        monitor: ProcessMonitor,
    ) -> int:
        comments = await self.fetch_comments(article)
        monitor.advance_comment(task_id)

        if not comments:
            return 0

        docs = [
            {
                **comment,
                "source":       source,
                "keyword":      keyword,
                "article_url":  article.get("url", ""),
                "content_type": "comment",
                "fetched_at":   datetime.now(timezone.utc).isoformat(),
            }
            for comment in comments
        ]
        await asyncio.to_thread(File.write_json, "comments", docs)
        # await asyncio.to_thread(Mongo.insert_many, "comments", docs)
        return len(docs)


# Import plugins AFTER BaseSource is defined so decorators can reference it.
# Each new source file must be added to this list.
from sources.news import detik  # noqa: F401
