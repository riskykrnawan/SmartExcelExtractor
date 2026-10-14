"""Disambiguation: unique, by-address, near, not-near; Chebyshev + tie-break."""
from __future__ import annotations

import pytest

from core.audit import ExtractionError, IssueCode
from core.cell_index import SheetData
from core.disambiguator import address_of, disambiguate
from core.matcher import fold_text, normalize_text
from core.models import DisambiguationMode, KeywordConfig


def make_sheet(cells: dict[tuple[int, int], str]) -> SheetData:
    """Build a SheetData directly from (row, col) -> text, without Excel files."""
    sheet = SheetData(title="Uji")
    for pos, text in cells.items():
        normalized = normalize_text(text)
        sheet.values[pos] = text
        sheet.texts[pos] = normalized
        sheet.index.setdefault(fold_text(normalized), []).append(pos)
    for bucket in sheet.index.values():
        bucket.sort()
    return sheet


BASE_CELLS = {
    (5, 3): "Total Produksi",
    (25, 3): "Total Produksi",
    (1, 1): "SUMMARY",
    (20, 1): "SECTION PRODUKSI",
    (45, 9): "Produksi Harian",
    (94, 9): "Produksi Harian",
}


def unique_kw(text: str) -> KeywordConfig:
    return KeywordConfig(text=text)


def by_address(text: str, address: str) -> KeywordConfig:
    return KeywordConfig(
        text=text,
        is_unique=False,
        disambiguation=DisambiguationMode.BY_ADDRESS,
        reference_address=address,
    )


def near(text: str, ref_text: str, radius: int = 10) -> KeywordConfig:
    return KeywordConfig(
        text=text,
        is_unique=False,
        disambiguation=DisambiguationMode.NEAR_KEYWORD,
        reference_keyword=KeywordConfig(text=ref_text),
        radius=radius,
    )


def not_near(text: str, ref_text: str, radius: int = 10) -> KeywordConfig:
    return KeywordConfig(
        text=text,
        is_unique=False,
        disambiguation=DisambiguationMode.NOT_NEAR_KEYWORD,
        reference_keyword=KeywordConfig(text=ref_text),
        radius=radius,
    )


class TestUnique:
    def test_single_match_selected(self) -> None:
        sheet = make_sheet({(45, 9): "Produksi Harian"})
        keyword = unique_kw("Produksi Harian")
        result = disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert result.selected == (45, 9)
        assert result.mode == "unique"

    def test_no_match_raises_key_not_found(self) -> None:
        sheet = make_sheet(BASE_CELLS)
        with pytest.raises(ExtractionError) as exc:
            disambiguate([], unique_kw("Tidak Ada"), sheet)
        assert exc.value.code is IssueCode.KEYWORD_NOT_FOUND

    def test_two_matches_raise_unique_violation_with_addresses(self) -> None:
        sheet = make_sheet(BASE_CELLS)
        keyword = unique_kw("Produksi Harian")
        with pytest.raises(ExtractionError) as exc:
            disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert exc.value.code is IssueCode.UNIQUE_VIOLATION
        assert exc.value.candidates == ["I45", "I94"]
        assert "ditemukan 2 kali" in exc.value.message


class TestByAddress:
    def test_exact_address_selected_without_drift(self) -> None:
        sheet = make_sheet(BASE_CELLS)
        keyword = by_address("Produksi Harian", "I45")
        result = disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert result.selected == (45, 9)
        assert result.drift is None
        assert result.warnings == []

    def test_nearest_candidate_wins_and_reports_drift(self) -> None:
        sheet = make_sheet(BASE_CELLS)
        keyword = by_address("Produksi Harian", "I46")  # 1 row above I45, 48 from I94
        result = disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert result.selected == (45, 9)
        assert result.drift == {
            "reference": "I46",
            "actual": "I45",
            "row_delta": -1,
            "col_delta": 0,
        }
        assert result.warnings[0][0] is IssueCode.ADDRESS_DRIFT
        assert "bergeser 1 baris" in result.warnings[0][1]

    def test_tie_break_prefers_smaller_row_then_column(self) -> None:
        cells = {(45, 9): "Label", (47, 9): "Label", (46, 8): "Label", (46, 10): "Label"}
        sheet = make_sheet(cells)
        keyword = by_address("Label", "I46")  # equidistant to all four
        result = disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert result.selected == (45, 9)  # smallest row among the ties


class TestNearKeyword:
    def test_picks_closest_to_comparison_keyword(self) -> None:
        sheet = make_sheet(BASE_CELLS)
        keyword = near("Total Produksi", "SECTION PRODUKSI")
        result = disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert result.selected == (25, 3)
        assert result.reference == "SECTION PRODUKSI"

    def test_missing_comparison_keyword_raises(self) -> None:
        sheet = make_sheet(BASE_CELLS)
        keyword = near("Total Produksi", "TIDAK ADA")
        with pytest.raises(ExtractionError) as exc:
            disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert exc.value.code is IssueCode.KEYWORD_NOT_FOUND
        assert "Pembanding" in exc.value.message

    def test_comparison_can_be_an_address(self) -> None:
        sheet = make_sheet(BASE_CELLS)
        keyword = KeywordConfig(
            text="Produksi Harian",
            is_unique=False,
            disambiguation=DisambiguationMode.NEAR_KEYWORD,
            reference_address="I90",
        )
        result = disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert result.selected == (94, 9)
        assert result.reference == "I90"


class TestNotNearKeyword:
    def test_drops_near_occurrences_keeps_far_one(self) -> None:
        sheet = make_sheet(BASE_CELLS)  # C5 is 4 cells from SUMMARY, C25 is 24 away
        keyword = not_near("Total Produksi", "SUMMARY")
        result = disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert result.selected == (25, 3)
        assert result.mode == "not_near_keyword"

    def test_all_near_raises_key_not_found(self) -> None:
        sheet = make_sheet(BASE_CELLS)
        keyword = not_near("Total Produksi", "SUMMARY", radius=30)  # both are within 30
        with pytest.raises(ExtractionError) as exc:
            disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert exc.value.code is IssueCode.KEYWORD_NOT_FOUND
        assert "Semua kemunculan" in exc.value.message

    def test_two_leftovers_raise_ambiguous(self) -> None:
        cells = dict(BASE_CELLS)
        cells[(60, 3)] = "Total Produksi"  # also far from SUMMARY
        sheet = make_sheet(cells)
        keyword = not_near("Total Produksi", "SUMMARY")
        with pytest.raises(ExtractionError) as exc:
            disambiguate(sheet.find_positions(keyword), keyword, sheet)
        assert exc.value.code is IssueCode.AMBIGUOUS_AFTER_DISAMBIGUATION
        assert exc.value.candidates == ["C25", "C60"]


def test_address_of_roundtrip() -> None:
    assert address_of((45, 9)) == "I45"
    assert address_of((1, 1)) == "A1"
