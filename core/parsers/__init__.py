"""Parser package — auto-registers all built-in parsers on import."""
from core.parsers.base import (  # noqa: F401 — re-export for convenience
    REGISTRY,
    BaseParser,
    get_parser,
    parse_source,
    register,
)

# Import each parser module so that the ``@register`` decorators run.
from core.parsers import isekainonbiri as _  # noqa: F401
from core.parsers import mangablaze as _  # noqa: F401
from core.parsers import mangadex as _  # noqa: F401
from core.parsers import weebcentral as _  # noqa: F401
