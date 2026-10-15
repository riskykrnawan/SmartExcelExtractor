"""Langkah 3: run the extraction, inspect the result, save a copy of the JSON."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
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

from core.audit import IssueCode, RunResult
from core.models import Profile
from ui.i18n import t
from ui.worker import RunWorker, start_worker


def _status_label(status: str) -> tuple[str, QColor, QColor]:
    """Status label, a dark text colour, and a light row colour (high contrast)."""
    text_colour = QColor("#212121")  # near-black: readable on every light row colour
    return {
        "ok": (t("s3.status_ok"), text_colour, QColor("#E8F5E9")),
        "warning": (t("s3.status_warning"), text_colour, QColor("#FFF3E0")),
        "error": (t("s3.status_error"), text_colour, QColor("#FFEBEE")),
    }.get(status, (t("s3.status_unknown"), text_colour, QColor("#FFFFFF")))


def _columns() -> list[str]:
    """Result table headers, in the active language."""
    return [
        t("s3.col_name"),
        t("s3.col_value"),
        t("s3.col_status"),
        t("s3.col_file"),
        t("s3.col_sheet"),
        t("s3.col_address"),
    ]


class StepRun(QWizardPage):
    """Wizard page 3: run the extraction and review every result."""

    def __init__(self, get_profile: Callable[[], Profile], output_dir: Path) -> None:
        super().__init__()
        self._get_profile = get_profile
        self._output_dir = output_dir
        self._worker: RunWorker | None = None
        self._result: RunResult | None = None
        self._result_path: Path | None = None

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        top.addWidget(self.run_button)
        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)  # indeterminate while the files are read
        self.busy_bar.setVisible(False)
        top.addWidget(self.busy_bar, 1)
        self.save_button = QPushButton()
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_copy)
        top.addWidget(self.save_button)
        layout.addLayout(top)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(_columns()))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 3)

        self.issues_label = QLabel()
        layout.addWidget(self.issues_label)
        self.issues_list = QListWidget()
        layout.addWidget(self.issues_list, 2)

        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.path_label)
        self._apply_texts()

    def _apply_texts(self) -> None:
        """Set the static widget texts and table headers in the active language."""
        self.setTitle(t("s3.title"))
        self.setSubTitle(t("s3.subtitle"))
        self.run_button.setText(t("s3.btn_run"))
        self.save_button.setText(t("s3.btn_save"))
        self.issues_label.setText(t("s3.label_issues"))
        self.table.setHorizontalHeaderLabels(_columns())
        if self._result is None:
            self.summary_label.setText(t("s3.summary_empty"))

    def retranslate(self) -> None:
        """Re-apply texts (and refill the table) after a language change."""
        self._apply_texts()
        if self._result is not None:
            self._fill(self._result)

    def _run(self) -> None:
        profile = self._get_profile()
        if not profile.input_root:
            QMessageBox.warning(self, t("s3.err_no_root_title"), t("s3.err_no_root"))
            return
        enabled = [source for source in profile.sources if source.enabled]
        if not enabled:
            QMessageBox.warning(self, t("s3.err_no_root_title"), t("s3.err_no_sources"))
            return
        field_count = sum(len(sheet.fields) for source in enabled for sheet in source.sheets)
        if field_count == 0:
            QMessageBox.warning(self, t("s3.err_no_root_title"), t("s3.err_no_fields"))
            return
        self.table.setRowCount(0)
        self.issues_list.clear()
        self.path_label.setText("")
        self.summary_label.setText(
            t("s3.reading", fields=field_count, folders=len(enabled))
        )
        self.run_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.busy_bar.setVisible(True)
        self._worker = RunWorker(profile, self._output_dir)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        start_worker(self._worker)

    def _on_worker_finished(self) -> None:
        """Let go of the finished job; start_worker() releases the thread once it stops."""
        self._worker = None

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
        self.path_label.setText(t("s3.saved_path", path=self._result_path))
        self.save_button.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.busy_bar.setVisible(False)
        self.run_button.setEnabled(True)
        self.summary_label.setText(t("s3.failed_summary"))
        QMessageBox.critical(self, t("s3.failed_title"), message)

    def _fill(self, result: RunResult) -> None:
        summary = result.summary
        self.summary_label.setText(
            t(
                "s3.summary_result",
                total=summary["total_fields"],
                ok=summary["ok"],
                warning=summary["warning"],
                error=summary["error"],
            )
        )
        # Same grouping as the JSON file: folder (with its file) first, then sheet,
        # then the fields. Per items, not result.data: a result name may repeat.
        rows = self._grouped_rows(result)
        self.table.clearSpans()
        self.table.setRowCount(len(rows))
        for row, (kind, text, entry) in enumerate(rows):
            if entry is None:
                self._fill_group_row(row, kind, text)
                continue
            label, text_colour, colour = _status_label(entry["status"])
            source = entry["source"]
            location = entry["location"]
            value = entry["value"]
            cells = [
                text,
                t("s3.value_empty") if value is None else str(value),
                label,
                source.get("file") or t("s3.source_none"),
                source.get("sheet") or "-",
                location.get("value_address") or "-",
            ]
            for column, cell in enumerate(cells):
                item = QTableWidgetItem(cell)
                item.setBackground(colour)
                item.setForeground(text_colour)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.issues_list.clear()
        # SHEET_ABSENT stays in the audit (CLI prints it); the red sheet rows in
        # step 2 already tell the user the sheet is not there yet.
        issues = [
            issue
            for issue in result.audit.get("issues", [])
            if issue.get("code") != IssueCode.SHEET_ABSENT.value
        ]
        for issue in sorted(issues, key=lambda item: item.get("level") != "error"):
            level = t("s3.level_error") if issue.get("level") == "error" else t("s3.level_warning")
            self.issues_list.addItem(
                f"[{level}] {issue.get('field') or t('s3.issue_general')}: {issue.get('message')}"
            )
        if not issues:
            self.issues_list.addItem(t("s3.no_issues"))

    @staticmethod
    def _grouped_rows(result: RunResult) -> list[tuple[str, str, dict | None]]:
        """Flat row list: group rows (entry None) and one row per field."""
        rows: list[tuple[str, str, dict | None]] = []
        folder_key: tuple[str, str] | None = None
        sheet_key: tuple[str, str, str] | None = None
        for item in result.items:
            item_folder = (item.folder or "", item.file or "")
            item_sheet = (*item_folder, item.sheet)
            if item_folder != folder_key:
                folder_key = item_folder
                sheet_key = None
                text = (
                    t(
                        "s3.group_folder_file",
                        folder=item.folder or t("s3.source_none"),
                        file=item.file,
                    )
                    if item.file
                    else t("s3.group_folder", folder=item.folder or t("s3.source_none"))
                )
                rows.append(("folder", text, None))
            if item_sheet != sheet_key:
                sheet_key = item_sheet
                rows.append(("sheet", t("s3.group_sheet", sheet=item.sheet), None))
            rows.extend(("field", name, field.to_dict()) for name, field in item.fields.items())
        return rows

    def _fill_group_row(self, row: int, kind: str, text: str) -> None:
        """One spanning header row: the folder (and its file), then the sheet."""
        item = QTableWidgetItem(text)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setBackground(QColor("#E0E0E0" if kind == "folder" else "#EEEEEE"))
        item.setForeground(QColor("#212121"))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, item)
        self.table.setSpan(row, 0, 1, self.table.columnCount())

    def _save_copy(self) -> None:
        if self._result_path is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            t("s3.save_title"),
            str(self._output_dir / self._result_path.name),
            t("s3.json_filter"),
        )
        if not target:
            return
        try:
            shutil.copyfile(self._result_path, target)
        except OSError as exc:
            QMessageBox.warning(
                self, t("s3.save_failed_title"), t("s3.save_failed", error=exc.strerror or exc)
            )
            return
        self.path_label.setText(t("s3.copy_saved", path=target))
