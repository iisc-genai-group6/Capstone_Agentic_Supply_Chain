"""Core application infrastructure: config, DI, logging, lifecycle."""

from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.logging import setup_logging

__all__ = ["Container", "Settings", "get_settings", "setup_logging"]
