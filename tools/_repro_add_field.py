"""Throwaway repro: can a beginner add a field (keyword) from Langkah 2?"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core.models import Profile, SourceConfig  # noqa: E402
from ui.field_form import FieldFormDialog  # noqa: E402
from ui.step2_fields import StepData  # noqa: E402

MESSAGES: list[tuple[str, str]] = []


def _record(kind: str):  # type: ignore[no-untyped-def]
    def _call(parent, title, text, *args, **kwargs):  # type: ignore[no-untyped-def]
        MESSAGES.append((kind, f"{title} / {text}"))
        return QMessageBox.Ok

    return _call


QMessageBox.warning = _record("warning")  # type: ignore[assignment]
QMessageBox.information = _record("info")  # type: ignore[assignment]
QMessageBox.question = _record("question")  # type: ignore[assignment]


def buttons(page: StepData) -> str:
    return (
        f"sheet={page.sheet_button.isEnabled()} field={page.field_button.isEnabled()} "
        f"edit={page.edit_button.isEnabled()} del={page.delete_button.isEnabled()}"
    )


def select(page: StepData, kind: str, index: int | None = None) -> None:
    page.tree.clearSelection()
    stack = [page.tree.topLevelItem(i) for i in range(page.tree.topLevelItemCount())]
    while stack:
        item = stack.pop(0)
        data = item.data(0, Qt.UserRole)
        if data and data[0] == kind:
            item.setSelected(True)
            return
        for i in range(item.childCount()):
            stack.append(item.child(i))


app = QApplication.instance() or QApplication([])

print("=== 1. folder dicentang, belum ada sheet ===")
p1 = Profile(name="p", input_root=None, sources=[SourceConfig(folder="lap_harian", enabled=True)])
page = StepData(lambda: p1, lambda: None)
page.refresh()
print("pilih folder ->", buttons(page))

print("=== 2. sudah ada sheet ===")
p2 = Profile.model_validate(
    {
        "name": "p",
        "sources": [
            {
                "folder": "lap_harian",
                "enabled": True,
                "sheets": [{"name": "Produksi", "fields": []}],
            }
        ],
    }
)
page2 = StepData(lambda: p2, lambda: None)
page2.refresh()
print("pilih folder ->", buttons(page2))
select(page2, "sheet")
print("pilih sheet  ->", buttons(page2))

print("=== 3. klik '+ Tambah Data' saat folder dipilih (bukan sheet) ===")
select(page2, "source")
MESSAGES.clear()
page2._add_field()
print("pesan:", MESSAGES or "TIDAK ADA PESAN APA PUN")

print("=== 4. isi form: nama + keyword baris, kolom dikosongkan ===")
sheet = p2.sources[0].sheets[0]
dialog = FieldFormDialog(None, p2, "lap_harian", sheet, None)
dialog.name_edit.setText("prod_hi")
dialog.row_editor.edit.setText("Produksi Harian")
MESSAGES.clear()
dialog.accept()
print("hasil:", dialog.result(), "pesan:", MESSAGES or "TIDAK ADA")
print("field:", dialog.field)
print("sources:", dialog.sources)

print("=== 5. form kosong lalu Simpan ===")
dialog2 = FieldFormDialog(None, p2, "lap_harian", sheet, None)
MESSAGES.clear()
dialog2.accept()
print("pesan:", MESSAGES or "TIDAK ADA PESAN")

print("=== 6. nama pakai spasi (bukan huruf/angka/garis bawah) ===")
dialog3 = FieldFormDialog(None, p2, "lap_harian", sheet, None)
dialog3.name_edit.setText("Produksi Harian")
dialog3.row_editor.edit.setText("Produksi")
MESSAGES.clear()
dialog3.accept()
print("pesan:", MESSAGES or "TIDAK ADA PESAN")

for widget in (page, page2, dialog, dialog2, dialog3):
    widget.close()
    widget.deleteLater()
app.processEvents()
