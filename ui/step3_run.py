"""Langkah 3: run the extraction, inspect the result, save a copy of the JSON."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWizardPage,
)

from core.audit import RunResult
from core.models import Profile
from ui.worker import RunWorker

#: Status in plain Indonesian plus the colour of the table row.
STATUS_LABELS = {
    "ok": ("Berhasil", QColor("#E8F5E9")),
    "warning": ("Perlu dicek", QColor("#FFF3E0")),
    "error": ("Gagal", QColor("#FFEBEE")),
}

COLUMNS = ["Nama data", "Nilai", "Status", "File", "Sheet", "Alamat nilai"]


class StepRun(QWizardPage):
    """Wizard page 3: run the extraction and review every result."""

    def __init__(self, get_profile: Callable[[], Profile], output_dir: Path) -> None:
        super().__init__()
        self._get_profile = get_profile
        self._output_dir = output_dir
        self._worker: RunWorker | None = None
        self._result: RunResult | None = None
        self._result_path: Path | None = None
        self.setTitle("Langkah 3 - Jalankan dan periksa")
        self.setSubTitle("Tekan 'Jalankan Ekstraksi', lalu periksa hasil tiap data.")

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.run_button = QPushButton("Jalankan Ekstraksi")
        self.run_button.clicked.connect(self._run)
        top.addWidget(self.run_button)
        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)  # indeterminate while the files are read
        self.busy_bar.setVisible(False)
        top.addWidget(self.busy_bar, 1)
        self.save_button = QPushButton("Simpan Salinan JSON...")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_copy)
        top.addWidget(self.save_button)
        layout.addLayout(top)

        self.summary_label = QLabel("Belum ada hasil. Tekan 'Jalankan Ekstraksi' untuk mulai.")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 3)

        layout.addWidget(QLabel("Catatan pemeriksaan:"))
        self.issues_list = QListWidget()
        layout.addWidget(self.issues_list, 2)

        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.path_label)

    def _run(self) -> None:
        profile = self._get_profile()
        if not profile.input_root:
            QMessageBox.warning(
                self, "Belum bisa dijalankan", "Folder induk belum diatur (Langkah 1)."
            )
            return
        enabled = [source for source in profile.sources if source.enabled]
        if not enabled:
            QMessageBox.warning(
                self, "Belum bisa dijalankan", "Belum ada sub-folder yang dicentang (Langkah 1)."
            )
            return
        field_count = sum(len(sheet.fields) for source in enabled for sheet in source.sheets)
        if field_count == 0:
            QMessageBox.warning(
                self, "Belum bisa dijalankan", "Belum ada data yang diatur (Langkah 2)."
            )
            return
        self.table.setRowCount(0)
        self.issues_list.clear()
        self.path_label.setText("")
        self.summary_label.setText(
            f"Sedang membaca {field_count} data dari {len(enabled)} folder..."
        )
        self.run_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.busy_bar.setVisible(True)
        self._worker = RunWorker(profile, self._output_dir)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self) -> None:
        """Drop the finished thread; deleteLater() invalidates the wrapper we hold."""
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()

    def stop(self) -> None:
        """Wait briefly for a running job so closing the window stays safe."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(10_000)

    def _on_succeeded(self, result: object, path: str) -> None:
        self.busy_bar.setVisible(False)
        self.run_button.setEnabled(True)
        if not isinstance(result, RunResult):  # defensive: the signal carries a plain object
            return
        self._result = result
        self._result_path = Path(path)
        self._fill(result)
        self.path_label.setText(f"Hasil tersimpan: {self._result_path}")
        self.save_button.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.busy_bar.setVisible(False)
        self.run_button.setEnabled(True)
        self.summary_label.setText("Ekstraksi gagal. Coba jalankan lagi, atau lihat file log.")
        QMessageBox.critical(self, "Ekstraksi gagal", message)

    def _fill(self, result: RunResult) -> None:
        summary = result.summary
        self.summary_label.setText(
            f"{summary['total_fields']} data: {summary['ok']} berhasil, "
            f"{summary['warning']} perlu dicek, {summary['error']} gagal."
        )
        entries = list(result.data.items())
        self.table.setRowCount(len(entries))
        for row, (name, entry) in enumerate(entries):
            label, colour = STATUS_LABELS.get(
                entry["status"], ("Tidak diketahui", QColor("#FFFFFF"))
            )
            source = entry["source"]
            location = entry["location"]
            value = entry["value"]
            cells = [
                name,
                "(kosong)" if value is None else str(value),
                label,
                source.get("file") or "(tidak ada)",
                source.get("sheet") or "-",
                location.get("value_address") or "-",
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(colour)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.issues_list.clear()
        issues = result.audit.get("issues", [])
        for issue in sorted(issues, key=lambda item: item.get("level") != "error"):
            level = "GAGAL" if issue.get("level") == "error" else "PERINGATAN"
            self.issues_list.addItem(
                f"[{level}] {issue.get('field') or '(umum)'}: {issue.get('message')}"
            )
        if not issues:
            self.issues_list.addItem("Tidak ada catatan. Semua data terbaca.")

    def _save_copy(self) -> None:
        if self._result_path is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan salinan hasil",
            str(self._output_dir / self._result_path.name),
            "File JSON (*.json)",
        )
        if not target:
            return
        try:
            shutil.copyfile(self._result_path, target)
        except OSError as exc:
            QMessageBox.warning(
                self, "Gagal menyimpan", f"Salinan tidak bisa disimpan: {exc.strerror or exc}"
            )
            return
        self.path_label.setText(f"Salinan disimpan: {target}")
