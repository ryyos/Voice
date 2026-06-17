from abc import ABC, abstractmethod


class BaseSource(ABC):
    @abstractmethod
    def fetch(self, keyword: str) -> list[dict]:
        """Fetch raw documents for the given keyword.

        Returns a list of dicts conforming to shared.schemas.RawDocument.
        """
        ...
