import re
from datetime import datetime, timedelta

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from sources import BaseSource, PyQuery as pq
from sources.registry import register_source
from shared.utils import Network, log


@register_source("liputan6")
class Liputan6Source(BaseSource):
    """
    Liputan6.com source plugin.

    Search:   https://www.liputan6.com/search (SSR — HTML scraping)
    Comments: None — Liputan6 has no comment system.

    article_id = numeric ID from URL path (/read/{id}/).
    Pagination stops when no new articles found or seen IDs repeat (site may
    return same "latest" block on every page beyond results).
    """

    _SEARCH_URL = "https://www.liputan6.com/search?q={keyword}&page={page}"
    _BASE_URL   = "https://www.liputan6.com"
    _ID_RE      = re.compile(r"/read/(\d+)/")
    _MAX_PAGES  = 50

    def _cutoff_date(self, interval: str) -> datetime:
        try:
            days = int(interval.rstrip("d"))
        except ValueError:
            days = 30
        return datetime.now() - timedelta(days=days)

    def _parse_cards(self, html: str) -> list[dict]:
        doc  = pq(html)
        seen = set()
        cards: list[dict] = []

        for a in doc("a[href*='/read/']").items():
            href = a.attr("href") or ""
            m    = self._ID_RE.search(href)
            if not m:
                continue

            url        = href if href.startswith("http") else self._BASE_URL + href
            article_id = m.group(1)
            if article_id in seen:
                continue
            seen.add(article_id)

            title = a.find("h3").text().strip() or a.text().strip()
            if not title:
                continue

            # Category from URL: /bisnis/read/... → "bisnis"
            path_parts = href.replace(self._BASE_URL, "").lstrip("/").split("/")
            media = path_parts[0] if path_parts else ""

            # Timestamp may be a sibling <span class="timestamp"> or child
            ts = (
                a.find(".timestamp").text()
                or a.parent().find(".timestamp").text()
                or ""
            )

            cards.append({
                "url":        url,
                "content_id": article_id,
                "title":      title,
                "media":      media,
                "desc":       "",
                "date":       {"text": ts.strip()},
            })

        return cards

    @override
    async def collect_urls(self, keyword: str, interval: str) -> list[dict]:
        cutoff    = self._cutoff_date(interval)
        contents: list[dict] = []
        seen_ids: set[str]   = set()
        page = 1
        stop = False

        while not stop and page <= self._MAX_PAGES:
            response = await Network.aget(
                url=self._SEARCH_URL.format(
                    keyword=keyword.replace(" ", "+"), page=page
                )
            )
            if not response or not response.text:
                break

            cards = self._parse_cards(response.text)
            if not cards:
                break

            new_on_page = 0
            for card in cards:
                aid = card["content_id"]
                if aid in seen_ids:
                    continue
                seen_ids.add(aid)
                new_on_page += 1

                date_text = card["date"].get("text", "")
                if date_text:
                    try:
                        # Format from search page: "YYYY-MM-DD HH:MM:SS"
                        pub = datetime.strptime(date_text[:19], "%Y-%m-%d %H:%M:%S")
                        if pub < cutoff:
                            stop = True
                            break
                    except ValueError:
                        pass

                contents.append(card)

            # If every article on this page was already seen, pagination has looped
            if new_on_page == 0:
                break

            log.debug(f"[liputan6] page {page} → {len(cards)} cards, {new_on_page} new")
            page += 1

        return contents

    @override
    async def fetch_detail(self, content: dict) -> dict:
        url = content.get("url", "")
        if not url:
            return content

        response = await Network.aget(url=url)
        if not response or not response.text:
            return {**content, "raw": ""}

        doc = pq(response.text)

        # Prefer og/meta dates — more reliable than search-page timestamp
        pub_date = (
            doc('meta[property="article:published_time"]').attr("content")
            or doc('meta[name="date"]').attr("content")
            or content.get("date", {}).get("text", "")
        )
        author = (
            doc('meta[name="author"]').attr("content")
            or doc('meta[property="article:author"]').attr("content")
            or ""
        )

        return {
            **content,
            "raw":    response.text,
            "author": author,
            "date":   {"text": pub_date},
        }

    @override
    async def fetch_comments(self, content: dict) -> list[dict]:
        return []  # Liputan6 has no comment system
