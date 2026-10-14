"""Live preview pane: value, status, candidates, and the mini-grid snippet."""
from __future__ import annotations

import logging
from collections.abc import Callable

from openpyxl.utils import column_index_from_string, coordinate_to_tuple, range_boundaries
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import FieldConfig, Profile, SheetConfig, SourceConfig
from ui.sample_files import SampleFile, sample_files
from ui.worker import PreviewWorker

logger = logging.getLogger(__name__)

_OK_COLOR = QColor("#2E7D32")
_WARNING_COLOR = QColor("#EF6C00")
_ERROR_COLOR = QColor("#C62828")
_ROW_KEYWORD_BG = QColor("#BBDEFB")  # blue: row keyword cell
_COL_KEYWORD_BG = QColor("#C8E6C9")  # green: column keyword cell
_VALUE_BG = QColor("#FFE0B2")  # orange: value cell (and merged range)

_STATUS_TEXT = {
    "ok": ("&#128994; OK", _OK_COLOR),
    "warning": ("&#128992; Perlu dicek", _WARNING_COLOR),
    "error": ("&#128308; Gagal", _ERROR_COLOR),
}

_DISAMBIGUATION_TEXT = {
    "unique": "karena tulisan ini hanya muncul sekali",
    "by_address": "karena paling dekat ke alamat acuan",
    "near_keyword": "karena paling dekat ke tulisan pembanding",
    "not_near_keyword": "karena tidak dekat dengan tulisan pembanding",
}


class PreviewPane(QWidget):
    """Runs the field currently being edited against a chosen sample file."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile: Profile | None = None
        self._sheet: SheetConfig | None = None
        self._field_provider: Callable[[], FieldConfig | None] | None = None
        self._request_seq = 0
        self._pending = False
        self._worker: PreviewWorker | None = None

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self._start_pending)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("<b>Pratinjau hasil</b>"))

        sample_row = QVBoxLayout()
        sample_row.addWidget(QLabel("File sampel:"))
        self.sample_combo = QComboBox()
        self.sample_combo.currentIndexChanged.connect(self.schedule_refresh)
        sample_row.addWidget(self.sample_combo)
        layout.addLayout(sample_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(self.status_label)
        self.value_label = QLabel("-")
        self.value_label.setWordWrap(True)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value_label.setStyleSheet(
            "background: #F5F5F5; padding: 6px; border: 1px solid #DDDDDD;"
        )
        layout.addWidget(self.value_label)
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.detail_label)
        self.occurrence_label = QLabel("")
        layout.addWidget(self.occurrence_label)

        layout.addWidget(QLabel("Kemunculan dan catatan:"))
        self.candidates_list = QListWidget()
        self.candidates_list.setMaximumHeight(120)
        layout.addWidget(self.candidates_list)

        layout.addWidget(QLabel("Cuplikan sheet (sekitar 5 sel):"))
        self.grid_table = QTableWidget()
        self.grid_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.grid_table.setSelectionMode(QTableWidget.NoSelection)
        self.grid_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.grid_table)

        legend = QLabel(
            '<span style="background-color:#BBDEFB;">&nbsp;&nbsp;&nbsp;</span> tulisan baris'
            '&nbsp; <span style="background-color:#C8E6C9;">&nbsp;&nbsp;&nbsp;</span> tulisan kolom'
            '&nbsp; <span style="background-color:#FFE0B2;">&nbsp;&nbsp;&nbsp;</span> nilai'
        )
        layout.addWidget(legend)
        layout.addStretch(1)
        self._show_placeholder("Pratinjau akan tampil di sini.")

    def set_context(
        self,
        profile: Profile,
        sheet: SheetConfig,
        field_provider: Callable[[], FieldConfig | None],
    ) -> None:
        """Bind the pane to the profile/sheet of the field being edited."""
        self._profile = profile
        self._sheet = sheet
        self._field_provider = field_provider
        self.sample_combo.blockSignals(True)
        self.sample_combo.clear()
        for sample in sample_files(profile):
            self.sample_combo.addItem(sample.label, sample)
        self.sample_combo.blockSignals(False)
        if self.sample_combo.count() == 0:
            self._show_placeholder("Belum ada file sampel. Lengkapi Langkah 1 dulu.")
        else:
            self.schedule_refresh()

    def schedule_refresh(self, *_args: object) -> None:
        """Restart the debounce timer; the newest edit wins."""
        self._debounce.start()

    def _start_pending(self) -> None:
        self._pending = False
        field = self._current_field()
        if field is None:
            self._show_placeholder("Lengkapi dulu bagian form yang masih kosong.")
            return
        sample = self.sample_combo.currentData()
        if not isinstance(sample, SampleFile) or self._sheet is None:
            self._show_placeholder("Belum ada file sampel. Lengkapi Langkah 1 dulu.")
            return
        profile = Profile(
            name="Pratinjau",
            input_root=sample.input_root,
            sources=[
                SourceConfig(
                    folder=sample.folder,
                    sheets=[
                        SheetConfig(
                            name=self._sheet.name,
                            match_mode=self._sheet.match_mode,
                            fields=[field],
                        )
                    ],
                )
            ],
        )
        if self._worker is not None and self._worker.isRunning():
            self._pending = True  # relaunch with the newest edit once this one ends
            return
        self._request_seq += 1
        self._launch(self._request_seq, profile)

    def _current_field(self) -> FieldConfig | None:
        """Ask the form for the current field; None while the form is incomplete."""
        if self._field_provider is None:
            return None
        return self._field_provider()

    def _launch(self, request_id: int, profile: Profile) -> None:
        self._worker = PreviewWorker(request_id, profile)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_finished)
        self.status_label.setText("Membaca file sampel...")
        self.status_label.setStyleSheet("color: #666666; font-size: 15px;")
        self._worker.start()

    def _on_success(self, request_id: int, payload: dict) -> None:
        if request_id != self._request_seq:
            return  # a newer edit superseded this preview
        result = payload["result"]
        entry = next(iter(result["data"].values()), None)
        audit_fields = result["audit"]["fields"]
        audit = audit_fields[0] if audit_fields else None
        if entry is None:
            self._show_placeholder("Hasil pratinjau tidak tersedia.")
            return
        status_text, status_color = _STATUS_TEXT.get(entry["status"], ("-", _ERROR_COLOR))
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(
            f"color: {status_color.name()}; font-size: 15px; font-weight: bold;"
        )
        value = entry["value"]
        self.value_label.setText("(kosong)" if value is None else str(value))
        location = entry["location"]
        parts = []
        if location["value_address"]:
            parts.append(f"Nilai di sel {location['value_address']}")
        if location["row_keyword_address"]:
            parts.append(f"tulisan baris di {location['row_keyword_address']}")
        if location["col_keyword_address"]:
            parts.append(f"tulisan kolom di {location['col_keyword_address']}")
        self.detail_label.setText(" - ".join(parts) if parts else "Tidak ada titik temu.")
        self.occurrence_label.setText(self._occurrence_text(audit))
        self._fill_candidates(audit)
        self._fill_grid(payload.get("grid"))

    def _on_failed(self, request_id: int, message: str) -> None:
        if request_id != self._request_seq:
            return
        self._show_placeholder(message)

    def _on_finished(self) -> None:
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        self._worker = None  # deleteLater() invalidates the wrapper; never touch it again
        if self._pending:
            self._pending = False
            self._debounce.start()

    @staticmethod
    def _occurrence_text(audit: dict | None) -> str:
        if not audit:
            return ""
        parts = []
        for key, label in (("row_keyword", "baris"), ("col_keyword", "kolom")):
            keyword = audit.get(key)
            if keyword:
                parts.append(f"{label}: {len(keyword['candidates'])} kemunculan")
        return "Tulisan " + ", ".join(parts) if parts else ""

    def _fill_candidates(self, audit: dict | None) -> None:
        self.candidates_list.clear()
        if not audit:
            return
        for key, label in (("row_keyword", "Tulisan baris"), ("col_keyword", "Tulisan kolom")):
            keyword = audit.get(key)
            if not keyword:
                continue
            self.candidates_list.addItem(QListWidgetItem(f"- {label}:"))
            for address in keyword["candidates"]:
                suffix = " (dipakai)" if address == keyword["selected"] else ""
                self.candidates_list.addItem(QListWidgetItem(f"    {address}{suffix}"))
            if keyword["selected"]:
                reason = _DISAMBIGUATION_TEXT.get(keyword["disambiguation"] or "", "")
                reference = keyword.get("reference")
                detail = f" {reference}" if reference else ""
                self.candidates_list.addItem(
                    QListWidgetItem(f"    alasan: {reason}{detail}")
                )
        for warning in audit.get("warnings", []):
            self.candidates_list.addItem(QListWidgetItem(f"! {warning}"))
        for error in audit.get("errors", []):
            self.candidates_list.addItem(QListWidgetItem(f"X {error}"))

    def _fill_grid(self, grid: dict | None) -> None:
        self.grid_table.clear()
        if not grid:
            self.grid_table.setRowCount(0)
            self.grid_table.setColumnCount(0)
            return
        rows = grid["rows"]
        col_letters = grid["col_letters"]
        row_numbers = grid["row_numbers"]
        self.grid_table.setRowCount(len(rows))
        self.grid_table.setColumnCount(len(col_letters))
        self.grid_table.setVerticalHeaderLabels([str(n) for n in row_numbers])
        self.grid_table.setHorizontalHeaderLabels(col_letters)
        highlights = self._highlight_map(grid, row_numbers, col_letters)
        merged = self._merged_cells(grid)
        for row_idx, row in enumerate(rows):
            for col_idx, text in enumerate(row):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                background = highlights.get((row_idx, col_idx))
                if (row_numbers[row_idx], col_idx + 1) in merged and background is None:
                    background = _VALUE_BG
                if background is not None:
                    item.setBackground(background)
                self.grid_table.setItem(row_idx, col_idx, item)
        self.grid_table.resizeColumnsToContents()

    @staticmethod
    def _highlight_map(
        grid: dict, row_numbers: list[int], col_letters: list[str]
    ) -> dict[tuple[int, int], QColor]:
        """Map grid positions to colors for the keyword and value cells."""
        first_col = column_index_from_string(col_letters[0]) if col_letters else 1

        def position(address: object) -> tuple[int, int] | None:
            if not isinstance(address, str) or ":" in address or not row_numbers:
                return None
            row, col = coordinate_to_tuple(address)
            col_idx = col - first_col
            if row in row_numbers and 0 <= col_idx < len(col_letters):
                return (row_numbers.index(row), col_idx)
            return None

        result: dict[tuple[int, int], QColor] = {}
        value_pos = position(grid.get("value_address"))
        if value_pos:
            result[value_pos] = _VALUE_BG
        row_pos = position(grid.get("row_keyword"))
        if row_pos and row_pos not in result:
            result[row_pos] = _ROW_KEYWORD_BG
        col_pos = position(grid.get("col_keyword"))
        if col_pos and col_pos not in result:
            result[col_pos] = _COL_KEYWORD_BG
        return result

    @staticmethod
    def _merged_cells(grid: dict) -> set[tuple[int, int]]:
        """All (row, col) inside the merged range of the value cell, if any."""
        merged_range = grid.get("merged_range")
        if not isinstance(merged_range, str) or ":" not in merged_range:
            return set()
        min_col, min_row, max_col, max_row = range_boundaries(merged_range)
        return {
            (row, col)
            for row in range(min_row, max_row + 1)
            for col in range(min_col, max_col + 1)
        }

    def _show_placeholder(self, message: str) -> None:
        self.status_label.setText("")
        self.value_label.setText("-")
        self.detail_label.setText(message)
        self.occurrence_label.setText("")
        self.candidates_list.clear()
        self.grid_table.clear()
        self.grid_table.setRowCount(0)
        self.grid_table.setColumnCount(0)
