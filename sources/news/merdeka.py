import re
from datetime import datetime, timedelta

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from sources import BaseSource, PyQuery as pq
from sources.registry import register_source
from shared.utils import Network, log


@register_source("merdeka")
class MerdekaSource(BaseSource):
    """
    Merdeka.com source plugin.

    Search:   https://www.merdeka.com/search/?q={keyword}&page={page} (SSR — HTML)
    Comments: None — Merdeka.com has no comment system.

    article_id = numeric segment before "-mvk.html" suffix in URL.
    E.g. /peristiwa/slug-587174-mvk.html → article_id = "587174"
    """

    _SEARCH_URL = "https://www.merdeka.com/search/?q={keyword}&page={page}"
    _BASE_URL   = "https://www.merdeka.com"
    _ID_RE      = re.compile(r"-(\d+)-mvk\.html")
    _MAX_PAGES  = 50

    # Indonesian + common English month abbreviations used by Merdeka
    _MONTHS: dict[str, int] = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "mei": 5, "may": 5, "jun": 6, "jul": 7,
        "agu": 8, "aug": 8, "sep": 9, "okt": 10, "oct": 10,
        "nov": 11, "des": 12, "dec": 12,
    }

    def _cutoff_date(self, interval: str) -> datetime:
        try:
            days = int(interval.rstrip("d"))
        except ValueError:
            days = 30
        return datetime.now() - timedelta(days=days)

    def _parse_date(self, text: str) -> datetime | None:
        """Parse dates like '30 Jun 2026' or '30 Juni 2026'."""
        parts = text.strip().split()
        if len(parts) < 3:
            return None
        try:
            day   = int(parts[0])
            month = self._MONTHS.get(parts[1].lower()[:3])
            year  = int(parts[2])
            if month:
                return datetime(year, month, day)
        except (ValueError, IndexError):
            pass
        return None

    def _parse_cards(self, html: str) -> list[dict]:
        doc  = pq(html)
        seen = set()
        cards: list[dict] = []

        for a in doc("a[href*='-mvk.html']").items():
            href = a.attr("href") or ""
            m    = self._ID_RE.search(href)
            if not m:
                continue

            article_id = m.group(1)
            if article_id in seen:
                continue
            seen.add(article_id)

            # Build full URL
            url = href if href.startswith("http") else self._BASE_URL + href

            title = a.find("h2, h3").text().strip() or a.text().strip()
            if not title:
                continue

            # Category from URL path: /peristiwa/slug-id-mvk.html → "peristiwa"
            path_parts = href.replace(self._BASE_URL, "").lstrip("/").split("/")
            media = path_parts[0] if path_parts else ""

            # Date from <time> sibling or parent's <time>
            ts = (
                a.find("time").text()
                or a.parent().find("time").text()
                or a.closest("article, li, div").find("time").text()
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
                    pub = self._parse_date(date_text)
                    if pub and pub < cutoff:
                        stop = True
                        break

                contents.append(card)

            if new_on_page == 0:
                break

            log.debug(f"[merdeka] page {page} → {len(cards)} cards, {new_on_page} new")
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

        pub_date = (
            doc('meta[property="article:published_time"]').attr("content")
            or doc('meta[name="date"]').attr("content")
            or doc('time[datetime]').attr("datetime")
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
        return []  # Merdeka.com has no comment system
