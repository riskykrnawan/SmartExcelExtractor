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
from ui.i18n import t
from ui.sample_files import SampleFile, sample_files
from ui.worker import PreviewWorker, start_worker

logger = logging.getLogger(__name__)

_ROW_KEYWORD_BG = QColor("#BBDEFB")  # blue: row keyword cell
_COL_KEYWORD_BG = QColor("#C8E6C9")  # green: column keyword cell
_VALUE_BG = QColor("#FFE0B2")  # orange: value cell (and merged range)
_BOX_BG = QColor("#F5F5F5")  # value box fill
# Every fill above is light, while a dark system theme paints text white; without an explicit
# dark colour the text vanishes into its own background.
_TEXT_ON_LIGHT = QColor("#212121")


def _status_text(status: str) -> tuple[str, QColor, QColor]:
    """Status text, a dark text colour, and a light pill colour (high contrast)."""
    return {
        "ok": (t("pv.status_ok"), _TEXT_ON_LIGHT, QColor("#E8F5E9")),
        "warning": (t("pv.status_warning"), _TEXT_ON_LIGHT, QColor("#FFF3E0")),
        "error": (t("pv.status_error"), _TEXT_ON_LIGHT, QColor("#FFEBEE")),
    }.get(status, ("-", _TEXT_ON_LIGHT, QColor("#FFFFFF")))


def _disambiguation_text(key: str) -> str:
    """The 'because ...' reason for the chosen candidate, in the active language."""
    return {
        "unique": t("pv.dis_unique"),
        "by_address": t("pv.dis_by_address"),
        "near_keyword": t("pv.dis_near"),
        "not_near_keyword": t("pv.dis_not_near"),
    }.get(key, "")


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
        layout.addWidget(QLabel(t("pv.title")))

        sample_row = QVBoxLayout()
        sample_row.addWidget(QLabel(t("pv.label_sample")))
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
            f"color: {_TEXT_ON_LIGHT.name()}; background: {_BOX_BG.name()}; "
            "padding: 6px; border: 1px solid #DDDDDD;"
        )
        layout.addWidget(self.value_label)
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)
        self.occurrence_label = QLabel("")
        layout.addWidget(self.occurrence_label)

        layout.addWidget(QLabel(t("pv.label_notes")))
        self.candidates_list = QListWidget()
        self.candidates_list.setMaximumHeight(120)
        layout.addWidget(self.candidates_list)

        layout.addWidget(QLabel(t("pv.label_grid")))
        self.grid_table = QTableWidget()
        self.grid_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.grid_table.setSelectionMode(QTableWidget.NoSelection)
        self.grid_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.grid_table)

        legend = QLabel(
            '<span style="background-color:#BBDEFB;">&nbsp;&nbsp;&nbsp;</span> '
            + t("pv.legend_row")
            + '&nbsp; <span style="background-color:#C8E6C9;">&nbsp;&nbsp;&nbsp;</span> '
            + t("pv.legend_col")
            + '&nbsp; <span style="background-color:#FFE0B2;">&nbsp;&nbsp;&nbsp;</span> '
            + t("pv.legend_value")
        )
        layout.addWidget(legend)
        layout.addStretch(1)
        self._show_placeholder(t("pv.placeholder_default"))

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
            self._show_placeholder(t("pv.no_sample"))
        else:
            self.schedule_refresh()

    def schedule_refresh(self, *_args: object) -> None:
        """Restart the debounce timer; the newest edit wins."""
        self._debounce.start()

    def _start_pending(self) -> None:
        self._pending = False
        field = self._current_field()
        if field is None:
            self._show_placeholder(t("pv.incomplete"))
            return
        sample = self.sample_combo.currentData()
        if not isinstance(sample, SampleFile) or self._sheet is None:
            self._show_placeholder(t("pv.no_sample"))
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
        self.status_label.setText(t("pv.loading"))
        self.status_label.setStyleSheet("font-size: 15px;")
        start_worker(self._worker)

    def _on_success(self, request_id: int, payload: dict) -> None:
        if request_id != self._request_seq:
            return  # a newer edit superseded this preview
        result = payload["result"]
        entry = next(iter(result["data"].values()), None)
        audit_fields = result["audit"]["fields"]
        audit = audit_fields[0] if audit_fields else None
        if entry is None:
            self._show_placeholder(t("pv.no_result"))
            return
        status_text, text_colour, pill_colour = _status_text(entry["status"])
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(
            f"color: {text_colour.name()}; background: {pill_colour.name()}; "
            "font-size: 15px; font-weight: bold; padding: 2px 6px; border-radius: 4px;"
        )
        value = entry["value"]
        self.value_label.setText(t("pv.value_empty") if value is None else str(value))
        location = entry["location"]
        parts = []
        if location["value_address"]:
            parts.append(t("pv.detail_value", address=location["value_address"]))
        if location["row_keyword_address"]:
            parts.append(t("pv.detail_row", address=location["row_keyword_address"]))
        if location["col_keyword_address"]:
            parts.append(t("pv.detail_col", address=location["col_keyword_address"]))
        self.detail_label.setText(" - ".join(parts) if parts else t("pv.no_match"))
        self.occurrence_label.setText(self._occurrence_text(audit))
        self._fill_candidates(audit)
        self._fill_grid(payload.get("grid"))

    def _on_failed(self, request_id: int, message: str) -> None:
        if request_id != self._request_seq:
            return
        self._show_placeholder(message)

    def _on_finished(self) -> None:
        self._worker = None  # start_worker() owns the thread until it has stopped
        if self._pending:
            self._pending = False
            self._debounce.start()

    @staticmethod
    def _occurrence_text(audit: dict | None) -> str:
        if not audit:
            return ""
        parts = []
        for key, label in (("row_keyword", "pv.occ_row"), ("col_keyword", "pv.occ_col")):
            keyword = audit.get(key)
            if keyword:
                parts.append(f"{t(label)}: {t('pv.occ_count', count=len(keyword['candidates']))}")
        return t("pv.occ_prefix") + ", ".join(parts) if parts else ""

    def _fill_candidates(self, audit: dict | None) -> None:
        self.candidates_list.clear()
        if not audit:
            return
        for key, label in (("row_keyword", "pv.cand_row"), ("col_keyword", "pv.cand_col")):
            keyword = audit.get(key)
            if not keyword:
                continue
            self.candidates_list.addItem(QListWidgetItem(f"- {t(label)}:"))
            for address in keyword["candidates"]:
                suffix = t("pv.cand_used") if address == keyword["selected"] else ""
                self.candidates_list.addItem(QListWidgetItem(f"    {address}{suffix}"))
            if keyword["selected"]:
                reason = _disambiguation_text(keyword["disambiguation"] or "")
                reference = keyword.get("reference")
                detail = f" {reference}" if reference else ""
                self.candidates_list.addItem(
                    QListWidgetItem(f"    {t('pv.cand_reason')}{reason}{detail}")
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
                merged_cell = (
                    row_numbers[row_idx],
                    column_index_from_string(col_letters[col_idx]),
                ) in merged
                if merged_cell and background is None:
                    background = _VALUE_BG
                if background is not None:
                    item.setBackground(background)
                    item.setForeground(_TEXT_ON_LIGHT)
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
