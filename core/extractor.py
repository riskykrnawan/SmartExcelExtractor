"""Extraction engine: profile -> sources -> sheet templates -> items (v2).

One failing field never stops the others; every failure becomes an audit issue.
Deterministic: same profile + same input files + same `now` -> identical JSON.
An item is one sheet (daily report) or one table row, identified by `Profile.key`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .audit import (
    ExtractionError,
    FieldAudit,
    FieldResult,
    Issue,
    IssueCode,
    Item,
    KeywordAudit,
    RunResult,
    make_issue,
)
from .cell_index import (
    ExcelFileError,
    SheetData,
    ValueRead,
    build_sheet_data,
    list_excel_files,
    load_workbook_pair,
)
from .disambiguator import DisambiguationResult, address_of, disambiguate
from .matcher import matches_text, normalize_text
from .models import (
    DataType,
    FieldConfig,
    KeyConfig,
    KeySource,
    KeywordConfig,
    Profile,
    SheetConfig,
    SheetMode,
    SourceConfig,
    ValueDirection,
)
from .output import summarize

logger = logging.getLogger(__name__)

_EXCEL_ERRORS = frozenset({"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NULL!", "#NUM!"})

_TYPE_LABELS = {DataType.NUMBER: "angka", DataType.TEXT: "teks", DataType.DATE: "tanggal"}

# Month names as they really appear in Indonesian reports (plus the English ones).
_ID_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7,
    "agu": 8, "ags": 8, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11,
    "des": 12, "dec": 12,
}

# Sheet-name patterns (`key.format`): tokens are replaced, everything else is literal.
_DATE_TOKENS: tuple[tuple[str, str], ...] = (
    ("YYYY", "y4"), ("YY", "y2"), ("MMMM", "mon"), ("MMM", "mon"), ("MM", "m"), ("M", "m"),
    ("DD", "d"), ("D", "d"),
)
_TOKEN_GROUPS = {
    "y4": r"(?P<y4>\d{4})", "y2": r"(?P<y2>\d{2})", "mon": r"(?P<mon>[A-Za-z]+)",
    "m": r"(?P<m>\d{1,2})", "d": r"(?P<d>\d{1,2})",
}


@dataclass
class _FileRef:
    """File provenance shared by every field of one source."""

    folder: str
    name: str
    modified: str | None


@dataclass
class _Outcome:
    """Result + audit trail + issues for one field."""

    result: FieldResult
    audit: FieldAudit
    issues: list[Issue] = dc_field(default_factory=list)


@dataclass
class _KeywordPick:
    """One keyword search: its audit trail, plus the cell it resolved to (if any)."""

    audit: KeywordAudit
    selected: tuple[int, int] | None = None

    @property
    def address(self) -> str | None:
        """Address of the selected cell, or None when the keyword was not resolved."""
        return address_of(self.selected) if self.selected is not None else None


@dataclass
class _KeyResult:
    """The identity of one item, or the reason it could not be read."""

    key: str | None
    issue: Issue | None = None


@dataclass
class _SheetResult:
    """Everything one sheet template produced."""

    items: list[Item] = dc_field(default_factory=list)
    outcomes: list[_Outcome] = dc_field(default_factory=list)
    issues: list[Issue] = dc_field(default_factory=list)


@dataclass
class _SourceResult:
    """Everything one source folder produced."""

    items: list[Item] = dc_field(default_factory=list)
    outcomes: list[_Outcome] = dc_field(default_factory=list)
    issues: list[Issue] = dc_field(default_factory=list)
    unmatched: list[dict[str, str]] = dc_field(default_factory=list)


def run_extraction(
    profile: Profile,
    *,
    now: datetime | None = None,
    period_year: int | None = None,
    period_month: int | None = None,
) -> RunResult:
    """Extract every enabled sheet template of `profile` into items.

    `period_year` / `period_month` are the manual run input for keys taken from a
    sheet name that only carries the day (see docs/SPEC.md revision v2).

    Raises only for a broken profile (validate before calling). Single field,
    sheet, and file failures are recorded as issues instead of propagating.
    """
    run_at = now or datetime.now().astimezone()
    items: list[Item] = []
    outcomes: list[_Outcome] = []
    source_issues: list[Issue] = []
    unmatched: list[dict[str, str]] = []
    root = Path(profile.input_root) if profile.input_root else None
    for source in profile.sources:
        if not source.enabled:
            continue
        part = _run_source(source, root, profile.key, period_year, period_month)
        items.extend(part.items)
        outcomes.extend(part.outcomes)
        source_issues.extend(part.issues)
        unmatched.extend(part.unmatched)

    field_issues = [issue for outcome in outcomes for issue in outcome.issues]
    meta: dict[str, Any] = {
        "app_version": __version__,
        "profile": profile.name,
        "run_at": run_at.isoformat(timespec="seconds"),
        # Local path: used by the app (mini spreadsheet), never written to the output file.
        "input_root": profile.input_root,
        "summary": summarize(items),
        "unmatched_sheets": unmatched,
    }
    audit: dict[str, Any] = {
        "fields": [outcome.audit.to_dict() for outcome in outcomes],
        "issues": [issue.to_dict() for issue in source_issues + field_issues],
    }
    data: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        # Flat view for previews: a repeated result name keeps the first; the UI table
        # and the output file read `items`, so every sheet's entry stays available.
        data.setdefault(outcome.result.field_name, outcome.result.to_dict())
    return RunResult(meta=meta, data=data, audit=audit, items=items)


def _file_mtime(path: Path) -> str | None:
    """ISO timestamp of the last modification, or None when unreadable."""
    try:
        return (
            datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        )
    except OSError:
        return None


def sheet_matches(title: str, cfg: SheetConfig) -> bool:
    """True when a real sheet title matches the configured sheet name/pattern.

    Public because the interface marks the rows of sheets that are not in the sample
    file yet (SPEC v2 poin 2): the colour must follow exactly the engine's rule.
    """
    probe = KeywordConfig(text=cfg.name, match_mode=cfg.match_mode, is_unique=True)
    return matches_text(normalize_text(title), probe)


def _failed_outcomes(
    sheet_cfg: SheetConfig, folder: str, code: IssueCode, message: str, file_ref: _FileRef | None
) -> list[_Outcome]:
    """One failed field per configured field: the sheet never ran."""
    return [
        _failed_outcome(cfg, sheet_cfg.name, folder, code, message, file_ref)
        for cfg in sheet_cfg.fields
    ]


def _absorb_failure(
    result: _SourceResult,
    sheet_cfg: SheetConfig,
    folder: str,
    file_ref: _FileRef | None,
    code: IssueCode,
    message: str,
) -> None:
    """Record a template that never ran: one item with `key: null`, every field failed."""
    outcomes = _failed_outcomes(sheet_cfg, folder, code, message, file_ref)
    result.items.append(
        _item_from(
            outcomes,
            sheet_cfg.name,
            folder,
            file_ref.name if file_ref else None,
            file_ref.modified if file_ref else None,
            _KeyResult(None),
        )
    )
    result.outcomes.extend(outcomes)
    result.issues.extend(issue for outcome in outcomes for issue in outcome.issues)


def _run_source(
    source: SourceConfig,
    root: Path | None,
    key_cfg: KeyConfig,
    year: int | None,
    month: int | None,
) -> _SourceResult:
    """Resolve one source folder's file, then extract every sheet template in it."""
    result = _SourceResult()
    if not any(sheet.fields for sheet in source.sheets):
        return result

    folder: Path | None = root / source.folder if root is not None else None
    files = list_excel_files(folder) if folder is not None else []
    file_path = files[0] if files else None

    file_code: IssueCode | None
    file_msg: str | None
    if folder is None:
        file_code = IssueCode.FILE_NOT_FOUND
        file_msg = f"Folder induk belum diatur untuk sumber '{source.folder}'."
    elif file_path is None:
        file_code = IssueCode.FILE_NOT_FOUND
        file_msg = f"Tidak ditemukan file Excel (.xlsx/.xlsm) di folder '{source.folder}'."
    else:
        file_code = None
        file_msg = None
        if len(files) > 1:
            names = ", ".join(sorted(path.name for path in files))
            result.issues.append(
                make_issue(
                    None,
                    IssueCode.MULTIPLE_FILES,
                    f"Folder '{source.folder}' berisi {len(files)} file Excel ({names}). "
                    f"Yang dipakai: {file_path.name} (paling baru diubah).",
                )
            )

    if file_code is not None and file_msg is not None:
        for sheet_cfg in source.sheets:
            _absorb_failure(result, sheet_cfg, source.folder, None, file_code, file_msg)
        return result

    if file_path is None:  # unreachable; narrows the type for the checker
        return result
    file_ref = _FileRef(folder=source.folder, name=file_path.name, modified=_file_mtime(file_path))
    try:
        wb = load_workbook_pair(file_path)
    except ExcelFileError as exc:
        for sheet_cfg in source.sheets:
            _absorb_failure(
                result, sheet_cfg, source.folder, file_ref, IssueCode.FILE_UNREADABLE, str(exc)
            )
        return result

    cache: dict[str, SheetData] = {}
    try:
        titles = wb.sheet_titles()
        used: set[str] = set()
        for sheet_cfg in source.sheets:
            matched = [title for title in titles if sheet_matches(title, sheet_cfg)]
            if not matched:
                # A sheet that is not there yet is not an error (daily reports): the field
                # is not reported at all, one warning per template is enough (SPEC v2 poin 2).
                result.issues.append(
                    make_issue(
                        None,
                        IssueCode.SHEET_ABSENT,
                        f"Sheet '{sheet_cfg.name}' tidak ada di '{file_ref.name}'. "
                        f"Sheet yang tersedia: {', '.join(titles)}. "
                        "Sheet yang belum ada bukan error.",
                    )
                )
                continue
            if not sheet_cfg.every_sheet and len(matched) > 1:
                _absorb_failure(
                    result,
                    sheet_cfg,
                    source.folder,
                    file_ref,
                    IssueCode.SHEET_AMBIGUOUS,
                    f"Nama sheet '{sheet_cfg.name}' cocok dengan {len(matched)} sheet: "
                    f"{', '.join(matched)}. Pakai nama yang lebih spesifik.",
                )
                used.update(matched)
                continue

            for title in matched if sheet_cfg.every_sheet else matched[:1]:
                used.add(title)
                if (
                    key_cfg.source is KeySource.SHEET_NAME
                    and key_cfg.format
                    and _date_parts_from(title, key_cfg.format) is None
                ):
                    _mark_unmatched(result, file_ref, title, key_cfg)
                    continue
                if title not in cache:
                    cache[title] = build_sheet_data(
                        wb.values_wb[title], wb.formulas_wb[title], title
                    )
                part = _extract_sheet(
                    sheet_cfg, cache[title], title, file_ref, key_cfg, file_ref.name, year, month
                )
                result.items.extend(part.items)
                result.outcomes.extend(part.outcomes)
                result.issues.extend(part.issues)

        for title in titles:
            if title not in used:
                # Not used by the profile: listed in the audit, but never an issue
                # (decision 2026-10-15 - an unused sheet is not a problem).
                result.unmatched.append(
                    {
                        "folder": file_ref.folder,
                        "file": file_ref.name,
                        "sheet": title,
                        "reason": "tidak cocok template mana pun",
                    }
                )
    finally:
        wb.close()
    return result


def _mark_unmatched(
    result: _SourceResult, file_ref: _FileRef, title: str, key_cfg: KeyConfig
) -> None:
    """A sheet claimed by a template but failing the identity pattern: never silent."""
    reason = f"nama sheet tidak cocok pola identitas '{key_cfg.format}'"
    result.unmatched.append(
        {"folder": file_ref.folder, "file": file_ref.name, "sheet": title, "reason": reason}
    )
    result.issues.append(
        make_issue(
            None,
            IssueCode.SHEET_UNMATCHED,
            f"Sheet '{title}' di '{file_ref.name}' tidak dipakai: {reason}.",
        )
    )



def _extract_sheet(
    sheet_cfg: SheetConfig,
    sheet: SheetData,
    title: str,
    file_ref: _FileRef,
    key_cfg: KeyConfig,
    file_name: str,
    year: int | None,
    month: int | None,
) -> _SheetResult:
    """One sheet template against one real sheet: one item per sheet, or per data row."""
    if sheet_cfg.mode is SheetMode.ROWS:
        return _extract_rows(sheet_cfg, sheet, title, file_ref, key_cfg, file_name, year, month)
    outcomes: list[_Outcome] = []
    for cfg in sheet_cfg.fields:
        try:
            outcomes.append(_extract_field(sheet, title, cfg, file_ref))
        except Exception:
            logger.exception("Unexpected error extracting field %s", cfg.output_name)
            outcomes.append(
                _failed_outcome(
                    cfg,
                    title,
                    file_ref.folder,
                    IssueCode.INTERNAL_ERROR,
                    "Terjadi kesalahan tak terduga saat mengambil data ini. "
                    "Detail lengkap ada di file log.",
                    file_ref,
                )
            )
    key = _key_for_sheet(key_cfg, sheet, title, file_name, year, month)
    item = _item_from(outcomes, title, file_ref.folder, file_ref.name, file_ref.modified, key)
    return _SheetResult([item], outcomes, [key.issue] if key.issue else [])


def _extract_rows(
    sheet_cfg: SheetConfig,
    sheet: SheetData,
    title: str,
    file_ref: _FileRef,
    key_cfg: KeyConfig,
    file_name: str,
    year: int | None,
    month: int | None,
) -> _SheetResult:
    """One item per data row, found from the key column content (not row positions).

    A cumulative table grows by rows, so the same mapping handles a file that stops
    at the 15th and one that reaches the 31st (docs/SPEC.md revision v2).
    """
    if not key_cfg.label:
        return _rows_failed(
            sheet_cfg,
            title,
            file_ref,
            "Profil belum menentukan kolom identitas untuk data berbentuk tabel.",
        )
    key_issues: list[Issue] = []
    key_kw = KeywordConfig(text=key_cfg.label, is_unique=True)
    key_pick = _pick_keyword(sheet, key_kw, key_issues, None)
    if key_pick is None or key_pick.selected is None:
        return _rows_failed(
            sheet_cfg,
            title,
            file_ref,
            f"Kolom identitas '{key_cfg.label}' tidak ada (harus muncul tepat satu kali) di "
            f"sheet '{title}'.",
        )

    col_picks: dict[str, _KeywordPick | None] = {}
    col_issues: dict[str, list[Issue]] = {}
    for cfg in sheet_cfg.fields:
        issues: list[Issue] = []
        col_picks[cfg.output_name] = _pick_keyword(sheet, cfg.col_keyword, issues, cfg.output_name)
        col_issues[cfg.output_name] = issues

    items: list[Item] = []
    outcomes: list[_Outcome] = []
    issues_found: list[Issue] = list(key_issues)
    key_col = key_pick.selected[1]
    for row in _data_rows(sheet, key_col, key_pick.selected[0], key_cfg.type):
        row_pos = (row, key_col)
        row_audit = _keyword_audit(key_kw)
        row_audit.selected = address_of(row_pos)
        key = _key_for_row(key_cfg, sheet, row_pos, file_ref, title, file_name, year, month)
        row_outcomes = [
            _field_outcome(
                sheet,
                cfg,
                title,
                file_ref,
                list(col_issues[cfg.output_name]),
                col_picks[cfg.output_name],
                _KeywordPick(row_audit, row_pos),
            )
            for cfg in sheet_cfg.fields
        ]
        items.append(
            _item_from(row_outcomes, title, file_ref.folder, file_ref.name, file_ref.modified, key)
        )
        outcomes.extend(row_outcomes)
        if key.issue is not None:
            issues_found.append(key.issue)
    return _SheetResult(items, outcomes, issues_found)


def _rows_failed(
    sheet_cfg: SheetConfig, title: str, file_ref: _FileRef, message: str
) -> _SheetResult:
    """The table could not be read at all: one failed item, never silence."""
    issue = make_issue(None, IssueCode.KEY_NOT_FOUND, message)
    outcomes = [
        _failed_outcome(cfg, title, file_ref.folder, IssueCode.KEY_NOT_FOUND, message, file_ref)
        for cfg in sheet_cfg.fields
    ]
    item = _item_from(
        outcomes, title, file_ref.folder, file_ref.name, file_ref.modified, _KeyResult(None, issue)
    )
    return _SheetResult([item], outcomes, [issue])



def _data_rows(sheet: SheetData, key_col: int, header_row: int, key_type: DataType) -> list[int]:
    """Rows below the header whose key cell really holds an identity (dates by default)."""
    rows: list[int] = []
    for row, col in sorted(sheet.values):
        if row <= header_row or col != key_col:
            continue
        value = sheet.value_at(row, key_col).value
        readable = (
            _as_date(value) is not None
            if key_type is DataType.DATE
            else value is not None and str(value).strip() != ""
        )
        if readable:
            rows.append(row)
    return rows


def _item_from(
    outcomes: list[_Outcome],
    sheet: str,
    folder: str | None,
    file: str | None,
    modified: str | None,
    key: _KeyResult,
) -> Item:
    """Turn one sheet's (or one table row's) field outcomes into an output item."""
    fields = {outcome.result.field_name: outcome.result for outcome in outcomes}
    issues = {outcome.result.field_name: outcome.issues for outcome in outcomes}
    levels = [result.status for result in fields.values()]
    if key.issue is not None:
        levels.append(key.issue.level)
    status = "error" if "error" in levels else "warning" if "warning" in levels else "ok"
    return Item(
        key=key.key,
        status=status,
        folder=folder,
        file=file,
        file_modified=modified,
        sheet=sheet,
        fields=fields,
        issues=issues,
        key_issue=key.issue,
    )


def _failed_outcome(
    cfg: FieldConfig,
    sheet_name: str,
    folder: str,
    code: IssueCode,
    message: str,
    file_ref: _FileRef | None,
) -> _Outcome:
    """A field that could not run at all (file/sheet level failure)."""
    audit = FieldAudit(field_name=cfg.output_name, status="error", errors=[message])
    result = FieldResult(
        field_name=cfg.output_name,
        value=None,
        status="error",
        folder=folder,
        file=file_ref.name if file_ref else None,
        file_modified=file_ref.modified if file_ref else None,
        sheet=sheet_name,
        value_address=None,
        row_keyword_address=None,
        col_keyword_address=None,
        raw_value=None,
        type_found="empty",
        merged=False,
        merged_range=None,
        hidden=False,
        from_formula=False,
    )
    return _Outcome(result, audit, [make_issue(cfg.output_name, code, message)])



def _extract_field(sheet: SheetData, title: str, cfg: FieldConfig, file_ref: _FileRef) -> _Outcome:
    """Extract one field from one sheet (one sheet = one item mode). Never raises."""
    issues: list[Issue] = []
    row_pick = _pick_keyword(sheet, cfg.row_keyword, issues, cfg.output_name)
    col_pick = (
        _pick_keyword(sheet, cfg.col_keyword, issues, cfg.output_name)
        if cfg.col_keyword is not None
        else None
    )
    return _field_outcome(sheet, cfg, title, file_ref, issues, col_pick, row_pick)


def _pick_keyword(
    sheet: SheetData, keyword: KeywordConfig | None, issues: list[Issue], field_name: str | None
) -> _KeywordPick | None:
    """Search + disambiguate one keyword, appending every resulting issue to `issues`.

    The audit trail is returned even when nothing was selected, so the reason is kept.
    """
    if keyword is None:
        return None
    audit = _keyword_audit(keyword)
    positions = sheet.find_positions(keyword)
    result, error = _try_disambiguate(positions, keyword, sheet)
    _fill_keyword_audit(audit, positions, result)
    if error is not None:
        _add_issue(issues, field_name, error.code, error.message)
    if result is None:
        return _KeywordPick(audit)
    for code, message in result.warnings:
        _add_issue(issues, field_name, code, message)
    return _KeywordPick(audit, result.selected)


def _field_outcome(
    sheet: SheetData,
    cfg: FieldConfig,
    title: str,
    file_ref: _FileRef,
    issues: list[Issue],
    col_pick: _KeywordPick | None,
    row_pick: _KeywordPick | None,
) -> _Outcome:
    """Read the value cell and turn everything found into a result + audit record.

    In rows mode `row_pick` is built from the table itself, so the reported row
    address is the key cell of that row.
    """
    row_audit = row_pick.audit if row_pick is not None else None
    col_audit = col_pick.audit if col_pick is not None else None
    row_pos = row_pick.selected if row_pick is not None else None
    row_address = row_pick.address if row_pick is not None else None
    col_pos = col_pick.selected if col_pick is not None else None
    col_address = col_pick.address if col_pick is not None else None
    if row_pos is None or (cfg.col_keyword is not None and col_pos is None):
        return _error_outcome(cfg, title, file_ref, issues, row_audit, col_audit, row_address)

    # Value cell: intersection of row/column keyword, or a shift from the row keyword.
    if col_pos is not None:
        target = (row_pos[0], col_pos[1])
    else:
        delta = _direction_delta(cfg.value_direction, cfg.value_offset)
        target = (row_pos[0] + delta[0], row_pos[1] + delta[1])
        col_address = None

    if target[0] >= 1 and target[1] >= 1:
        read = sheet.value_at(*target)
        value_address: str | None = address_of(target)
    else:
        read = ValueRead(value=None)
        value_address = None

    value = read.value
    # Merged cells: the value comes from the top-left anchor, which is the correct
    # value, so it is not a warning (docs/SPEC.md revision v2, point 1).
    if read.from_formula and value is None:
        _add_issue(
            issues,
            cfg.output_name,
            IssueCode.FORMULA_NOT_CALCULATED,
            f"Rumus di {value_address} belum dihitung oleh Excel, nilainya kosong.",
        )
    elif value is None or (isinstance(value, str) and not value.strip()):
        if not cfg.allow_empty:
            message = (
                f"Tidak ada nilai di {value_address}."
                if value_address
                else "Tidak ada nilai (posisi hasil geser di luar sheet)."
            )
            _add_issue(issues, cfg.output_name, IssueCode.EMPTY_VALUE, message)
    if isinstance(value, str) and value in _EXCEL_ERRORS:
        _add_issue(
            issues,
            cfg.output_name,
            IssueCode.EXCEL_ERROR_VALUE,
            f"Sel {value_address} berisi kesalahan Excel {value}.",
        )
    elif (
        value is not None
        and cfg.data_type is not DataType.ANY
        and _type_mismatch(value, cfg.data_type)
    ):
        _add_issue(
            issues,
            cfg.output_name,
            IssueCode.TYPE_MISMATCH,
            f"Nilai di {value_address} bukan {_TYPE_LABELS[cfg.data_type]} "
            f"(terbaca: {_type_of(value)}); nilai asli tetap disimpan.",
        )

    final_value = value.isoformat() if isinstance(value, datetime | date) else value
    audit = FieldAudit(
        field_name=cfg.output_name,
        status=_status_of(issues),
        row_keyword=row_audit,
        col_keyword=col_audit,
        warnings=_messages(issues, "warning"),
        errors=_messages(issues, "error"),
    )
    result = FieldResult(
        field_name=cfg.output_name,
        value=final_value,
        status=audit.status,
        folder=file_ref.folder,
        file=file_ref.name,
        file_modified=file_ref.modified,
        sheet=title,
        value_address=value_address,
        row_keyword_address=row_address,
        col_keyword_address=col_address,
        raw_value=str(value) if value is not None else None,
        type_found=_type_of(value),
        merged=read.merged,
        merged_range=read.merged_range,
        hidden=read.hidden,
        from_formula=read.from_formula,
    )
    return _Outcome(result, audit, issues)



def _error_outcome(
    cfg: FieldConfig,
    title: str,
    file_ref: _FileRef,
    issues: list[Issue],
    row_audit: KeywordAudit | None,
    col_audit: KeywordAudit | None,
    row_address: str | None,
) -> _Outcome:
    """A field whose keywords were not resolved: value stays None (never guessed)."""
    audit = FieldAudit(
        field_name=cfg.output_name,
        status=_status_of(issues),
        row_keyword=row_audit,
        col_keyword=col_audit,
        warnings=_messages(issues, "warning"),
        errors=_messages(issues, "error"),
    )
    result = FieldResult(
        field_name=cfg.output_name,
        value=None,
        status=audit.status,
        folder=file_ref.folder,
        file=file_ref.name,
        file_modified=file_ref.modified,
        sheet=title,
        value_address=None,
        row_keyword_address=row_address,
        col_keyword_address=None,
        raw_value=None,
        type_found="empty",
        merged=False,
        merged_range=None,
        hidden=False,
        from_formula=False,
    )
    return _Outcome(result, audit, issues)


def _keyword_audit(keyword: KeywordConfig) -> KeywordAudit:
    """Empty audit record for one keyword, filled as the extraction progresses."""
    return KeywordAudit(
        text=keyword.text, match_mode=keyword.match_mode.value, is_unique=keyword.is_unique
    )


def _try_disambiguate(
    positions: list[tuple[int, int]], keyword: KeywordConfig, sheet: SheetData
) -> tuple[DisambiguationResult | None, ExtractionError | None]:
    """Run disambiguation without raising, so both keywords can be audited."""
    try:
        return disambiguate(positions, keyword, sheet), None
    except ExtractionError as exc:
        return None, exc


def _fill_keyword_audit(
    audit: KeywordAudit, positions: list[tuple[int, int]], result: DisambiguationResult | None
) -> None:
    """Record every candidate plus the selection and its explanation."""
    audit.candidates = [address_of(pos) for pos in sorted(positions)]
    if result is not None:
        audit.selected = address_of(result.selected)
        audit.disambiguation = result.mode
        audit.reference = result.reference
        audit.drift = result.drift


def _add_issue(issues: list[Issue], field_name: str | None, code: IssueCode, message: str) -> None:
    """Append one issue to a field's (or the run's) issue list."""
    issues.append(make_issue(field_name, code, message))


def _status_of(issues: list[Issue]) -> str:
    """Field status from its issues: any error wins, then any warning."""
    if any(issue.level == "error" for issue in issues):
        return "error"
    return "warning" if issues else "ok"


def _messages(issues: list[Issue], level: str) -> list[str]:
    """Issue messages of one level, for the audit record."""
    return [issue.message for issue in issues if issue.level == level]


def _direction_delta(direction: ValueDirection, offset: int) -> tuple[int, int]:
    """Row/column shift for the 'value next to the label' mode."""
    if direction is ValueDirection.RIGHT:
        return (0, offset)
    if direction is ValueDirection.LEFT:
        return (0, -offset)
    if direction is ValueDirection.DOWN:
        return (offset, 0)
    return (-offset, 0)


def _type_of(value: Any) -> str:
    """JSON-safe type name of a raw cell value."""
    if value is None:
        return "empty"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, datetime | date):
        return "date"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "error" if value in _EXCEL_ERRORS else "text"
    return "text"


def _type_mismatch(value: Any, expected: DataType) -> bool:
    """True when the found value does not match the expected data type."""
    if expected is DataType.NUMBER:
        return isinstance(value, bool) or not isinstance(value, int | float)
    if expected is DataType.DATE:
        return not isinstance(value, datetime | date)
    return not isinstance(value, str)  # DataType.TEXT



def _key_for_sheet(
    key_cfg: KeyConfig,
    sheet: SheetData,
    title: str,
    file_name: str,
    year: int | None,
    month: int | None,
) -> _KeyResult:
    """The identity of one sheet's item (docs/SPEC.md revision v2, points 3 and 3b).

    Never guesses: an unreadable key gives `key: null` plus a KEY_NOT_FOUND or
    DATE_CONFLICT issue, and the item is still emitted.
    """
    if key_cfg.source is KeySource.NONE:
        return _KeyResult(None)
    read, at = _labelled_read(sheet, key_cfg.label) if key_cfg.label else (None, None)
    if key_cfg.type is not DataType.DATE:
        return _text_key(key_cfg, read, title)

    parts = _date_parts_from(title, key_cfg.format) if key_cfg.format else None
    content = _as_date(read.value) if read is not None else None
    if key_cfg.source is KeySource.SHEET_NAME:
        if parts is None:
            return _KeyResult(
                None,
                make_issue(
                    None,
                    IssueCode.KEY_NOT_FOUND,
                    f"Nama sheet '{title}' tidak cocok pola identitas '{key_cfg.format}'.",
                ),
            )
        return _date_key_from_name(key_cfg, parts, content, title, file_name, year, month)

    if content is not None:
        if parts is not None:
            named = _date_key_from_name(key_cfg, parts, content, title, file_name, year, month)
            if named.key is not None and named.key != content.isoformat():
                return _KeyResult(
                    None,
                    make_issue(
                        None,
                        IssueCode.DATE_CONFLICT,
                        f"Tanggal di {at} ({content.isoformat()}) berbeda dengan tanggal dari "
                        f"nama sheet '{title}' ({named.key}).",
                    ),
                )
        return _KeyResult(content.isoformat())
    if key_cfg.fallback is KeySource.SHEET_NAME and parts is not None:
        return _date_key_from_name(key_cfg, parts, None, title, file_name, year, month)
    return _KeyResult(
        None,
        make_issue(
            None,
            IssueCode.KEY_NOT_FOUND,
            f"Identitas dari tulisan '{key_cfg.label}' tidak terbaca di sheet '{title}'.",
        ),
    )


def _key_for_row(
    key_cfg: KeyConfig,
    sheet: SheetData,
    row_pos: tuple[int, int],
    file_ref: _FileRef,
    title: str,
    file_name: str,
    year: int | None,
    month: int | None,
) -> _KeyResult:
    """The identity of one table row: the value of the key column in that row."""
    read = sheet.value_at(*row_pos)
    at = address_of(row_pos)
    where = f"{file_ref.name}, sheet '{title}', baris {row_pos[0]}"
    if key_cfg.type is not DataType.DATE:
        value = read.value
        if value is None or str(value).strip() == "":
            return _KeyResult(
                None, make_issue(None, IssueCode.KEY_NOT_FOUND, f"Identitas di {at} ({where}) kosong.")
            )
        return _KeyResult(str(value).strip())

    content = _as_date(read.value)
    if content is None:
        return _KeyResult(
            None,
            make_issue(
                None, IssueCode.KEY_NOT_FOUND, f"Nilai di {at} ({where}) bukan tanggal."
            ),
        )
    parts = _date_parts_from(title, key_cfg.format) if key_cfg.format else None
    if parts is not None:
        named = _date_key_from_name(key_cfg, parts, content, title, file_name, year, month)
        if named.key is not None and named.key != content.isoformat():
            return _KeyResult(
                None,
                make_issue(
                    None,
                    IssueCode.DATE_CONFLICT,
                    f"Tanggal di {at} ({content.isoformat()}) berbeda dengan tanggal dari nama "
                    f"sheet '{title}' ({named.key}).",
                ),
            )
    return _KeyResult(content.isoformat())


def _date_key_from_name(
    key_cfg: KeyConfig,
    parts: tuple[int | None, int | None, int | None],
    content: date | None,
    title: str,
    file_name: str,
    year: int | None,
    month: int | None,
) -> _KeyResult:
    """Build the key from the sheet name, then refuse if it contradicts the content."""
    built = _name_date(key_cfg, parts, content, title, file_name, year, month)
    if built.issue is not None:
        return built
    if content is not None and built.key != content.isoformat():
        return _KeyResult(
            None,
            make_issue(
                None,
                IssueCode.DATE_CONFLICT,
                f"Tanggal dari nama sheet '{title}' ({built.key}) berbeda dengan tanggal di isi "
                f"sheet ({content.isoformat()}); salah satu tidak dipilih.",
            ),
        )
    return built



def _text_key(key_cfg: KeyConfig, read: ValueRead | None, title: str) -> _KeyResult:
    """Identity taken as text (a region name, a plant name, ...)."""
    if key_cfg.source is KeySource.SHEET_NAME:
        return _KeyResult(title)
    if read is not None and read.value is not None and str(read.value).strip():
        return _KeyResult(str(read.value).strip())
    if key_cfg.fallback is KeySource.SHEET_NAME:
        return _KeyResult(title)
    return _KeyResult(
        None,
        make_issue(
            None,
            IssueCode.KEY_NOT_FOUND,
            f"Identitas dari tulisan '{key_cfg.label}' tidak terbaca di sheet '{title}'.",
        ),
    )


def _name_date(
    key_cfg: KeyConfig,
    parts: tuple[int | None, int | None, int | None],
    content: date | None,
    title: str,
    file_name: str,
    year: int | None,
    month: int | None,
) -> _KeyResult:
    """Day from the sheet name; month/year from content, file name, or manual input."""
    day, month_part, year_part = parts
    file_month, file_year = _file_month_year(file_name, key_cfg.file_pattern) or (None, None)
    month_final = month_part or (content.month if content else None) or file_month or month
    year_final = year_part or (content.year if content else None) or file_year or year
    if day is None or month_final is None or year_final is None:
        missing = "hari" if day is None else "bulan" if month_final is None else "tahun"
        return _KeyResult(
            None,
            make_issue(
                None,
                IssueCode.KEY_NOT_FOUND,
                f"{missing.capitalize()} untuk identitas sheet '{title}' belum bisa ditentukan "
                "(isi sheet, nama file, atau isian bulan/tahun saat menjalankan).",
            ),
        )
    try:
        return _KeyResult(date(year_final, month_final, day).isoformat())
    except ValueError:
        return _KeyResult(
            None,
            make_issue(
                None,
                IssueCode.KEY_NOT_FOUND,
                f"Tanggal {day}/{month_final}/{year_final} dari nama sheet '{title}' tidak ada "
                "di kalender bulan itu.",
            ),
        )


def _labelled_read(sheet: SheetData, label: str) -> tuple[ValueRead | None, str | None]:
    """The cell next to a unique label, or (None, None) when missing/ambiguous."""
    positions = sheet.find_positions(KeywordConfig(text=label, is_unique=True))
    if len(positions) != 1:
        return None, None
    pos = positions[0]
    return sheet.value_at(*pos), address_of(pos)


def _as_date(value: Any) -> date | None:
    """A calendar date from a cell value; text is only accepted as ISO (no guessing)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _file_month_year(file_name: str, pattern: str) -> tuple[int | None, int | None] | None:
    """Month/year declared in the profile's file-name pattern (groups `month`/`year`)."""
    if not pattern:
        return None
    match = re.search(pattern, file_name, re.IGNORECASE)
    if match is None:
        return None
    groups = match.groupdict()
    raw_month = groups.get("month")
    month = None
    if raw_month:
        month = int(raw_month) if raw_month.isdigit() else _month_from_name(raw_month)
    raw_year = groups.get("year")
    year = int(raw_year) if raw_year and raw_year.isdigit() else None
    if year is not None and year < 100:
        year += 2000
    return month, year


def _date_parts_from(text: str, fmt: str) -> tuple[int | None, int | None, int | None] | None:
    """(day, month, year) read from `text` with the profile's pattern, None when no match."""
    pattern = _compile_format(fmt) if fmt else None
    if pattern is None:
        return None
    match = pattern.match(text.strip())
    if match is None:
        return None
    groups = match.groupdict()
    day = int(groups["d"]) if groups.get("d") else None
    month = int(groups["m"]) if groups.get("m") else None
    if month is None and groups.get("mon"):
        month = _month_from_name(groups["mon"])
        if month is None:
            return None
    year = None
    if groups.get("y4"):
        year = int(groups["y4"])
    elif groups.get("y2"):
        year = 2000 + int(groups["y2"])
    return day, month, year


def _compile_format(fmt: str) -> re.Pattern[str] | None:
    """Turn `DD MMM`-style patterns into a full-match regex (None when unusable)."""
    pattern = ""
    index = 0
    while index < len(fmt):
        for token, group in _DATE_TOKENS:
            if fmt.startswith(token, index):
                pattern += _TOKEN_GROUPS[group]
                index += len(token)
                break
        else:
            pattern += re.escape(fmt[index])
            index += 1
    try:
        return re.compile(rf"^{pattern}$", re.IGNORECASE)
    except re.error:
        return None


def _month_from_name(text: str) -> int | None:
    """Month number from a month name (Indonesian short names included)."""
    token = text.strip().lower()
    if not token:
        return None
    return _ID_MONTHS.get(token[:3])

