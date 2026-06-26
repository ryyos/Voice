from sources import (
    BaseSource, 
    Generator, 
    PyQuery as pq
)

from sources.registry import register_source
from shared.utils import Network, Time, log

from icecream import ic

@register_source("detik")
class DetikSource(BaseSource):
    def __init__(self):
        super().__init__()
        
    def build_param(self, keyword: str, interval: str) -> str:
        _start, _end = Time.interval(interval)
        return \
            "https://www.detik.com/search/searchall?query=%s&fromdatex=%s&todatex=%s&result_type=latest&page={_page_}"\
                % (
                    keyword\
                        .replace(" ", "+"),
                    _start,
                    _end
                )
        ...
        
    async def _collect_card(self, html: str) -> list:
        html: pq = pq(html)
        return list(
            map(
                lambda x: {
                    "title": pq(x)('h3[class="media__title"]').text(),
                    "url": pq(x)('h3[class="media__title"] a').attr("href"),
                    "media": pq(x)('h2[class="media__subtitle"]').text(),
                    "desc": pq(x)('div[class="media__desc"]').text(),
                    "date": {
                        "epoch": pq(x)('div[class="media__date"] span').attr("d-time"),
                        "text": pq(x)('div[class="media__date"] span').attr("title"),
                    },
                },
                html.find(
                    'article[class="list-content__item"]'
                )
            )
        )
        ...
        
    async def _fetch_detail(self, url: str) -> dict:
        response: Network.Response = Network.get(url=url)
        html: pq = pq(response.text)
        
        return {
            "author": html.find('div[class="detail__author"]'),
            "thumbnail": {
                "url": html.find('div.detail__media img').attr("src"),
                "desc": html.find('.detail__media-caption').text(),
            }
        }
        ...
        
    async def tidying(self, raw: any) -> list|dict:
        try:
            return {
                
            }
            ...
        except Exception as err:
            ...
        ...
        
    async def process(self, quest: dict, **kwargs) -> Generator:
        _page: int = 1
        while True:
            try:
                response: Network.Response = Network.get(
                    url=self.build_param(
                        (_keyword:=quest["keyword"]),
                        (_interval:=quest["interval"])
                    )\
                        .format(
                            _page_=_page
                        )
                )
                
                for card in await self._collect_card(response.text):
                    ic(card)
                    quit()
                    ...
            except Exception as err:
                log.warning(f"[ {self.__class__} ] warning process message :: [ {str(err)} ]")
        ...