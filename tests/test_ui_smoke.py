"""Smoke test: the window builds, the wizard mirrors the profile, a run shows results."""
from __future__ import annotations

import gc
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="antarmuka memerlukan PySide6")

from PySide6.QtCore import QMimeData, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QDropEvent, QPalette  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
)

from core.profiles import save_profile  # noqa: E402
from tests.test_extractor import profile_for  # noqa: E402
from ui.field_form import HIDDEN_MODE_INDEX, FieldFormDialog  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.preview import _BOX_BG, _TEXT_ON_LIGHT, PreviewPane  # noqa: E402
from ui.step2_fields import SheetDialog, _free_output_name  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    """One Qt application for this module; offscreen, so no window pops up."""
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(app: QApplication, input_a: Path, tmp_path: Path) -> Iterator[MainWindow]:
    """A window whose only profile points at the generated sample folder."""
    profiles = tmp_path / "profiles"
    save_profile(profile_for(input_a), directory=profiles)
    window = MainWindow(
        profiles_directory=profiles,
        settings_path=tmp_path / "settings.json",
        output_dir=tmp_path / "output",
    )
    yield window
    window.close()
    window.deleteLater()
    app.processEvents()


def field_dialog(window: MainWindow) -> FieldFormDialog:
    """The '+ Tambah Data' form for the first sheet in the tree."""
    page = window.page_fields
    _kind, folder, sheet_name = page.tree.topLevelItem(0).child(0).data(0, Qt.UserRole)
    profile = page._get_profile()
    sheet, _field = page._find(profile, folder, sheet_name, None)
    assert sheet is not None
    return FieldFormDialog(None, profile, folder, sheet, None)


def test_window_opens_the_saved_profile(window: MainWindow) -> None:
    assert window.profile_combo.count() == 1
    assert window.windowTitle().endswith("Pabrik Uji")


def test_wizard_pages_mirror_the_profile(window: MainWindow) -> None:
    folders = window.page_sources.folder_list
    checked = {
        folders.item(index).text()
        for index in range(folders.count())
        if folders.item(index).checkState() == Qt.Checked
    }
    assert checked == {"prod_harian", "lap_harian", "penjualan_harian"}
    assert window.page_fields.tree.topLevelItemCount() == 3


def test_run_fills_the_result_table(window: MainWindow) -> None:
    window.page_run._run()
    worker = window.page_run._worker
    assert worker is not None
    assert worker.wait(60_000)
    QApplication.processEvents()
    assert window.page_run.table.rowCount() == 15
    assert "need review" in window.page_run.summary_label.text()
    assert window.page_run.issues_list.count() >= 1
    result_path = window.page_run._result_path
    assert result_path is not None
    assert result_path.exists()
    assert window.page_run.save_button.isEnabled()


def test_add_data_button_opens_the_form_and_saves(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: '+ Tambah Data' must open the form (Qt6 combo row hiding)."""
    page = window.page_fields
    sheet_item = page.tree.topLevelItem(0).child(0)
    sheet_item.setSelected(True)
    assert page.field_button.isEnabled()

    def fill_and_save(dialog: FieldFormDialog) -> int:
        dialog.name_edit.setText("nilai_baru")
        dialog.row_editor.edit.setText("Produksi Harian")
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(FieldFormDialog, "exec", fill_and_save)
    page.field_button.click()

    sheet_item = page.tree.topLevelItem(0).child(0)  # re-fetch: refresh() rebuilt the tree
    names = [sheet_item.child(index).text(0) for index in range(sheet_item.childCount())]
    assert any(text.startswith("nilai_baru") for text in names)


def test_closed_dialogs_are_torn_down_by_qt_not_the_gc(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a form dialog left to the GC segfaulted the app on macOS (cocoa)."""
    page = window.page_fields
    teardowns: list[str] = []

    def accept_sheet(dialog: SheetDialog) -> int:
        dialog.name_combo.setCurrentText("Sheet Baru")
        dialog.accept()
        return dialog.result()

    page.tree.topLevelItem(0).setSelected(True)
    monkeypatch.setattr(SheetDialog, "exec", accept_sheet)
    monkeypatch.setattr(SheetDialog, "deleteLater", lambda self: teardowns.append("sheet"))
    page.sheet_button.click()
    source_item = page.tree.topLevelItem(0)
    sheet_names = [source_item.child(index).text(0) for index in range(source_item.childCount())]
    assert "Sheet: Sheet Baru" in sheet_names

    def reject_field(dialog: FieldFormDialog) -> int:
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(FieldFormDialog, "exec", reject_field)
    monkeypatch.setattr(FieldFormDialog, "deleteLater", lambda self: teardowns.append("field"))
    page.tree.topLevelItem(0).child(0).setSelected(True)
    page.field_button.click()

    QApplication.processEvents()  # the app schedules the dialog teardown here
    gc.collect()  # the crash happened inside a pass like this one
    assert teardowns == ["sheet", "field"]
    assert page.tree.topLevelItemCount() == 3


def test_duplicate_sheet_copies_every_field_to_a_new_sheet(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The daily-report case: the next date's sheet reuses the same rules."""
    page = window.page_fields
    warnings: list[str] = []  # a modal warning would hang an offscreen run, so record it
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **_kwargs: warnings.append(args[2]))
    page.tree.topLevelItem(0).child(0).setSelected(True)
    assert page.duplicate_button.isEnabled()

    def accept_sheet(dialog: SheetDialog) -> int:
        dialog.name_combo.setCurrentText(next(names))
        dialog.accept()
        return dialog.result()

    names = iter(["Produksi 02-10", "Produksi 03-10"])
    monkeypatch.setattr(SheetDialog, "exec", accept_sheet)
    page.duplicate_button.click()

    source_item = page.tree.topLevelItem(0)  # re-fetch: refresh() rebuilt the tree
    labels = [source_item.child(index).text(0) for index in range(source_item.childCount())]
    assert "Sheet: Produksi 02-10" in labels

    source = page._get_profile().sources[0]
    assert [sheet.name for sheet in source.sheets] == ["Produksi", "Produksi 02-10"]
    original, copy = source.sheets
    assert len(copy.fields) == len(original.fields) > 0
    for before, after in zip(original.fields, copy.fields, strict=True):
        assert after.output_name == f"{before.output_name}_2"  # SPEC: unique per profile
        assert after.row_keyword.text == before.row_keyword.text
        assert after.col_keyword == before.col_keyword

    # duplicating the copy must not stack suffixes (`prod_hi_2_2`) nor reuse taken names
    page.tree.topLevelItem(0).child(1).setSelected(True)
    page.duplicate_button.click()
    third = page._get_profile().sources[0].sheets[2]
    assert third.name == "Produksi 03-10"
    assert [field.output_name for field in third.fields] == [
        f"{field.output_name}_3" for field in original.fields
    ]
    assert warnings == []


def test_free_output_name_skips_a_name_the_profile_already_uses() -> None:
    assert _free_output_name("prod_hi_copy", set()) == "prod_hi_copy"
    assert _free_output_name("prod_hi_copy", {"prod_hi_copy"}) == "prod_hi_copy_2"
    assert _free_output_name("prod_hi_copy", {"prod_hi_copy", "prod_hi_copy_2"}) == "prod_hi_copy_3"
    assert _free_output_name("prod_hi_2", {"prod_hi", "prod_hi_2"}) == "prod_hi_3"
    assert _free_output_name("harga_2024", {"harga_2024"}) == "harga_2024_2"


def _drag_drop(
    tree: QTreeWidget,
    dragged: QTreeWidgetItem,
    target: QTreeWidgetItem,
    below: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A drag-and-drop gesture without a mouse: offscreen Qt never sends a real one."""
    tree.setCurrentItem(dragged)
    monkeypatch.setattr(tree, "itemAt", lambda _position: target)
    monkeypatch.setattr(
        tree,
        "dropIndicatorPosition",
        lambda: QAbstractItemView.BelowItem if below else QAbstractItemView.AboveItem,
    )
    tree.dropEvent(
        QDropEvent(QPointF(0, 0), Qt.MoveAction, QMimeData(), Qt.LeftButton, Qt.NoModifier)
    )


def test_a_change_keeps_rows_open_as_the_user_left_them(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: every edit rebuilt the tree and closed every sheet the user had opened."""

    def accept_sheet(dialog: SheetDialog) -> int:
        dialog.name_combo.setCurrentText("Sheet Kedua")
        dialog.accept()
        return dialog.result()

    page = window.page_fields
    monkeypatch.setattr(SheetDialog, "exec", accept_sheet)
    page.tree.topLevelItem(0).setSelected(True)
    page.sheet_button.click()

    first, second = (page.tree.topLevelItem(0).child(index) for index in (0, 1))
    assert second.isExpanded()  # the sheet just added is in view
    second.setExpanded(False)
    first.setExpanded(True)

    def fill_and_save(dialog: FieldFormDialog) -> int:
        dialog.name_edit.setText("nilai_kelima")
        dialog.row_editor.edit.setText("Produksi Harian")
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(FieldFormDialog, "exec", fill_and_save)
    page.tree.clearSelection()  # offscreen, item.setSelected alone keeps the earlier row
    first.setSelected(True)
    page.field_button.click()

    first, second = (page.tree.topLevelItem(0).child(index) for index in (0, 1))
    assert first.isExpanded()  # still open: the new row is visible without another click
    assert first.isSelected()
    assert not second.isExpanded()  # a sheet the user closed stays closed


def test_drag_and_drop_reorders_fields_and_sheets(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user arranges the order by dragging a row; the rules themselves stay put."""
    page = window.page_fields
    sheet_item = page.tree.topLevelItem(0).child(0)
    names = [
        sheet_item.child(index).data(0, Qt.UserRole)[3]
        for index in range(sheet_item.childCount())
    ]
    assert len(names) > 1

    _drag_drop(page.tree, sheet_item.child(1), sheet_item.child(0), False, monkeypatch)

    sheet = page._get_profile().sources[0].sheets[0]
    assert [field.output_name for field in sheet.fields] == [names[1], names[0], *names[2:]]

    def accept_sheet(dialog: SheetDialog) -> int:
        dialog.name_combo.setCurrentText("Sheet Baru")
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(SheetDialog, "exec", accept_sheet)
    page.tree.clearSelection()  # setSelected() never clears the previous row (Qt single selection)
    page.tree.topLevelItem(0).setSelected(True)
    page.sheet_button.click()
    source_item = page.tree.topLevelItem(0)  # re-fetch: refresh() rebuilt the tree
    assert source_item.child(1).data(0, Qt.UserRole)[2] == "Sheet Baru"

    _drag_drop(page.tree, source_item.child(1), source_item.child(0), False, monkeypatch)
    assert [item.name for item in page._get_profile().sources[0].sheets] == [
        "Sheet Baru",
        "Produksi",
    ]

    # a drop on the sheet row itself means "put it last"
    sheet_item = page.tree.topLevelItem(0).child(1)  # re-fetch: refresh() rebuilt the tree
    dropped = sheet_item.child(0).data(0, Qt.UserRole)[3]
    _drag_drop(page.tree, sheet_item.child(0), sheet_item, True, monkeypatch)
    fields = page._get_profile().sources[0].sheets[1].fields
    assert [field.output_name for field in fields][-1] == dropped


def test_drag_and_drop_ignores_moves_across_sheets_and_folders(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A field must not jump to another sheet, and a sheet not to another folder.

    (Moving a field to another sheet is an edit, not a reorder; nothing was asked for.)
    """
    page = window.page_fields
    first = page.tree.topLevelItem(0)
    other = page.tree.topLevelItem(1)
    fields_before = [
        [
            sheet_item.child(index).data(0, Qt.UserRole)[3]
            for index in range(sheet_item.childCount())
        ]
        for sheet_item in (first.child(0), other.child(0))
    ]

    _drag_drop(page.tree, first.child(0).child(0), other.child(0).child(0), True, monkeypatch)

    sources = page._get_profile().sources
    assert [
        [field.output_name for field in source.sheets[0].fields] for source in sources[:2]
    ] == fields_before

    sheets_before = [sheet.name for sheet in sources[0].sheets]
    _drag_drop(
        page.tree,
        page.tree.topLevelItem(0).child(0),
        page.tree.topLevelItem(1).child(0),
        True,
        monkeypatch,
    )
    assert [sheet.name for sheet in page._get_profile().sources[0].sheets] == sheets_before


def test_advanced_match_mode_stays_hidden(app: QApplication, window: MainWindow) -> None:
    """The 'Lanjutan' row is only hidden in the popup, not removed from the list."""
    dialog = field_dialog(window)
    combo = dialog.row_editor.mode_combo
    assert combo.count() == HIDDEN_MODE_INDEX + 1
    assert combo.itemText(HIDDEN_MODE_INDEX) == "Advanced"
    assert combo.view().isRowHidden(HIDDEN_MODE_INDEX)
    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_preview_survives_a_second_run(app: QApplication, window: MainWindow) -> None:
    """Regression: a finished preview thread must not leave a dangling worker."""
    dialog = field_dialog(window)
    dialog.name_edit.setText("nilai_baru")
    dialog.row_editor.edit.setText("Produksi Harian")
    pane = dialog.preview
    assert pane.sample_combo.count() >= 1  # a real preview needs a sample file
    for _ in range(2):
        pane._start_pending()
        assert pane._worker is not None
        assert pane._worker.wait(60_000)
        QApplication.processEvents()  # deliver finished, which frees the worker
        assert pane.status_label.text(), "preview finished without a status"
        assert pane._worker is None
    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def _dark_palette() -> QPalette:
    """The palette a dark system theme hands to Qt: near-black fills, white text."""
    palette = QPalette()
    for role in (QPalette.Window, QPalette.Base, QPalette.Button, QPalette.AlternateBase):
        palette.setColor(role, QColor("#1E1E1E"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(role, QColor("white"))
    return palette


def _luminance(colour: QColor) -> float:
    channels = [
        value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        for value in (colour.redF(), colour.greenF(), colour.blueF())
    ]
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: QColor, second: QColor) -> float:
    """WCAG contrast ratio; 4.5 is the smallest readable value for body text."""
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _grid(merged_range: str | None = None) -> dict:
    """A mini-grid as `PreviewWorker._build_grid` returns it, around cell I47."""
    return {
        "rows": [["", "Total", ""], ["", "Catatan", ""], ["Produksi Harian", "1523.5", ""]],
        "row_numbers": [45, 46, 47],
        "col_letters": ["H", "I", "J"],
        "row_keyword": "H47",
        "col_keyword": "I45",
        "value_address": "I47",
        "merged_range": merged_range,
    }


def test_preview_text_stays_readable_on_its_light_fills(app: QApplication) -> None:
    """Regression: white themed text on the preview's light fills made it invisible (dark mode)."""
    original = QPalette(app.palette())
    app.setPalette(_dark_palette())
    pane = PreviewPane()
    try:
        assert _contrast(_TEXT_ON_LIGHT, _BOX_BG) >= 4.5
        assert _TEXT_ON_LIGHT.name() in pane.value_label.styleSheet()
        assert _BOX_BG.name() in pane.value_label.styleSheet()
        text_role = pane.grid_table.palette().color(QPalette.Text)
        for grid, expected in ((_grid(), 3), (_grid(merged_range="I47:J47"), 4)):
            pane._fill_grid(grid)
            filled = 0
            for row in range(pane.grid_table.rowCount()):
                for column in range(pane.grid_table.columnCount()):
                    item = pane.grid_table.item(row, column)
                    if item is None or item.background().style() == Qt.NoBrush:
                        continue
                    filled += 1
                    brush = item.foreground()
                    colour = brush.color() if brush.style() != Qt.NoBrush else text_role
                    ratio = _contrast(colour, item.background().color())
                    assert ratio >= 4.5, f"{item.text()!r} unreadable: contrast {ratio:.2f}"
            assert filled == expected  # row keyword, column keyword, value (+ merged range)
    finally:
        pane.deleteLater()
        app.setPalette(original)
        app.processEvents()
