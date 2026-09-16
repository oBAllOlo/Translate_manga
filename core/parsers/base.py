"""Parser plugin registry and base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import PageImage


class BaseParser(ABC):
    """Abstract base for site-specific manga chapter parsers.

    Subclasses MUST set *name* and *domains*, then implement *parse()*.
    Register a concrete parser by decorating the class with ``@register``.
    """

    name: str = ""
    domains: list[str] = []

    @abstractmethod
    def parse(self, url: str) -> tuple[str, list[PageImage]]:
        """Return ``(chapter_title, pages)`` for the given chapter URL."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, type[BaseParser]] = {}


def register(cls: type[BaseParser]) -> type[BaseParser]:
    """Class decorator — adds a parser to the global registry."""
    for domain in cls.domains:
        REGISTRY[domain] = cls
    return cls


def get_parser(url: str) -> BaseParser:
    """Return an instantiated parser matching *url*, or raise ValueError."""
    for domain, parser_cls in REGISTRY.items():
        if domain in url:
            return parser_cls()
    supported = ", ".join(sorted(REGISTRY.keys()))
    raise ValueError(
        f"No parser found for URL: {url}\nSupported domains: {supported}"
    )


def parse_source(url: str) -> tuple[str, list[PageImage]]:
    """Convenience wrapper: find the right parser and call it."""
    parser = get_parser(url)
    return parser.parse(url)
