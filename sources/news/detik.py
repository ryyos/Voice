from sources import BaseSource
from sources.registry import register_source


@register_source("detik")
class DetikSource(BaseSource):
    def __init__(self):
        super().__init__()
        
    def fetch(self, keyword: str) -> list[dict]:
        ...
        
    def process(self, data, **kwargs):
        return super().process(data, **kwargs)
    
    def output(self, data, **kwargs):
        return super().output(data, **kwargs)
