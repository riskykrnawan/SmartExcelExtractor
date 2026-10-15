"""Mapping CSV: draft from a sample sheet, and the export/import round trip."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.cell_index import ExcelFileError
from core.mapping import CSV_COLUMNS, MappingError, export_csv, import_csv, suggest_csv
from core.models import DataType, Profile, ValueDirection
from tests.test_extractor import profile_for

HEADER = ",".join(CSV_COLUMNS) + "\n"


def test_suggest_drafts_labels_that_have_a_value_beside_them(input_a: Path) -> None:
    path = input_a / "prod_harian" / "Prod_14Okt2026.xlsx"
    rows = suggest_csv(path, "Produksi", "prod_harian")
    names = {row["output_name"] for row in rows}
    assert {"harian", "akum"} <= names
    assert all(row["row_keyword"] and not row["col_keyword"] for row in rows)
    assert all(row["folder"] == "prod_harian" and row["sheet"] == "Produksi" for row in rows)


def test_suggest_rejects_a_sheet_that_is_not_there(input_a: Path) -> None:
    path = input_a / "prod_harian" / "Prod_14Okt2026.xlsx"
    with pytest.raises(MappingError, match="Tidak Ada"):
        suggest_csv(path, "Tidak Ada", "prod_harian")


def test_suggest_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ExcelFileError):
        suggest_csv(tmp_path / "hilang.xlsx", "Produksi", "prod_harian")


def test_suggest_writes_the_csv_it_returns(input_a: Path, tmp_path: Path) -> None:
    path = input_a / "penjualan_harian" / "Penjualan_14Okt.xlsx"
    out = tmp_path / "draf.csv"
    rows = suggest_csv(path, "Penjualan", "penjualan_harian", out)
    assert out.read_text(encoding="utf-8").startswith(HEADER)
    assert len(import_csv(out)[0].sheets[0].fields) == len(rows)


def test_export_after_import_gives_the_same_csv(input_a: Path, tmp_path: Path) -> None:
    """Everything the CSV can carry survives a trip through a profile."""
    profile = profile_for(input_a, unique_violation=False)
    first = tmp_path / "pertama.csv"
    export_csv(profile, first)
    rebuilt = Profile(name=profile.name, input_root=profile.input_root, sources=import_csv(first))
    again = tmp_path / "kedua.csv"
    export_csv(rebuilt, again)
    assert again.read_text(encoding="utf-8") == first.read_text(encoding="utf-8")


def test_import_keeps_the_simple_settings_as_given(tmp_path: Path) -> None:
    path = tmp_path / "mapping.csv"
    path.write_text(
        HEADER + "prod_harian,Produksi,prod_hi,Produksi Harian,Total,down,2,number,true\n",
        encoding="utf-8",
    )
    field = import_csv(path)[0].sheets[0].fields[0]
    assert field.output_name == "prod_hi" and field.col_keyword is not None
    assert field.row_keyword.text == "Produksi Harian"
    assert field.value_direction is ValueDirection.DOWN and field.value_offset == 2
    assert field.data_type is DataType.NUMBER and field.allow_empty


def test_import_names_the_missing_column(tmp_path: Path) -> None:
    path = tmp_path / "kurang.csv"
    path.write_text("folder,sheet\nprod_harian,Produksi\n", encoding="utf-8")
    with pytest.raises(MappingError, match="output_name"):
        import_csv(path)


def test_import_names_the_line_with_a_bad_value(tmp_path: Path) -> None:
    path = tmp_path / "offset.csv"
    path.write_text(
        HEADER + "prod_harian,Produksi,prod_hi,Produksi Harian,Total,right,0,any,false\n",
        encoding="utf-8",
    )
    with pytest.raises(MappingError, match="Baris 2"):
        import_csv(path)


def test_import_rejects_an_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "kosong.csv"
    path.write_text(HEADER, encoding="utf-8")
    with pytest.raises(MappingError, match="satu baris pun"):
        import_csv(path)


def test_import_rejects_an_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(MappingError, match="tidak bisa dibaca"):
        import_csv(tmp_path / "tidak-ada.csv")
