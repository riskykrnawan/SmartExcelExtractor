"""Smoke test: the window builds, the wizard mirrors the profile, a run shows results."""
from __future__ import annotations

import gc
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="antarmuka memerlukan PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.profiles import save_profile  # noqa: E402
from tests.test_extractor import profile_for  # noqa: E402
from ui.field_form import HIDDEN_MODE_INDEX, FieldFormDialog  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.step2_fields import SheetDialog  # noqa: E402


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
    assert "perlu dicek" in window.page_run.summary_label.text()
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


def test_advanced_match_mode_stays_hidden(app: QApplication, window: MainWindow) -> None:
    """The 'Lanjutan' row is only hidden in the popup, not removed from the list."""
    dialog = field_dialog(window)
    combo = dialog.row_editor.mode_combo
    assert combo.count() == HIDDEN_MODE_INDEX + 1
    assert combo.itemText(HIDDEN_MODE_INDEX) == "Lanjutan"
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
