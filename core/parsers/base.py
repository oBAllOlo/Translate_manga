"""Parser plugin registry and base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
import ipaddress
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlparse

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


def _is_private_or_loopback_host(hostname: str) -> bool:
    """Check if a hostname resolves to private, loopback, or link-local IP."""
    lower = hostname.lower()
    if lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    try:
        ip = ipaddress.ip_address(lower)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for *_, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True
    except (socket.gaierror, ValueError):
        pass
    return False


def get_parser(url: str) -> BaseParser:
    """Return an instantiated parser matching *url*, or raise ValueError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid or untrusted URL scheme: {parsed.scheme!r}. Expected 'http' or 'https'.")

    hostname = (parsed.hostname or "").lower()
    if not hostname or _is_private_or_loopback_host(hostname):
        raise ValueError(f"Access to private, loopback, or missing host is prohibited: {hostname!r}")

    for domain, parser_cls in REGISTRY.items():
        if hostname == domain or hostname.endswith("." + domain):
            return parser_cls()
    supported = ", ".join(sorted(REGISTRY.keys()))
    raise ValueError(
        f"No parser found for URL: {url}\nSupported domains: {supported}"
    )


def parse_source(url: str) -> tuple[str, list[PageImage]]:
    """Convenience wrapper: find the right parser and call it."""
    parser = get_parser(url)
    return parser.parse(url)
