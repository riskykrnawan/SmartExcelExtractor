"""Application entry point for the desktop interface.

Jalankan: python main.py  (atau: python -m ui.main)
"""
from __future__ import annotations

import atexit
import sys

from PySide6.QtWidgets import QApplication

from core.logging_config import setup_logging
from ui.main_window import MainWindow
from ui.worker import wait_for_workers


def main() -> int:
    """Start the application; returns the process exit code."""
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("SmartExcelExtractor")
    app.setOrganizationName("SmartExcelExtractor")
    window = MainWindow()
    app.aboutToQuit.connect(wait_for_workers)  # a running thread must never be freed
    atexit.register(wait_for_workers)  # also for exits that skip aboutToQuit
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
