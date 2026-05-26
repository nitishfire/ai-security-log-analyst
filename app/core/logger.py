"""
Structured logging setup using loguru.

- Development:  colourised human-readable output on stdout.
- Production:   JSON-serialised output on stdout + rotating file sink.

Usage:
    from app.core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Hello {name}", name="world")
"""

import sys
from pathlib import Path

from loguru import logger as _loguru_logger

from app.core.config import get_settings

_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "app.log"
_CONFIGURED = False


def _configure_logger() -> None:
    """Set up loguru sinks (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    log_level = settings.log_level.upper()
    is_production = log_level not in ("DEBUG", "TRACE")

    # Remove default handler added by loguru
    _loguru_logger.remove()

    # Wrap stdout with UTF-8 encoding to handle emoji / unicode on Windows
    import io  # noqa: PLC0415
    safe_stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding="utf-8",
        errors="replace",
        line_buffering=True,
    ) if hasattr(sys.stdout, "buffer") else sys.stdout

    if is_production:
        # JSON structured output to stdout
        _loguru_logger.add(
            safe_stdout,
            level=log_level,
            serialize=True,  # JSON format
            backtrace=False,
            diagnose=False,
        )
    else:
        # Human-readable coloured output for development
        _loguru_logger.add(
            safe_stdout,
            level=log_level,
            colorize=False,  # disable colour codes that can corrupt non-ANSI terminals
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | "
                "{level: <8} | "
                "{name}:{function}:{line} | "
                "{message}"
            ),
            backtrace=True,
            diagnose=True,
        )

    # Always add a rotating file sink regardless of environment
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _loguru_logger.add(
        str(_LOG_FILE),
        level=log_level,
        serialize=True,  # JSON in file for easy parsing
        rotation="10 MB",
        retention=5,
        compression="zip",
        backtrace=True,
        diagnose=False,
        enqueue=True,  # thread-safe async writing
    )

    _CONFIGURED = True


def get_logger(name: str):
    """Return a loguru logger bound to *name* (module path)."""
    _configure_logger()
    return _loguru_logger.bind(module=name)


# Module-level convenience logger
_configure_logger()
logger = _loguru_logger
