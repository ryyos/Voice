from datetime import datetime, timedelta

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from sources import BaseSource
from sources.registry import register_source
from shared.utils import Network, log, Search


@register_source("cnn")
class CnnSource(BaseSource):
    """
    CNN Indonesia source plugin.

    Search:   https://www.cnnindonesia.com/api/search (JSON, no HTML scraping)
    Comments: https://apicomment.cnnindonesia.com/graphql (identical structure to Detik)

    content_id = intidberita from search API (used as news.artikel in comment filter).
    """

    _SEARCH_API  = "https://www.cnnindonesia.com/api/search"
    _COMMENT_ENDPOINT = "https://apicomment.cnnindonesia.com/graphql"
    _COMMENT_QUERY = """
        query search($type: String!, $size: Int!, $sort: String!, $page: Int!, $adsLabelKanal: String, $adsEnv: String, $query: [ElasticSearchAggregation]) {
            search(type: $type, size: $size, sort: $sort, page: $page, adsLabelKanal: $adsLabelKanal, adsEnv: $adsEnv, query: $query) {
                hits {
                    results {
                        id author content like dislike prokontra status moderation_level news create_date
                        child {
                            id author content create_date moderation_level authorRefer
                        }
                    }
                }
            }
        }
    """

    def _date_range(self, interval: str) -> tuple[str, str]:
        """Convert '30d' → ('06/02/2026', '07/02/2026') — CNN uses MM/DD/YYYY."""
        try:
            days = int(interval.rstrip("d"))
        except ValueError:
            days = 30
        end   = datetime.now()
        start = end - timedelta(days=days)
        fmt   = "%m/%d/%Y"
        return start.strftime(fmt), end.strftime(fmt)

    def _build_comment_payload(self, content_id: str, page: int) -> dict:
        return {
            "query": self._COMMENT_QUERY,
            "variables": {
                "type":  "comment",
                "sort":  "newest_v2",
                "size":  10,
                "page":  page,
                "query": [
                    {"name": "news.artikel", "terms": str(content_id)},
                    {"name": "news.site",    "terms": "cnn"},
                ],
                "adsEnv": "desktop",
            },
        }

    @override
    async def collect_urls(self, keyword: str, interval: str) -> list[dict]:
        fromdate, todate = self._date_range(interval)
        contents: list[dict] = []
        seen_ids: set[str] = set()
        page = 1

        while True:
            response = await Network.aget(
                url=self._SEARCH_API,
                params={
                    "query":    keyword,
                    "page":     page,
                    "fromdate": fromdate,
                    "todate":   todate,
                },
                headers={
                    "Referer":    "https://www.cnnindonesia.com/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
            )
            if not response or not response.ok:
                break

            data = response.json().get("data") or []
            if not data:
                break

            new_on_page = 0
            for item in data:
                iid = str(item.get("intidberita", ""))
                if not iid or iid in seen_ids:
                    continue
                seen_ids.add(iid)
                new_on_page += 1
                author = item.get("author") or {}
                contents.append({
                    "url":        item.get("url", ""),
                    "content_id": iid,
                    "title":      item.get("strjudul", ""),
                    "media":      item.get("strnmkanal", ""),
                    "desc":       item.get("strringkasan", ""),
                    "date": {
                        "text": item.get("dtnewsdate", ""),
                    },
                    "author": author.get("name", "") if isinstance(author, dict) else "",
                })

            log.debug(f"[cnn] page {page} → {new_on_page} new items (total {len(contents)})")
            if new_on_page == 0:
                break
            page += 1

        return contents

    _DETAIL_HEADERS = {
        "Referer":    "https://www.cnnindonesia.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    @override
    async def fetch_detail(self, content: dict) -> dict:
        """
        content_id is already populated from collect_urls (intidberita).
        This step only fetches raw HTML for the datalake.
        """
        url = content.get("url", "")
        if not url:
            return content

        response = await Network.aget(url=url, headers=self._DETAIL_HEADERS)
        if not response or not response.text:
            return {**content, "raw": ""}

        return {**content, "raw": response.text}

    @override
    async def fetch_comments(self, content: dict) -> list[dict]:
        content_id = content.get("content_id", "")
        if not content_id:
            return []

        comments: list[dict] = []
        page = 1
        while page <= self.MAX_COMMENT_PAGES:
            response = await Network.apost(
                url=self._COMMENT_ENDPOINT,
                json=self._build_comment_payload(content_id, page),
                headers={
                    "content-type": "application/json",
                    "origin":       "https://comment.cnnindonesia.com",
                },
            )
            if not response or not response.ok:
                break
            results = Search.jpath("data.search.hits.results", response.json()) or []
            if not results:
                break
            log.debug(f"[cnn] comments page {page} → {len(results)} results")
            comments.extend(results)
            page += 1

        return comments
