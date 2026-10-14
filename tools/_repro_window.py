"""Headless end-to-end check of the real window: build, run, close, exit."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.profiles import save_profile  # noqa: E402
from tests.test_extractor import profile_for  # noqa: E402
from tools.generate_samples import generate  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

root = Path(tempfile.mkdtemp())
generate(root, "a")
profiles = root / "profiles"
save_profile(profile_for(root / "input_a"), directory=profiles)

app = QApplication([])
window = MainWindow(
    profiles_directory=profiles,
    settings_path=root / "settings.json",
    output_dir=root / "output",
)
window.show()
app.processEvents()
window.page_run._run()
worker = window.page_run._worker
assert worker is not None and worker.wait(60_000)
app.processEvents()
print("rows", window.page_run.table.rowCount())
window.close()
app.processEvents()
print("closed")
