"""Langkah 2: the Sub-folder > Sheet > Field tree with add/edit/duplicate/delete."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)
from pydantic import ValidationError

from core.models import FieldConfig, MatchMode, Profile, SheetConfig, SourceConfig
from core.profiles import format_validation_error, replace_sources
from ui.field_form import REFERENCE_MODE_LABELS, FieldFormDialog, fill_combo
from ui.sample_files import sample_files, sheet_titles


class SheetDialog(QDialog):
    """Ask for a sheet name (auto-filled from the sample file) and match mode."""

    def __init__(self, parent: QWidget | None, titles: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tambah sheet")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nama sheet:"))
        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.addItems(titles)
        layout.addWidget(self.name_combo)
        hint = QLabel(
            "Pilih dari daftar atau ketik nama. Kalau nama sheet sering berubah "
            "(mis. 'Produksi 01-10'), pilih 'Mengandung'."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666666;")
        layout.addWidget(hint)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Cara mencocokkan nama:"))
        self.mode_combo = QComboBox()
        fill_combo(self.mode_combo, REFERENCE_MODE_LABELS)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Tambah")
        buttons.button(QDialogButtonBox.Cancel).setText("Batal")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, MatchMode]:
        """The typed sheet name and its matching mode."""
        return self.name_combo.currentText().strip(), MatchMode(self.mode_combo.currentData())


class StepData(QWizardPage):
    """Wizard page 2: arrange sheets and fields under each checked folder."""

    def __init__(self, get_profile: Callable[[], Profile], on_change: Callable[[], None]) -> None:
        super().__init__()
        self._get_profile = get_profile
        self._on_change = on_change
        self.setTitle("Langkah 2 - Data yang diambil")
        self.setSubTitle("Susun data per folder: sheet lalu data yang mau diambil.")

        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Struktur data"])
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.sheet_button = QPushButton("+ Tambah Sheet")
        self.sheet_button.clicked.connect(self._add_sheet)
        self.field_button = QPushButton("+ Tambah Data")
        self.field_button.clicked.connect(self._add_field)
        self.edit_button = QPushButton("Ubah")
        self.edit_button.clicked.connect(self._edit_field)
        self.duplicate_button = QPushButton("Duplikat")
        self.duplicate_button.clicked.connect(self._duplicate_field)
        self.delete_button = QPushButton("Hapus")
        self.delete_button.clicked.connect(self._delete_selected)
        for button in (
            self.sheet_button,
            self.field_button,
            self.edit_button,
            self.duplicate_button,
            self.delete_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def initializePage(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the tree from the profile (checked sources only)."""
        self.tree.clear()
        profile = self._get_profile()
        style = self.style()
        for source in profile.sources:
            if not source.enabled:
                continue
            src_item = QTreeWidgetItem([source.folder])
            src_item.setData(0, Qt.UserRole, ("source", source.folder))
            src_item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
            self.tree.addTopLevelItem(src_item)
            for sheet in source.sheets:
                sheet_item = QTreeWidgetItem([f"Sheet: {sheet.name}"])
                sheet_item.setData(0, Qt.UserRole, ("sheet", source.folder, sheet.name))
                src_item.addChild(sheet_item)
                for field in sheet.fields:
                    field_item = QTreeWidgetItem(
                        [f"{field.output_name}  -  cari baris: '{field.row_keyword.text}'"]
                    )
                    field_item.setData(
                        0, Qt.UserRole, ("field", source.folder, sheet.name, field.output_name)
                    )
                    sheet_item.addChild(field_item)
            src_item.setExpanded(True)
        self._update_buttons()

    def _selection(self) -> tuple | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def _update_buttons(self) -> None:
        selection = self._selection()
        kind = selection[0] if selection else None
        profile = self._get_profile()
        self.sheet_button.setEnabled(any(source.enabled for source in profile.sources))
        self.field_button.setEnabled(kind == "sheet")
        self.edit_button.setEnabled(kind == "field")
        self.duplicate_button.setEnabled(kind == "field")
        self.delete_button.setEnabled(kind in ("sheet", "field"))

    def _add_sheet(self) -> None:
        profile = self._get_profile()
        folder = self._target_folder(profile)
        if folder is None:
            QMessageBox.information(self, "Tambah sheet", "Pilih dulu satu folder di daftar atas.")
            return
        titles: list[str] = []
        for sample in sample_files(profile):
            if sample.folder == folder:
                titles = sheet_titles(sample)
                break
        dialog = SheetDialog(self, titles)
        accepted = dialog.exec() == QDialog.Accepted
        name, mode = dialog.values()
        dialog.deleteLater()  # Qt owns the teardown; GC-collected dialogs segfault (PySide6)
        if not accepted or not name:
            return
        sources: list[SourceConfig] = []
        for source in profile.sources:
            if source.folder == folder:
                sheets = list(source.sheets) + [SheetConfig(name=name, match_mode=mode)]
                sources.append(source.model_copy(update={"sheets": sheets}))
            else:
                sources.append(source)
        self._apply_sources(sources)

    def _target_folder(self, profile: Profile) -> str | None:
        """The folder a new sheet belongs to: the selection, or the only checked one."""
        selection = self._selection()
        if selection is not None and selection[0] in ("source", "sheet"):
            return str(selection[1])
        enabled = [source.folder for source in profile.sources if source.enabled]
        if len(enabled) == 1:
            return enabled[0]
        return None

    def _add_field(self) -> None:
        selection = self._selection()
        if selection is None or selection[0] != "sheet":
            return
        self._open_field_dialog(str(selection[1]), str(selection[2]), None)

    def _edit_field(self) -> None:
        selection = self._selection()
        if selection is None or selection[0] != "field":
            return
        self._open_field_dialog(str(selection[1]), str(selection[2]), str(selection[3]))

    def _open_field_dialog(self, folder: str, sheet_name: str, output_name: str | None) -> None:
        profile = self._get_profile()
        sheet, field = self._find(profile, folder, sheet_name, output_name)
        if sheet is None:
            return
        dialog = FieldFormDialog(self, profile, folder, sheet, field)
        accepted = dialog.exec() == QDialog.Accepted
        sources = dialog.sources
        dialog.deleteLater()  # Qt owns the teardown; GC-collected dialogs segfault (PySide6)
        if accepted and sources is not None:
            self._apply_sources(sources)

    @staticmethod
    def _find(
        profile: Profile, folder: str, sheet_name: str, output_name: str | None
    ) -> tuple[SheetConfig | None, FieldConfig | None]:
        for source in profile.sources:
            if source.folder != folder:
                continue
            for sheet in source.sheets:
                if sheet.name != sheet_name:
                    continue
                field = None
                if output_name:
                    field = next(
                        (item for item in sheet.fields if item.output_name == output_name), None
                    )
                return sheet, field
        return None, None

    def _duplicate_field(self) -> None:
        selection = self._selection()
        if selection is None or selection[0] != "field":
            return
        folder, sheet_name, output_name = (
            str(selection[1]),
            str(selection[2]),
            str(selection[3]),
        )
        profile = self._get_profile()
        sheet, field = self._find(profile, folder, sheet_name, output_name)
        if sheet is None or field is None:
            return
        name, ok = QInputDialog.getText(
            self, "Duplikat data", "Nama untuk hasil baru:", text=f"{output_name}_salinan"
        )
        if not ok or not name.strip():
            return
        duplicate = field.model_copy(deep=True)
        duplicate.output_name = name.strip()
        sources: list[SourceConfig] = []
        for source in profile.sources:
            if source.folder != folder:
                sources.append(source)
                continue
            sheets: list[SheetConfig] = []
            for config in source.sheets:
                if config.name != sheet_name:
                    sheets.append(config)
                    continue
                fields: list[FieldConfig] = []
                for existing in config.fields:
                    fields.append(existing)
                    if existing.output_name == output_name:
                        fields.append(duplicate)
                sheets.append(config.model_copy(update={"fields": fields}))
            sources.append(source.model_copy(update={"sheets": sheets}))
        self._apply_sources(sources)

    def _delete_selected(self) -> None:
        selection = self._selection()
        if selection is None:
            return
        profile = self._get_profile()
        sources: list[SourceConfig] = []
        if selection[0] == "sheet":
            folder, sheet_name = str(selection[1]), str(selection[2])
            sheet, _field = self._find(profile, folder, sheet_name, None)
            count = len(sheet.fields) if sheet else 0
            answer = QMessageBox.question(
                self,
                "Hapus sheet",
                f"Hapus sheet '{sheet_name}' beserta {count} data di dalamnya?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            for source in profile.sources:
                if source.folder != folder:
                    sources.append(source)
                    continue
                sheets = [item for item in source.sheets if item.name != sheet_name]
                sources.append(source.model_copy(update={"sheets": sheets}))
        elif selection[0] == "field":
            folder, sheet_name, output_name = (
                str(selection[1]),
                str(selection[2]),
                str(selection[3]),
            )
            answer = QMessageBox.question(
                self,
                "Hapus data",
                f"Hapus data '{output_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            for source in profile.sources:
                if source.folder != folder:
                    sources.append(source)
                    continue
                sheets: list[SheetConfig] = []
                for config in source.sheets:
                    if config.name == sheet_name:
                        fields = [
                            item for item in config.fields if item.output_name != output_name
                        ]
                        config = config.model_copy(update={"fields": fields})
                    sheets.append(config)
                sources.append(source.model_copy(update={"sheets": sheets}))
        else:
            return
        self._apply_sources(sources)

    def _apply_sources(self, sources: list[SourceConfig]) -> None:
        """Validate, then store the new source list and refresh the tree."""
        profile = self._get_profile()
        try:
            replace_sources(profile, sources)
        except ValidationError as exc:
            QMessageBox.warning(
                self, "Belum bisa disimpan", "\n".join(format_validation_error(exc))
            )
            return
        profile.sources = sources
        self._on_change()
        self.refresh()
