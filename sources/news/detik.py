try:
    from typing import override
except ImportError:
    from typing_extensions import override

from sources import BaseSource, PyQuery as pq
from sources.registry import register_source
from shared.utils import Network, Time, log, Search


@register_source("detik")
class DetikSource(BaseSource):

    _SEARCH_URL = (
        "https://www.detik.com/search/searchall"
        "?query={keyword}&fromdatex={start}&todatex={end}"
        "&result_type=latest&page={page}"
    )
    _COMMENT_ENDPOINT = "https://apicomment.detik.com/graphql"
    _COMMENT_QUERY = """
        query search(
            $type: String!, $size: Int!, $sort: String!, $page: Int!,
            $adsLabelKanal: String, $adsEnv: String, $query: [ElasticSearchAggregation]
        ) {
            search(
                type: $type, size: $size, sort: $sort, page: $page,
                adsLabelKanal: $adsLabelKanal, adsEnv: $adsEnv, query: $query
            ) {
                paging sorting counter counterparent profile
                hits {
                    posisi hasAds
                    results {
                        id author content like dislike prokontra
                        status moderation_level news create_date
                        pilihanredaksi pin pin_date refer
                        liker    { name uniqueid }
                        disliker { name uniqueid }
                        reporter { id status_report }
                        child {
                            id child parent author content like dislike prokontra
                            status moderation_level create_date
                            pilihanredaksi pin pin_date refer authorRefer
                            liker    { name uniqueid }
                            disliker { name uniqueid }
                            reporter { id status_report }
                        }
                    }
                }
            }
        }
    """

    def _search_url(self, keyword: str, interval: str, page: int) -> str:
        start, end = Time.interval(interval)
        return self._SEARCH_URL.format(
            keyword=keyword.replace(" ", "+"),
            start=start,
            end=end,
            page=page,
        )

    def _build_comment_payload(self, article_id: str, page: int) -> dict:
        return {
            "query": self._COMMENT_QUERY,
            "variables": {
                "type": "comment",
                "sort": "newest_v2",
                "size": 10,
                "page": page,
                "query": [
                    {"name": "news.artikel", "terms": article_id},
                    {"name": "news.site",    "terms": "dtk"},
                ],
                "adsEnv": "desktop",
            },
        }

    def _parse_cards(self, html: str) -> list[dict]:
        doc = pq(html)
        return [
            {
                "title": pq(x)('h3[class="media__title"]').text(),
                "url":   pq(x)('h3[class="media__title"] a').attr("href"),
                "media": pq(x)('h2[class="media__subtitle"]').text(),
                "desc":  pq(x)('div[class="media__desc"]').text(),
                "date": {
                    "epoch": pq(x)('div[class="media__date"] span').attr("d-time"),
                    "text":  pq(x)('div[class="media__date"] span').attr("title"),
                },
            }
            for x in doc.find('article[class="list-content__item"]')
        ]

    @override
    async def collect_urls(self, keyword: str, interval: str) -> list[dict]:
        contents: list[dict] = []
        page = 1
        while True:
            response: Network.Response = await Network.aget(
                url=self._search_url(keyword, interval, page)
            )
            if not response or not response.text:
                break
            cards = self._parse_cards(response.text)
            if not cards:
                break
            contents.extend(cards)
            log.debug(f"[detik] page {page} → {len(cards)} cards")
            page += 1
        return contents

    @override
    async def fetch_detail(self, content: dict) -> dict:
        url = content.get("url", "")
        if not url:
            return content

        response = await Network.aget(url=url)
        if not response or not response.text:
            return content

        doc = pq(response.text)
        return {
            **content,
            "content_id": doc.find('meta[name="dtk:articleid"]').attr("content") or "",
            "raw": response.text,
        }

    @override
    async def fetch_comments(self, content: dict) -> list[dict]:
        content_id = content.get("content_id", "")
        if not content_id:
            return []

        comments: list[dict] = []
        page = 1
        while page <= self.MAX_COMMENT_PAGES:
            response: Network.Response = await Network.apost(
                url=self._COMMENT_ENDPOINT,
                json=self._build_comment_payload(content_id, page),
                headers={
                    "content-type": "application/json",
                    "origin": "https://comment.detik.com",
                },
            )
            if not response or not response.ok:
                break
            results = Search.jpath("data.search.hits.results", response.json()) or []
            if not results:
                break
            log.debug(f"[detik] comments page {page} → {len(results)} results")
            comments.extend(results)
            page += 1
        return comments
