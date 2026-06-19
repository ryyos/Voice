from typing import Type
from sources import BaseSource

_registry: dict[str, Type[BaseSource]] = {}


def register_source(name: str):
    """Class decorator that registers a source plugin under the given name."""
    def decorator(cls: Type[BaseSource]) -> Type[BaseSource]:
        _registry[name] = cls
        return cls
    return decorator


def get_all_sources() -> dict[str, Type[BaseSource]]:
    return dict(_registry)
