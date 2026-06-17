from sources.base import BaseSource
from sources.registry import register_source


@register_source("detik")
class DetikSource(BaseSource):
    def fetch(self, keyword: str) -> list[dict]:
        # TODO: implement scraping for detik.com
        raise NotImplementedError
