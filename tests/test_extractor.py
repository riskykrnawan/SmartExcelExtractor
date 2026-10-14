"""End-to-end extraction against the messy sample workbooks."""
from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

from core.audit import RunResult
from core.extractor import run_extraction
from core.models import (
    DataType,
    DisambiguationMode,
    FieldConfig,
    KeywordConfig,
    MatchMode,
    Profile,
    SheetConfig,
    SourceConfig,
    ValueDirection,
)


def row_by_address(text: str, address: str) -> KeywordConfig:
    """A repeated keyword resolved by its reference address."""
    return KeywordConfig(
        text=text,
        is_unique=False,
        disambiguation=DisambiguationMode.BY_ADDRESS,
        reference_address=address,
    )


def profile_for(input_root: Path, *, unique_violation: bool = True) -> Profile:
    """The full 3-source test profile (15 fields, one deliberate unique violation)."""
    prod_fields = [
        FieldConfig(
            output_name="prod_hi",
            row_keyword=row_by_address("Produksi Harian", "I45"),
            col_keyword=KeywordConfig(text="Total"),
        ),
        FieldConfig(
            output_name="prod_formula",
            row_keyword=row_by_address("Produksi Harian", "I45"),
            col_keyword=KeywordConfig(text="Harian"),
        ),
        FieldConfig(
            output_name="prod_energy",
            row_keyword=KeywordConfig(text="Total Energi"),
            col_keyword=KeywordConfig(text="Total"),
        ),
        FieldConfig(
            output_name="prod_util",
            row_keyword=KeywordConfig(text="Utilisasi Mesin"),
            col_keyword=KeywordConfig(text="Total"),
        ),
        FieldConfig(
            output_name="prod_tgl",
            row_keyword=KeywordConfig(text="Tanggal Laporan"),
            col_keyword=KeywordConfig(text="Total"),
        ),
        FieldConfig(
            output_name="prod_target",
            row_keyword=KeywordConfig(text="Target Harian"),
            col_keyword=KeywordConfig(text="Total"),
            data_type=DataType.NUMBER,
        ),
        FieldConfig(
            output_name="prod_catatan",
            row_keyword=KeywordConfig(text="Catatan"),
            col_keyword=KeywordConfig(text="Total"),
        ),
        FieldConfig(
            output_name="prod_catatan_ok",
            row_keyword=KeywordConfig(text="Catatan"),
            col_keyword=KeywordConfig(text="Total"),
            allow_empty=True,
        ),
        FieldConfig(
            output_name="prod_scrap",
            row_keyword=KeywordConfig(text="Scrap Harian"),
            col_keyword=KeywordConfig(text="Total"),
        ),
    ]
    if unique_violation:
        prod_fields.append(
            FieldConfig(
                output_name="prod_unique",
                row_keyword=KeywordConfig(text="Produksi Harian"),
                col_keyword=KeywordConfig(text="Total"),
            )
        )

    lap_fields = [
        FieldConfig(
            output_name="lap_near",
            row_keyword=KeywordConfig(
                text="Total Produksi",
                is_unique=False,
                disambiguation=DisambiguationMode.NEAR_KEYWORD,
                reference_keyword=KeywordConfig(text="SECTION PRODUKSI"),
            ),
            value_direction=ValueDirection.RIGHT,
        ),
        FieldConfig(
            output_name="lap_far",
            row_keyword=KeywordConfig(
                text="Total Produksi",
                is_unique=False,
                disambiguation=DisambiguationMode.NOT_NEAR_KEYWORD,
                reference_keyword=KeywordConfig(text="SUMMARY"),
            ),
            value_direction=ValueDirection.RIGHT,
        ),
    ]
    pen_fields = [
        FieldConfig(
            output_name="pen_harian",
            row_keyword=row_by_address("Penjualan Harian", "A10"),
        ),
        FieldConfig(
            output_name="pen_harga",
            row_keyword=KeywordConfig(text="Harga Jual"),
            value_direction=ValueDirection.DOWN,
        ),
        FieldConfig(
            output_name="pen_target",
            row_keyword=KeywordConfig(text="Target"),
            value_direction=ValueDirection.LEFT,
        ),
    ]
    sources = [
        SourceConfig(
            folder="prod_harian",
            sheets=[SheetConfig(name="Produksi", match_mode=MatchMode.CONTAINS, fields=prod_fields)],
        ),
        SourceConfig(
            folder="lap_harian",
            sheets=[SheetConfig(name="Laporan", match_mode=MatchMode.CONTAINS, fields=lap_fields)],
        ),
        SourceConfig(
            folder="penjualan_harian",
            sheets=[SheetConfig(name="Penjualan", fields=pen_fields)],
        ),
    ]
    return Profile(
        name="Pabrik Uji",
        input_root=str(input_root),
        sources=sources,
    )


def single_field_profile(
    input_root: Path | None,
    field_cfg: FieldConfig,
    *,
    folder: str = "prod_harian",
    sheet: str = "Produksi",
    match_mode: MatchMode = MatchMode.CONTAINS,
) -> Profile:
    """One source, one sheet, one field: for focused error tests."""
    return Profile(
        name="Fokus",
        input_root=str(input_root) if input_root else None,
        sources=[
            SourceConfig(
                folder=folder,
                sheets=[SheetConfig(name=sheet, match_mode=match_mode, fields=[field_cfg])],
            )
        ],
    )


def simple_field(output_name: str = "satu") -> FieldConfig:
    """A trivially valid field used by file/sheet level error tests."""
    return FieldConfig(
        output_name=output_name,
        row_keyword=KeywordConfig(text="Produksi Harian"),
        col_keyword=KeywordConfig(text="Total"),
    )


def issue_codes(result: RunResult, field_name: str | None) -> set[str]:
    """Issue codes recorded for one field (or for the source when field is None)."""
    return {
        issue["code"]
        for issue in result.audit["issues"]
        if issue["field"] == field_name
    }


def field_audit(result: RunResult, field_name: str) -> dict:
    """The audit.fields entry of one field."""
    return next(entry for entry in result.audit["fields"] if entry["field"] == field_name)


class TestVariantA:
    """Base layout: every behavior visible in one run."""

    @pytest.fixture()
    def result(self, input_a: Path) -> RunResult:
        return run_extraction(profile_for(input_a))

    def test_summary_counts(self, result: RunResult) -> None:
        assert result.summary == {"total_fields": 15, "ok": 9, "warning": 5, "error": 1}

    def test_prod_hi_value_and_location(self, result: RunResult) -> None:
        entry = result.data["prod_hi"]
        assert entry["value"] == 1523.5
        assert entry["status"] == "ok"
        assert entry["source"]["folder"] == "prod_harian"
        assert entry["source"]["file"] == "Prod_14Okt2026.xlsx"
        assert entry["source"]["sheet"] == "Produksi"
        assert entry["source"]["file_modified"] is not None
        assert entry["location"] == {
            "value_address": "L45",
            "row_keyword_address": "I45",
            "col_keyword_address": "L12",
        }
        assert entry["value_meta"]["type_found"] == "number"
        assert entry["value_meta"]["raw_value"] == "1523.5"

    def test_formula_without_cache_warns(self, result: RunResult) -> None:
        entry = result.data["prod_formula"]
        assert entry["value"] is None
        assert entry["status"] == "warning"
        assert entry["value_meta"]["from_formula"] is True
        assert issue_codes(result, "prod_formula") == {"FORMULA_NOT_CALCULATED"}

    def test_excel_error_value_warns(self, result: RunResult) -> None:
        entry = result.data["prod_energy"]
        assert entry["value"] == "#REF!"
        assert entry["status"] == "warning"
        assert entry["value_meta"]["type_found"] == "error"
        assert issue_codes(result, "prod_energy") == {"EXCEL_ERROR_VALUE"}

    def test_merged_value_read_from_top_left(self, result: RunResult) -> None:
        entry = result.data["prod_util"]
        assert entry["value"] == 87.2
        assert entry["value_meta"]["merged"] is True
        assert entry["value_meta"]["merged_range"] == "K57:L57"
        assert entry["location"]["value_address"] == "L57"
        assert issue_codes(result, "prod_util") == {"MERGED_CELL"}

    def test_hidden_row_is_flagged_but_not_an_issue(self, result: RunResult) -> None:
        entry = result.data["prod_scrap"]
        assert entry["value"] == 12
        assert entry["value_meta"]["hidden"] is True
        assert entry["status"] == "ok"

    def test_date_converted_to_iso(self, result: RunResult) -> None:
        entry = result.data["prod_tgl"]
        assert str(entry["value"]).startswith("2026-10-14")
        assert entry["value_meta"]["type_found"] == "date"

    def test_type_mismatch_keeps_raw_value(self, result: RunResult) -> None:
        entry = result.data["prod_target"]
        assert entry["value"] == "N/A"
        assert entry["value_meta"]["raw_value"] == "N/A"
        assert issue_codes(result, "prod_target") == {"TYPE_MISMATCH"}

    def test_empty_value_warns_unless_allowed(self, result: RunResult) -> None:
        assert result.data["prod_catatan"]["value"] is None
        assert result.data["prod_catatan"]["status"] == "warning"
        assert issue_codes(result, "prod_catatan") == {"EMPTY_VALUE"}
        assert result.data["prod_catatan_ok"]["status"] == "ok"
        assert issue_codes(result, "prod_catatan_ok") == set()

    def test_unique_violation_fails_without_guessing(self, result: RunResult) -> None:
        entry = result.data["prod_unique"]
        assert entry["status"] == "error"
        assert entry["value"] is None
        audit = field_audit(result, "prod_unique")
        assert audit["row_keyword"]["candidates"] == ["I45", "I94"]
        assert audit["row_keyword"]["selected"] is None
        assert "UNIQUE_VIOLATION" in issue_codes(result, "prod_unique")

    def test_temp_lock_file_is_ignored(self, result: RunResult) -> None:
        codes = {issue["code"] for issue in result.audit["issues"]}
        assert "MULTIPLE_FILES" not in codes

    def test_one_failure_does_not_stop_others(self, result: RunResult) -> None:
        assert result.data["prod_unique"]["status"] == "error"
        assert result.data["prod_hi"]["status"] == "ok"
        assert result.data["lap_near"]["status"] == "ok"


class TestOffsetModes:
    """No column keyword: value sits right/below/left of the label."""

    @pytest.fixture()
    def result(self, input_a: Path) -> RunResult:
        return run_extraction(profile_for(input_a))

    def test_near_picks_section_produksi_occurrence(self, result: RunResult) -> None:
        entry = result.data["lap_near"]
        assert entry["value"] == 1523.5
        assert entry["location"]["value_address"] == "D25"
        assert entry["location"]["col_keyword_address"] is None
        audit = field_audit(result, "lap_near")
        assert audit["row_keyword"]["candidates"] == ["C5", "C25"]
        assert audit["row_keyword"]["selected"] == "C25"
        assert audit["row_keyword"]["disambiguation"] == "near_keyword"
        assert audit["row_keyword"]["reference"] == "SECTION PRODUKSI"

    def test_not_near_drops_summary_occurrence(self, result: RunResult) -> None:
        entry = result.data["lap_far"]
        assert entry["value"] == 1523.5
        audit = field_audit(result, "lap_far")
        assert audit["row_keyword"]["selected"] == "C25"
        assert audit["row_keyword"]["disambiguation"] == "not_near_keyword"

    def test_value_right_of_label(self, result: RunResult) -> None:
        entry = result.data["pen_harian"]
        assert entry["value"] == 2_500_000
        assert entry["location"]["value_address"] == "B10"
        assert entry["value_meta"]["hidden"] is True  # column B is hidden
        audit = field_audit(result, "pen_harian")
        assert audit["row_keyword"]["selected"] == "A10"
        assert audit["row_keyword"]["drift"] is None

    def test_value_below_label(self, result: RunResult) -> None:
        entry = result.data["pen_harga"]
        assert entry["value"] == 15_000
        assert entry["location"]["value_address"] == "A18"

    def test_value_left_of_label(self, result: RunResult) -> None:
        entry = result.data["pen_target"]
        assert entry["value"] == 2_400_000
        assert entry["location"]["value_address"] == "A30"


class TestVariantB:
    """Shifted layout: sheet name matches with contains, addresses drift."""

    @pytest.fixture()
    def result(self, input_b: Path) -> RunResult:
        return run_extraction(profile_for(input_b))

    def test_sheet_name_matched_by_contains(self, result: RunResult) -> None:
        assert result.data["prod_hi"]["source"]["sheet"] == "Produksi 01-10"

    def test_address_drift_is_a_warning(self, result: RunResult) -> None:
        entry = result.data["prod_hi"]
        assert entry["value"] == 1600.0
        assert entry["status"] == "warning"
        assert entry["location"]["value_address"] == "M48"
        assert "ADDRESS_DRIFT" in issue_codes(result, "prod_hi")
        audit = field_audit(result, "prod_hi")
        assert audit["row_keyword"]["drift"] == {
            "reference": "I45",
            "actual": "I48",
            "row_delta": 3,
            "col_delta": 0,
        }


class TestSheetErrors:
    def test_sheet_not_found_lists_available_sheets(self, input_a: Path) -> None:
        profile = single_field_profile(input_a, simple_field(), sheet="TidakAda")
        result = run_extraction(profile)
        entry = result.data["satu"]
        assert entry["status"] == "error"
        assert entry["value"] is None
        assert "SHEET_NOT_FOUND" in issue_codes(result, "satu")
        message = next(i["message"] for i in result.audit["issues"] if i["field"] == "satu")
        assert "Sheet yang tersedia" in message

    def test_ambiguous_sheet_name_never_guesses(self, tmp_path: Path) -> None:
        folder = tmp_path / "sumber"
        folder.mkdir(parents=True)
        wb = Workbook()
        wb.active.title = "Data 1"
        wb.create_sheet("Data 2")
        wb.save(folder / "dua_sheet.xlsx")
        profile = single_field_profile(tmp_path, simple_field(), folder="sumber", sheet="Data")
        result = run_extraction(profile)
        assert "SHEET_AMBIGUOUS" in issue_codes(result, "satu")
        assert result.data["satu"]["value"] is None


class TestFileErrors:
    def test_empty_folder(self, tmp_path: Path) -> None:
        (tmp_path / "input" / "kosong").mkdir(parents=True)
        profile = single_field_profile(tmp_path / "input", simple_field(), folder="kosong")
        result = run_extraction(profile)
        assert "FILE_NOT_FOUND" in issue_codes(result, "satu")
        assert result.data["satu"]["source"]["file"] is None

    def test_missing_folder(self, tmp_path: Path) -> None:
        profile = single_field_profile(tmp_path / "tidak-ada", simple_field())
        result = run_extraction(profile)
        assert "FILE_NOT_FOUND" in issue_codes(result, "satu")

    def test_input_root_not_set(self) -> None:
        profile = single_field_profile(None, simple_field())
        result = run_extraction(profile)
        assert "FILE_NOT_FOUND" in issue_codes(result, "satu")
        message = next(i["message"] for i in result.audit["issues"] if i["field"] == "satu")
        assert "Folder induk belum diatur" in message

    def test_unreadable_file(self, tmp_path: Path) -> None:
        folder = tmp_path / "input" / "rusak"
        folder.mkdir(parents=True)
        (folder / "rusak.xlsx").write_bytes(b"bukan file excel sama sekali")
        profile = single_field_profile(tmp_path / "input", simple_field(), folder="rusak")
        result = run_extraction(profile)
        assert "FILE_UNREADABLE" in issue_codes(result, "satu")
        message = next(i["message"] for i in result.audit["issues"] if i["field"] == "satu")
        assert "tidak bisa dibuka" in message

    def test_only_temp_file_treated_as_empty(self, tmp_path: Path) -> None:
        folder = tmp_path / "input" / "kunci"
        folder.mkdir(parents=True)
        (folder / "~$Prod.xlsx").write_bytes(b"lock")
        profile = single_field_profile(tmp_path / "input", simple_field(), folder="kunci")
        result = run_extraction(profile)
        assert "FILE_NOT_FOUND" in issue_codes(result, "satu")

    def test_corrupt_file_does_not_stop_other_sources(self, input_a: Path, tmp_path: Path) -> None:
        root = tmp_path / "input"
        shutil.copytree(input_a, root)
        bad = root / "lap_harian"
        for old in bad.glob("*.xlsx"):
            old.unlink()
        (bad / "laporan.xlsx").write_bytes(b"rusak")
        result = run_extraction(profile_for(root))
        assert result.data["prod_hi"]["status"] == "ok"
        assert "FILE_UNREADABLE" in issue_codes(result, "lap_near")


class TestMultipleFiles:
    def test_newest_file_picked_with_source_warning(self, input_a: Path, tmp_path: Path) -> None:
        root = tmp_path / "input"
        shutil.copytree(input_a, root)
        prod = root / "prod_harian"
        newer = prod / "Prod_15Okt2026.xlsx"
        shutil.copy2(prod / "Prod_14Okt2026.xlsx", newer)
        future = newer.stat().st_mtime + 1000
        os.utime(newer, (future, future))
        result = run_extraction(profile_for(root))
        assert result.data["prod_hi"]["source"]["file"] == "Prod_15Okt2026.xlsx"
        multi = [i for i in result.audit["issues"] if i["code"] == "MULTIPLE_FILES"]
        assert len(multi) == 1
        assert multi[0]["field"] is None
        assert "Prod_15Okt2026.xlsx" in multi[0]["message"]


class TestDeterminism:
    def test_same_input_same_output(self, input_a: Path) -> None:
        now = datetime(2026, 10, 14, 8, 30, tzinfo=UTC)
        first = run_extraction(profile_for(input_a), now=now)
        second = run_extraction(profile_for(input_a), now=now)
        assert first.to_dict() == second.to_dict()
        assert first.meta["run_at"] == "2026-10-14T08:30:00+00:00"
