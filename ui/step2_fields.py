"""Langkah 2: the Sub-folder > Sheet > Field tree with add/edit/duplicate/delete."""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDropEvent
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

from core.extractor import sheet_matches
from core.models import FieldConfig, MatchMode, Profile, SheetConfig, SourceConfig
from core.profiles import format_validation_error, replace_sources
from ui.field_form import FieldFormDialog, fill_combo, reference_mode_labels
from ui.i18n import t
from ui.sample_files import SampleFile, sample_files, sheet_titles


#: Sheet rows whose sheet is not in the sample file yet (see refresh()).
_MISSING_SHEET_COLOUR = QColor("#C62828")

T = TypeVar("T")


def _moved(items: list[T], moved: int, target: int, below: bool) -> list[T]:
    """A copy of `items` with the entry at `moved` placed just before/after `target`."""
    entry = items[moved]
    rest = [item for index, item in enumerate(items) if index != moved]
    index = target + (1 if below else 0)
    if moved < index:
        index -= 1
    rest.insert(index, entry)
    return rest


def _index_of(names: list[str], key: str) -> int | None:
    """The first index of `key`, or None when the tree and the profile disagree."""
    return names.index(key) if key in names else None


class SheetDialog(QDialog):
    """Ask for a sheet name (auto-filled from the sample file) and match mode."""

    def __init__(self, parent: QWidget | None, titles: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("sd.title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("sd.label_name")))
        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.addItems(titles)
        layout.addWidget(self.name_combo)
        hint = QLabel(t("sd.hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666666;")
        layout.addWidget(hint)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(t("sd.label_match")))
        self.mode_combo = QComboBox()
        fill_combo(self.mode_combo, reference_mode_labels())
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("sd.btn_add"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("sd.btn_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, MatchMode]:
        """The typed sheet name and its matching mode."""
        return self.name_combo.currentText().strip(), MatchMode(self.mode_combo.currentData())


class OrderTree(QTreeWidget):
    """Tree where a sheet or a field can be dragged to a new place.

    The drop is only reported to the page; Qt never moves rows itself, so an illegal
    drop (a field onto another sheet, a sheet onto another folder) changes nothing.
    """

    def __init__(self, on_move: Callable[[tuple, tuple, bool], None]) -> None:
        super().__init__()
        self._on_move = on_move
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt method name
        """Report the gesture as (dragged row, drop target, dropped below it?)."""
        event.ignore()
        dragged = self.currentItem()
        target = self.itemAt(event.position().toPoint()) if dragged is not None else None
        if dragged is None or target is None or dragged is target:
            return
        below = self.dropIndicatorPosition() in (
            QAbstractItemView.BelowItem,
            QAbstractItemView.OnItem,
        )
        self._on_move(dragged.data(0, Qt.UserRole), target.data(0, Qt.UserRole), below)


class StepData(QWizardPage):
    """Wizard page 2: arrange sheets and fields under each checked folder."""

    def __init__(self, get_profile: Callable[[], Profile], on_change: Callable[[], None]) -> None:
        super().__init__()
        self._get_profile = get_profile
        self._on_change = on_change

        layout = QVBoxLayout(self)
        self.tree = OrderTree(self._reorder)
        self._reveal: tuple | None = None  # the row to open and select after the next rebuild
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.sheet_button = QPushButton()
        self.sheet_button.clicked.connect(self._add_sheet)
        self.field_button = QPushButton()
        self.field_button.clicked.connect(self._add_field)
        self.edit_button = QPushButton()
        self.edit_button.clicked.connect(self._edit_field)
        self.duplicate_button = QPushButton()
        self.duplicate_button.clicked.connect(self._duplicate_selected)
        self.delete_button = QPushButton()
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
        self._apply_texts()

    def _apply_texts(self) -> None:
        """Set the static widget texts in the active language."""
        self.setTitle(t("s2.title"))
        self.setSubTitle(t("s2.subtitle"))
        self.tree.setHeaderLabels([t("s2.tree_header")])
        self.sheet_button.setText(t("s2.btn_add_sheet"))
        self.field_button.setText(t("s2.btn_add_field"))
        self.edit_button.setText(t("s2.btn_edit"))
        self.duplicate_button.setText(t("s2.btn_duplicate"))
        self.delete_button.setText(t("s2.btn_delete"))

    def retranslate(self) -> None:
        """Re-apply texts and rebuild the tree after a language change."""
        self._apply_texts()
        self.refresh()

    def initializePage(self) -> None:
        self.refresh()

    def _open_rows(self) -> dict[tuple, bool]:
        """Which rows are open, keyed the same way as the row data."""
        state: dict[tuple, bool] = {}
        stack = [self.tree.topLevelItem(index) for index in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            state[item.data(0, Qt.UserRole)] = item.isExpanded()
            stack.extend(item.child(index) for index in range(item.childCount()))
        return state

    def refresh(self) -> None:
        """Rebuild the tree from the profile (checked sources only).

        Rows are rebuilt from scratch, so which rows were open and which one was selected
        are read first and put back afterwards: without that, every single change collapsed
        the sheet the user was working in. `self._reveal` (the row the user just touched)
        wins over the remembered selection, so a row that was just added is always in view.
        """
        open_rows = self._open_rows()
        selected = self._reveal or self._selection()
        self._reveal = None
        self.tree.clear()
        rows: dict[tuple, QTreeWidgetItem] = {}
        profile = self._get_profile()
        style = self.style()
        for source in profile.sources:
            if not source.enabled:
                continue
            sample = self._sample_for(profile, source.folder)
            titles = sheet_titles(sample) if sample is not None else []
            sample_name = sample.path.name if sample is not None else ""
            folder_key = ("source", source.folder)
            src_item = QTreeWidgetItem([source.folder])
            src_item.setFlags(src_item.flags() & ~Qt.ItemIsDragEnabled)  # a folder stays put
            src_item.setData(0, Qt.UserRole, folder_key)
            src_item.setIcon(0, style.standardIcon(QStyle.SP_DirIcon))
            self.tree.addTopLevelItem(src_item)
            rows[folder_key] = src_item
            for sheet in source.sheets:
                sheet_key = ("sheet", source.folder, sheet.name)
                sheet_item = QTreeWidgetItem([t("s2.sheet_prefix", name=sheet.name)])
                sheet_item.setData(0, Qt.UserRole, sheet_key)
                if titles and not any(sheet_matches(title, sheet) for title in titles):
                    # Not an error, just "the data is not there yet" (SPEC v2 poin 2):
                    # the row goes red so the user sees it without reading the notes.
                    sheet_item.setForeground(0, _MISSING_SHEET_COLOUR)
                    sheet_item.setToolTip(
                        0, t("s2.sheet_missing", name=sheet.name, file=sample_name)
                    )
                src_item.addChild(sheet_item)
                rows[sheet_key] = sheet_item
                for field in sheet.fields:
                    field_key = ("field", source.folder, sheet.name, field.output_name)
                    field_item = QTreeWidgetItem(
                        [t("s2.field_row", name=field.output_name, text=field.row_keyword.text)]
                    )
                    field_item.setData(0, Qt.UserRole, field_key)
                    sheet_item.addChild(field_item)
                    rows[field_key] = field_item
        for key, item in rows.items():  # after the build: Qt ignores this before children exist
            if item.childCount():
                item.setExpanded(open_rows.get(key, key[0] == "source"))
        row = rows.get(selected) if selected is not None else None
        if row is not None:
            row.setExpanded(True)  # the touched row itself (a sheet row); a field row has none
            parent = row.parent()
            while parent is not None:  # the touched row must be visible, not folded away
                parent.setExpanded(True)
                parent = parent.parent()
            self.tree.setCurrentItem(row)
            row.setSelected(True)
        self._update_buttons()

    def _reorder(self, dragged: tuple, target: tuple, below: bool) -> None:
        """Move a dragged sheet or field to the drop position.

        A sheet only moves between the sheets of its own folder and a field only inside
        its own sheet; any other drop is ignored. The order is what the results follow
        (the rows of the result table and the JSON keys). Dropping on the folder/sheet
        row itself means "put it last".
        """
        if not dragged or not target:
            return
        profile = self._get_profile()
        if dragged[0] == "sheet" and target[0] in ("sheet", "source"):
            folder = str(dragged[1])
            if target[1] != dragged[1]:
                return
            for source in profile.sources:
                if source.folder != folder:
                    continue
                names = [sheet.name for sheet in source.sheets]
                last = len(names) - 1
                moved = _index_of(names, str(dragged[2]))
                dropped_on_parent = target[0] == "source"
                landing = last if dropped_on_parent else _index_of(names, str(target[2]))
                if moved is None or landing is None:
                    return  # duplicate names in the profile; the tree cannot tell them apart
                sheets = _moved(
                    list(source.sheets), moved, landing, below or dropped_on_parent
                )
                self._apply_sources(
                    [
                        item.model_copy(update={"sheets": sheets})
                        if item.folder == folder
                        else item
                        for item in profile.sources
                    ]
                )
                return
        same_place = dragged[1:3] == target[1:3]
        if dragged[0] == "field" and target[0] in ("field", "sheet") and same_place:
            folder, sheet_name = str(dragged[1]), str(dragged[2])
            sheet, _field = self._find(profile, folder, sheet_name, None)
            if sheet is None:
                return
            names = [field.output_name for field in sheet.fields]
            last = len(names) - 1
            moved = _index_of(names, str(dragged[3]))
            dropped_on_parent = target[0] == "sheet"
            landing = last if dropped_on_parent else _index_of(names, str(target[3]))
            if moved is None or landing is None:
                return
            fields = _moved(list(sheet.fields), moved, landing, below or dropped_on_parent)
            sources: list[SourceConfig] = []
            for source in profile.sources:
                if source.folder != folder:
                    sources.append(source)
                    continue
                sheets = [
                    item.model_copy(update={"fields": fields}) if item.name == sheet_name else item
                    for item in source.sheets
                ]
                sources.append(source.model_copy(update={"sheets": sheets}))
            self._apply_sources(sources)

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
        self.duplicate_button.setEnabled(kind in ("field", "sheet"))  # a sheet copies all its fields
        self.delete_button.setEnabled(kind in ("sheet", "field"))

    def _add_sheet(self) -> None:
        profile = self._get_profile()
        folder = self._target_folder(profile)
        if folder is None:
            QMessageBox.information(self, t("s2.info_add_sheet_title"), t("s2.info_pick_folder"))
            return
        dialog = SheetDialog(self, self._sheet_titles(profile, folder))
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
        self._reveal = ("sheet", folder, name)  # the new sheet must be in view
        self._apply_sources(sources)

    @staticmethod
    def _sample_for(profile: Profile, folder: str) -> SampleFile | None:
        """The newest sample file of `folder` (None when the folder has no Excel file)."""
        for sample in sample_files(profile):
            if sample.folder == folder:
                return sample
        return None

    @staticmethod
    def _sheet_titles(profile: Profile, folder: str) -> list[str]:
        """Sheet names of the newest sample file in `folder` (empty when there is none)."""
        sample = StepData._sample_for(profile, folder)
        return sheet_titles(sample) if sample is not None else []

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
            self._reveal = ("sheet", folder, sheet_name)  # keep the sheet open and selected
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

    def _duplicate_selected(self) -> None:
        """The Duplicate button: a field copies its rules, a sheet copies all of its fields."""
        selection = self._selection()
        if selection is not None and selection[0] == "sheet":
            self._duplicate_sheet(str(selection[1]), str(selection[2]))
            return
        self._duplicate_field()

    def _duplicate_sheet(self, folder: str, sheet_name: str) -> None:
        """Copy every field of a sheet to a new sheet: same rules, same result names.

        The daily-report case: one sheet per date, so only the sheet name changes and the
        rules are reused (a result name only has to be unique within one sheet).
        """
        profile = self._get_profile()
        sheet, _field = self._find(profile, folder, sheet_name, None)
        if sheet is None:
            return
        dialog = SheetDialog(self, self._sheet_titles(profile, folder))
        accepted = dialog.exec() == QDialog.Accepted
        name, mode = dialog.values()
        dialog.deleteLater()  # Qt owns the teardown; GC-collected dialogs segfault (PySide6)
        if not accepted or not name:
            return
        fields: list[FieldConfig] = [field.model_copy(deep=True) for field in sheet.fields]
        sources: list[SourceConfig] = []
        for source in profile.sources:
            if source.folder != folder:
                sources.append(source)
                continue
            sheets = list(source.sheets) + [SheetConfig(name=name, match_mode=mode, fields=fields)]
            sources.append(source.model_copy(update={"sheets": sheets}))
        self._reveal = ("sheet", folder, name)  # the copy must be in view
        self._apply_sources(sources)

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
            self,
            t("s2.dup_title"),
            t("s2.dup_prompt"),
            text=t("s2.dup_default", name=output_name),
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
        self._reveal = ("field", folder, sheet_name, duplicate.output_name)  # in view
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
                t("s2.delete_sheet_title"),
                t("s2.delete_sheet_question", name=sheet_name, count=count),
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
                t("s2.delete_field_title"),
                t("s2.delete_field_question", name=output_name),
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
                self, t("s2.err_save"), "\n".join(format_validation_error(exc))
            )
            return
        profile.sources = sources
        self._on_change()
        self.refresh()
