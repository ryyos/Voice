# Import all source plugins here so their @register_source decorators fire on import.
# Each new source file must be added to this list.
from sources.news import detik  # noqa: F401

from abc import ABC, abstractmethod


class BaseSource(ABC):
    @abstractmethod
    def fetch(self, keyword: str) -> list[dict]:
        """Fetch raw documents for the given keyword.

        Returns a list of dicts conforming to shared.schemas.RawDocument.
        """
        ...
    
    @abstractmethod
    def process(self, data: dict, **kwargs) -> list[dict]:
        ...
        
    @abstractmethod
    def output(self, data: dict, **kwargs) -> None:
        ...
    
