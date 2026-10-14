"""Start the real entry-point flow, quit after 1.5s, and report the exit code."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.logging_config import setup_logging  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

setup_logging()
app = QApplication([])
window = MainWindow()
window.show()
QTimer.singleShot(1500, app.quit)
print("exec code", app.exec())
