"""Centralized logging configuration for Manga Translate."""
from __future__ import annotations

import logging
from typing import Set

LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class PollingEndpointFilter(logging.Filter):
    """Filter out high-frequency polling requests from access logs unless they fail.

    Suppresses noisy GET /api/jobs and GET /api/chapters polling loops that drown out
    meaningful application progress logs.
    """

    DEFAULT_QUIET_PATHS: Set[str] = {
        "/api/jobs",
        "/api/chapters",
        "/favicon.ico",
    }

    def __init__(self, quiet_paths: Set[str] | None = None):
        super().__init__()
        self.quiet_paths = quiet_paths or self.DEFAULT_QUIET_PATHS

    def filter(self, record: logging.LogRecord) -> bool:
        # Check structured args if available from uvicorn.access
        if record.args and len(record.args) >= 3:
            try:
                req_line = str(record.args[1])
                status = int(record.args[2])
                if status in (200, 304):
                    parts = req_line.split()
                    if len(parts) >= 2 and parts[0] == "GET":
                        raw_path = parts[1].split("?")[0].rstrip("/")
                        if raw_path in self.quiet_paths:
                            return False
            except Exception:
                pass

        # Fallback to string message inspection
        msg = record.getMessage()
        if " 200" in msg or " 304" in msg:
            for path in self.quiet_paths:
                if f"GET {path} " in msg or f"GET {path}? " in msg or f"GET {path}?" in msg or f"GET {path}/ " in msg:
                    return False
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configure unified logging format and access log filtering."""
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Root logger
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(formatter)

    # 2. Uvicorn default & error loggers
    for logger_name in ("uvicorn", "uvicorn.error"):
        u_logger = logging.getLogger(logger_name)
        u_logger.setLevel(level)
        for handler in u_logger.handlers:
            handler.setFormatter(formatter)

    # 3. Uvicorn access logger
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(level)

    try:
        from uvicorn.logging import AccessFormatter
        access_fmt = "%(asctime)s [%(levelname)s] [uvicorn.access] %(client_addr)s - \"%(request_line)s\" %(status_code)s"
        access_formatter = AccessFormatter(fmt=access_fmt, datefmt=DATE_FORMAT)
        for handler in access_logger.handlers:
            handler.setFormatter(access_formatter)
    except Exception:
        for handler in access_logger.handlers:
            handler.setFormatter(formatter)

    # 4. Attach polling filter if not already attached
    if not any(isinstance(f, PollingEndpointFilter) for f in access_logger.filters):
        access_logger.addFilter(PollingEndpointFilter())
