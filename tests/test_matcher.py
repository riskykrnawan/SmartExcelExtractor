"""Normalization and keyword matching modes."""
from __future__ import annotations

from datetime import datetime

from core.matcher import matches_text, normalize_text
from core.models import KeywordConfig, MatchMode


def kw(
    text: str, mode: MatchMode = MatchMode.EXACT, case_sensitive: bool = False
) -> KeywordConfig:
    """Build a keyword config for tests."""
    return KeywordConfig(text=text, match_mode=mode, case_sensitive=case_sensitive)


class TestNormalize:
    """normalize_text: trim, collapse spaces, strip newlines, keep numbers."""

    def test_newlines_and_extra_spaces_collapse(self) -> None:
        assert normalize_text("  Produksi \n Harian\t  ") == "Produksi Harian"

    def test_integral_float_keeps_number(self) -> None:
        assert normalize_text(1523.0) == "1523"

    def test_float_keeps_fraction(self) -> None:
        assert normalize_text(1523.5) == "1523.5"

    def test_none_is_empty(self) -> None:
        assert normalize_text(None) == ""

    def test_datetime_becomes_iso_text(self) -> None:
        assert normalize_text(datetime(2026, 10, 14, 7, 55)) == "2026-10-14T07:55:00"


class TestExactMode:
    """'Sama persis': equal after normalization, case-insensitive by default."""

    def test_matches_ignoring_case_and_spacing(self) -> None:
        assert matches_text(normalize_text("produksi  harian"), kw("Produksi Harian"))

    def test_does_not_match_extra_word(self) -> None:
        assert not matches_text(normalize_text("Produksi Harian Total"), kw("Produksi Harian"))

    def test_keyword_double_space_also_normalized(self) -> None:
        assert matches_text("Produksi Harian", kw("Produksi  Harian"))

    def test_case_sensitive_option(self) -> None:
        keyword = kw("Produksi Harian", case_sensitive=True)
        assert matches_text("Produksi Harian", keyword)
        assert not matches_text("produksi harian", keyword)

    def test_number_cell_matches_number_keyword(self) -> None:
        assert matches_text(normalize_text(1523), kw("1523"))
        assert not matches_text(normalize_text(1524), kw("1523"))


class TestContainsStartsEnds:
    """The three partial-match modes."""

    def test_contains(self) -> None:
        keyword = kw("Harian", MatchMode.CONTAINS)
        assert matches_text("Rekap Laporan Harian", keyword)
        assert not matches_text("Rekap Laporan Haria", keyword)

    def test_starts_with(self) -> None:
        keyword = kw("Laporan", MatchMode.STARTS_WITH)
        assert matches_text("Laporan Harian", keyword)
        assert not matches_text("Rekap Laporan", keyword)

    def test_ends_with(self) -> None:
        keyword = kw("Harian", MatchMode.ENDS_WITH)
        assert matches_text("Laporan Harian", keyword)
        assert not matches_text("Harian Rekap", keyword)

    def test_all_modes_case_insensitive_by_default(self) -> None:
        assert matches_text("LAPORAN HARIAN", kw("lapor", MatchMode.CONTAINS))


class TestRegexMode:
    """Mode Lanjutan (regex): raw pattern, normalized cell text."""

    def test_pattern_matches(self) -> None:
        keyword = kw(r"Produksi\s+\d+", MatchMode.REGEX)
        assert matches_text(normalize_text("Produksi  10"), keyword)

    def test_pattern_rejects_other_text(self) -> None:
        keyword = kw(r"Produksi\s+\d+", MatchMode.REGEX)
        assert not matches_text(normalize_text("Total Lain"), keyword)

    def test_case_insensitive_by_default(self) -> None:
        keyword = kw("produksi", MatchMode.REGEX)
        assert matches_text("PRODUKSI HARIAN", keyword)
