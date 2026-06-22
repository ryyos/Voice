from abc import ABC, abstractmethod


class BaseSource(ABC):
    @abstractmethod
    def process(self, keyword: str) -> list[dict]:
        """Fetch raw documents for the given keyword.

        Returns a list of dicts conforming to shared.schemas.RawDocument.
        """
        ...

# Import plugins AFTER BaseSource is defined so decorators can reference it.
# Each new source file must be added to this list.
from sources.news import detik  # noqa: F401
    
