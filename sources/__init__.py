from abc import ABC, abstractmethod
from typing import Generator
from pyquery import PyQuery

class BaseSource(ABC):
    @abstractmethod
    async def process(self, quest: dict) -> Generator:
        """Fetch raw documents for the given keyword.

        Returns a list of dicts conforming to shared.schemas.RawDocument.
        """
        ...
        
    @abstractmethod
    async def tidying(self, raw: any) -> list|dict:
        """Fetch raw documents for the given keyword.

        Returns a list of dicts conforming to shared.schemas.RawDocument.
        """
        ...

# Import plugins AFTER BaseSource is defined so decorators can reference it.
# Each new source file must be added to this list.
from sources.news import detik  # noqa: F401
    
