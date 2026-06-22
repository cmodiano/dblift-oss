"""Formatters for log messages."""

from core.logger.formatters.factory import OutputFormatterFactory
from core.logger.formatters.formatter import OutputFormatter

# from .textformatter import TextFormatter  # Removed, as TextFormatter is in log.py

# Import formatters with fallbacks
try:
    from core.logger.formatters.htmlformatter import HtmlFormatter

    JINJA_AVAILABLE = True
except ImportError:
    JINJA_AVAILABLE = False
    HtmlFormatter = None  # type: ignore

try:
    from core.logger.formatters.jsonformatter import JsonFormatter

    JSON_AVAILABLE = True
except ImportError:
    JSON_AVAILABLE = False
    JsonFormatter = None  # type: ignore

__all__ = [
    "OutputFormatter",
    "OutputFormatterFactory",
    "HtmlFormatter",
    "JsonFormatter",
]
