"""Selecting one candidate cell when a keyword appears multiple times.

Distance metric: Chebyshev (max of row/col delta). Rows and columns weigh the
same, so "radius 10" reads naturally as "within the surrounding 10 cells", and
one number is easy to explain to non-technical users. Ties break deterministically
to the smaller row, then the smaller column.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field

from openpyxl.utils import coordinate_to_tuple, get_column_letter

from .audit import ExtractionError, IssueCode
from .cell_index import SheetData
from .models import DisambiguationMode, KeywordConfig


def address_of(pos: tuple[int, int]) -> str:
    """Cell address for a (row, col) pair, e.g. (45, 9) -> 'I45'."""
    return f"{get_column_letter(pos[1])}{pos[0]}"


def address_to_pos(address: str) -> tuple[int, int]:
    """Parse a validated address like 'I45' into (row, col)."""
    row, col = coordinate_to_tuple(address.upper())
    return int(row), int(col)


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Chebyshev distance: cells within `r` of `b` form an r x r box around it."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _nearest(positions: list[tuple[int, int]], target: tuple[int, int]) -> tuple[int, int]:
    """Pick closest to target; tie-break smaller row, then smaller column."""
    return min(positions, key=lambda p: (_distance(p, target), p[0], p[1]))


@dataclass
class DisambiguationResult:
    """The chosen cell plus everything the audit needs to explain the choice."""

    selected: tuple[int, int]
    candidates: list[tuple[int, int]]
    mode: str
    reference: str | None = None
    drift: dict[str, object] | None = None
    warnings: list[tuple[IssueCode, str]] = dataclass_field(default_factory=list)


def _comparison_positions(
    sheet: SheetData, keyword: KeywordConfig
) -> tuple[list[tuple[int, int]], str]:
    """Resolve the comparison reference (keyword or address) of a keyword."""
    if keyword.reference_keyword is not None and keyword.reference_keyword.text:
        positions = sheet.find_positions(keyword.reference_keyword)
        if not positions:
            raise ExtractionError(
                IssueCode.KEYWORD_NOT_FOUND,
                f"Pembanding '{keyword.reference_keyword.text}' tidak ditemukan di sheet ini.",
            )
        return positions, keyword.reference_keyword.text
    if keyword.reference_address:
        return [address_to_pos(keyword.reference_address)], keyword.reference_address
    # The model validator guarantees a reference exists; guard for safety.
    raise ExtractionError(IssueCode.INTERNAL_ERROR, "Pembanding belum diatur.")


def disambiguate(
    candidates: list[tuple[int, int]],
    keyword: KeywordConfig,
    sheet: SheetData,
) -> DisambiguationResult:
    """Pick exactly one cell, or raise ExtractionError. Never guess silently."""
    positions = sorted(set(candidates))
    if not positions:
        raise ExtractionError(
            IssueCode.KEYWORD_NOT_FOUND,
            f"Tulisan '{keyword.text}' tidak ditemukan di sheet ini.",
            [],
        )
    if keyword.is_unique:
        if len(positions) > 1:
            addrs = ", ".join(address_of(p) for p in positions)
            raise ExtractionError(
                IssueCode.UNIQUE_VIOLATION,
                f"Tulisan '{keyword.text}' diatur hanya muncul sekali, tetapi ditemukan "
                f"{len(positions)} kali: {addrs}.",
                [address_of(p) for p in positions],
            )
        return DisambiguationResult(selected=positions[0], candidates=positions, mode="unique")

    mode = keyword.disambiguation
    if mode is None:
        raise ExtractionError(IssueCode.INTERNAL_ERROR, "Cara memilih kemunculan belum diatur.")

    if mode is DisambiguationMode.BY_ADDRESS:
        if not keyword.reference_address:
            raise ExtractionError(IssueCode.INTERNAL_ERROR, "Alamat sel acuan belum diisi.")
        ref = address_to_pos(keyword.reference_address)
        selected = _nearest(positions, ref)
        drift: dict[str, object] | None = None
        warnings: list[tuple[IssueCode, str]] = []
        if selected != ref:
            row_delta = selected[0] - ref[0]
            col_delta = selected[1] - ref[1]
            drift = {
                "reference": address_of(ref),
                "actual": address_of(selected),
                "row_delta": row_delta,
                "col_delta": col_delta,
            }
            parts: list[str] = []
            if row_delta:
                parts.append(f"{abs(row_delta)} baris")
            if col_delta:
                parts.append(f"{abs(col_delta)} kolom")
            warnings.append(
                (
                    IssueCode.ADDRESS_DRIFT,
                    f"Keyword '{keyword.text}' ditemukan di {address_of(selected)}, "
                    f"acuan {address_of(ref)} (bergeser {' dan '.join(parts)}).",
                )
            )
        return DisambiguationResult(
            selected=selected,
            candidates=positions,
            mode="by_address",
            reference=address_of(ref),
            drift=drift,
            warnings=warnings,
        )

    ref_positions, ref_desc = _comparison_positions(sheet, keyword)
    if mode is DisambiguationMode.NEAR_KEYWORD:
        selected = min(
            positions,
            key=lambda p: (min(_distance(p, r) for r in ref_positions), p[0], p[1]),
        )
        return DisambiguationResult(
            selected=selected, candidates=positions, mode="near_keyword", reference=ref_desc
        )

    # NOT_NEAR_KEYWORD: drop everything within `radius` of the reference.
    radius = keyword.radius
    remaining = [p for p in positions if all(_distance(p, r) > radius for r in ref_positions)]
    if not remaining:
        addrs = ", ".join(address_of(p) for p in positions)
        raise ExtractionError(
            IssueCode.KEYWORD_NOT_FOUND,
            f"Semua kemunculan ({addrs}) berada dekat dengan pembanding '{ref_desc}' "
            f"(dalam {radius} sel).",
            [address_of(p) for p in positions],
        )
    if len(remaining) > 1:
        addrs = ", ".join(address_of(p) for p in remaining)
        raise ExtractionError(
            IssueCode.AMBIGUOUS_AFTER_DISAMBIGUATION,
            f"Setelah membuang yang dekat dengan pembanding '{ref_desc}', masih tersisa "
            f"{len(remaining)} kemunculan: {addrs}. Tidak bisa menebak mana yang dipakai.",
            [address_of(p) for p in remaining],
        )
    return DisambiguationResult(
        selected=remaining[0],
        candidates=positions,
        mode="not_near_keyword",
        reference=ref_desc,
    )

