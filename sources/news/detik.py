try:
    from typing import override
except ImportError:
    from typing_extensions import override

from sources import BaseSource, PyQuery as pq
from sources.registry import register_source
from shared.utils import Network, Time, log, Search
from icecream import ic


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
        articles: list[dict] = list()
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
            articles.extend(cards)
            log.debug(f"[detik] page {page} → {len(cards)} cards")
            page += 1
        return articles

    @override
    async def fetch_detail(self, article: dict) -> dict:
        url = article.get("url", "")
        if not url:
            return article

        response = await Network.aget(url=url)
        if not response or not response.text:
            return article

        doc = pq(response.text)
        return {
            **article,
            "author":    doc.find('div[class="detail__author"]').text(),
            "thumbnail": {
                "url":  doc.find("div.detail__media img").attr("src"),
                "desc": doc.find(".detail__media-caption").text(),
            },
            "content": doc.find(".detail__body-text").text(),
            "article_id": doc.find('meta[name="dtk:articleid"]').attr("content")
        }

    @override
    async def fetch_comments(self, article: dict) -> list[dict]:
        article_id = article.get("article_id", "")
        if not article_id:
            return []

        comments: list[dict] = []
        page = 1
        while True:
            response: Network.Response = await Network.apost(
                url=self._COMMENT_ENDPOINT,
                json=self._build_comment_payload(article_id, page),
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
