"""Resolve where the application keeps its data folders (profiles, output, logs)."""
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """Return the folder beside the application.

    When frozen by PyInstaller use the executable's folder, otherwise the project root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
