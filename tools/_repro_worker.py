"""Throwaway repro: does finishing a RunWorker crash under offscreen Qt?"""
from __future__ import annotations

import gc
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.test_extractor import profile_for  # noqa: E402
from tools.generate_samples import generate  # noqa: E402
from ui.worker import RunWorker  # noqa: E402

app = QApplication([])
root = Path(tempfile.mkdtemp())
generate(root, "a")
profile = profile_for(root / "input_a")
out = root / "output"

worker = RunWorker(profile, out)
worker.succeeded.connect(lambda result, path: print("ok", len(result.data), path))
if os.environ.get("DELETE_LATER") == "1":
    worker.finished.connect(worker.deleteLater)
worker.start()
print("wait", worker.wait(60000))
app.processEvents()
print("after events")
del worker
gc.collect()
print("exiting")
