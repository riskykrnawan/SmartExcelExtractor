"""Bulk mapping: draft fields from a sample sheet, and CSV import/export.

See docs/SPEC.md (revisi v2, point 3): `mapping suggest` drafts a field list from one
sample sheet, `mapping export` / `mapping import` move a mapping as CSV. Only the
simple settings travel in CSV; match mode and disambiguation stay in the JSON profile.
"""
from __future__ import annotations

import csv
import re
import sys
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from .cell_index import build_sheet_data, load_workbook_pair
from .models import (
    DataType,
    FieldConfig,
    KeywordConfig,
    MatchMode,
    Profile,
    SheetConfig,
    SourceConfig,
    ValueDirection,
)
from .profiles import format_validation_error

#: Columns of one mapping row, in the order they are written.
CSV_COLUMNS = (
    "folder",
    "sheet",
    "output_name",
    "row_keyword",
    "col_keyword",
    "direction",
    "offset",
    "data_type",
    "allow_empty",
)

#: Longest text still treated as a label rather than prose.
_MAX_LABEL = 60

#: Fallback output name for a label that has no usable letters or digits.
_FALLBACK_NAME = "nilai"


class MappingError(Exception):
    """A mapping problem with a message meant for non-technical users."""


def suggest_fields(file_path: Path, sheet_title: str) -> list[FieldConfig]:
    """Draft fields from one sample sheet: labels with a value on the right or below.

    The drafts are a starting point for the user to review; keywords match exactly,
    and no column keyword is set (the value sits right of, or below, the label).
    """
    wb = load_workbook_pair(file_path)
    try:
        if sheet_title not in wb.sheet_titles():
            raise MappingError(f"Sheet '{sheet_title}' tidak ada di file '{file_path.name}'.")
        sheet = build_sheet_data(
            wb.values_wb[sheet_title], wb.formulas_wb[sheet_title], sheet_title
        )
    finally:
        wb.close()

    drafts: list[FieldConfig] = []
    used: set[str] = set()
    for row, col in sorted(sheet.values):
        label = sheet.value_at(row, col).value
        if not isinstance(label, str) or not _is_label(label):
            continue
        for direction, target in (
            (ValueDirection.RIGHT, (row, col + 1)),
            (ValueDirection.DOWN, (row + 1, col)),
        ):
            value = sheet.value_at(*target).value
            if not _has_value(value):
                continue
            name = _unique_name(label, used)
            used.add(name)
            drafts.append(
                FieldConfig(
                    output_name=name,
                    row_keyword=KeywordConfig(text=label.strip(), match_mode=MatchMode.EXACT),
                    value_direction=direction,
                    data_type=_data_type(value),
                )
            )
            break
    return drafts


def suggest_csv(
    file_path: Path, sheet_title: str, folder: str, path: Path | None = None
) -> list[dict[str, str]]:
    """Draft mapping for one sheet, written as importable CSV rows (or printed)."""
    rows = [
        _row(folder, sheet_title, field)
        for field in suggest_fields(file_path, sheet_title)
    ]
    write_csv(rows, path)
    return rows


def export_csv(profile: Profile, path: Path | None = None) -> list[dict[str, str]]:
    """Write the mapping of every enabled source of `profile` as CSV rows."""
    rows = [
        _row(source.folder, sheet.name, field)
        for source in profile.sources
        for sheet in source.sheets
        for field in sheet.fields
    ]
    write_csv(rows, path)
    return rows


def write_csv(rows: list[dict[str, str]], path: Path | None = None) -> None:
    """Write mapping rows to `path`, or to the standard output when `path` is None."""
    if path is None:
        writer = csv.DictWriter(sys.stdout, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def import_csv(path: Path) -> list[SourceConfig]:
    """Read a mapping CSV back into sources; every problem gets a plain message."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        raise MappingError(f"File mapping '{path.name}' tidak bisa dibaca.") from None
    reader = csv.DictReader(text.splitlines())
    columns = reader.fieldnames or []
    missing = [name for name in ("folder", "sheet", "output_name") if name not in columns]
    if missing:
        raise MappingError(
            f"File mapping '{path.name}' tidak memuat kolom: {', '.join(missing)}. "
            f"Kolom yang dipakai: {', '.join(CSV_COLUMNS)}."
        )

    folders: dict[str, dict[str, list[FieldConfig]]] = {}
    for line, row in enumerate(reader, start=2):
        try:
            folder = (row.get("folder") or "").strip()
            sheet_name = (row.get("sheet") or "").strip()
            if not folder or not sheet_name:
                raise MappingError("Nama folder atau sheet belum diisi.")
            field = _field_from_row(row)
        except (MappingError, ValueError) as exc:
            detail = "; ".join(format_validation_error(exc)) if isinstance(exc, ValidationError) else str(exc)
            raise MappingError(f"Baris {line} di '{path.name}': {detail}") from exc
        folders.setdefault(folder, {}).setdefault(sheet_name, []).append(field)

    if not folders:
        raise MappingError(f"File mapping '{path.name}' tidak memuat satu baris pun.")
    return [
        SourceConfig(
            folder=folder,
            sheets=[SheetConfig(name=name, fields=fields) for name, fields in sheets.items()],
        )
        for folder, sheets in folders.items()
    ]


def _field_from_row(row: dict[str, str | None]) -> FieldConfig:
    """One CSV line as a field rule (settings outside the CSV keep their defaults)."""
    offset = (row.get("offset") or "").strip() or "1"
    if not offset.isdigit() or int(offset) < 1:
        raise MappingError(f"Isian offset '{offset}' bukan angka 1 atau lebih.")
    col_text = (row.get("col_keyword") or "").strip()
    return FieldConfig(
        output_name=(row.get("output_name") or "").strip(),
        row_keyword=KeywordConfig(text=(row.get("row_keyword") or "").strip()),
        col_keyword=KeywordConfig(text=col_text) if col_text else None,
        value_direction=ValueDirection((row.get("direction") or "right").strip().lower()),
        value_offset=int(offset),
        data_type=DataType((row.get("data_type") or "any").strip().lower()),
        allow_empty=(row.get("allow_empty") or "").strip().lower() in {"1", "true", "ya", "yes"},
    )


def _row(folder: str, sheet_name: str, field: FieldConfig) -> dict[str, str]:
    """One field as a flat CSV row."""
    return {
        "folder": folder,
        "sheet": sheet_name,
        "output_name": field.output_name,
        "row_keyword": field.row_keyword.text,
        "col_keyword": field.col_keyword.text if field.col_keyword else "",
        "direction": field.value_direction.value,
        "offset": str(field.value_offset),
        "data_type": field.data_type.value,
        "allow_empty": "true" if field.allow_empty else "false",
    }


def _is_label(text: str) -> bool:
    """Short single-line text: a label, not a paragraph or a long note."""
    stripped = text.strip()
    return bool(stripped) and len(stripped) <= _MAX_LABEL and "\n" not in stripped


def _has_value(value: object) -> bool:
    """True when the cell next to a label really holds something."""
    return value is not None and not (isinstance(value, str) and not value.strip())


def _data_type(value: object) -> DataType:
    """Expected value type for a draft field, from the sample cell."""
    if isinstance(value, datetime | date):
        return DataType.DATE
    if isinstance(value, int | float) and not isinstance(value, bool):
        return DataType.NUMBER
    return DataType.ANY


def _unique_name(label: str, used: set[str]) -> str:
    """A safe output name from a label; repeats get a number suffix."""
    base = re.sub(r"[^A-Za-z0-9]+", "_", label.strip()).strip("_").lower() or _FALLBACK_NAME
    name = base
    index = 2
    while name in used:
        name = f"{base}_{index}"
        index += 1
    return name

