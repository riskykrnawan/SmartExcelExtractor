"""File logging. Stack traces go to the log file, never to the user interface."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import app_dir

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> Path:
    """Configure the rotating log file `logs/app.log` and return its path.

    Idempotent: calling again reuses the existing handler.
    """
    log_dir = app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    for handler in logging.getLogger().handlers:
        if isinstance(handler, RotatingFileHandler):
            if Path(handler.baseFilename) == log_path.resolve():
                return log_path
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    return log_path
