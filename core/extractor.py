"""Extraction engine: profile -> sources -> sheets -> fields.

One failing field never stops the others; every failure becomes an audit issue.
Deterministic: same profile + same input files + same `now` -> identical JSON.
"""
from __future__ import annotations

import logging
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
    KeywordAudit,
    RunResult,
    build_summary,
    make_issue,
)
from .cell_index import (
    ExcelFileError,
    LoadedWorkbook,
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
    KeywordConfig,
    Profile,
    SheetConfig,
    SourceConfig,
    ValueDirection,
)

logger = logging.getLogger(__name__)

_EXCEL_ERRORS = frozenset({"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NULL!", "#NUM!"})

_TYPE_LABELS = {DataType.NUMBER: "angka", DataType.TEXT: "teks", DataType.DATE: "tanggal"}


@dataclass
class _FileRef:
    """File provenance shared by every field of one source."""

    folder: str
    name: str
    modified: str | None


@dataclass
class _FieldOutcome:
    """Result + audit trail + issues for one field."""

    result: FieldResult
    audit: FieldAudit
    issues: list[Issue] = dc_field(default_factory=list)


def run_extraction(profile: Profile, *, now: datetime | None = None) -> RunResult:
    """Extract every enabled field of `profile`.

    Raises only for a broken profile (validate before calling). Single field,
    sheet, and file failures are recorded as issues instead of propagating.
    """
    run_at = now or datetime.now().astimezone()
    outcomes: list[_FieldOutcome] = []
    source_issues: list[Issue] = []
    root = Path(profile.input_root) if profile.input_root else None
    for source in profile.sources:
        if not source.enabled:
            continue
        source_outcomes, issues = _run_source(source, root)
        outcomes.extend(source_outcomes)
        source_issues.extend(issues)

    field_issues = [issue for outcome in outcomes for issue in outcome.issues]
    meta: dict[str, Any] = {
        "app_version": __version__,
        "schema_version": profile.schema_version,
        "profile": profile.name,
        "run_at": run_at.isoformat(timespec="seconds"),
        "input_root": profile.input_root,
        "summary": build_summary([outcome.audit.status for outcome in outcomes]),
    }
    audit: dict[str, Any] = {
        "fields": [outcome.audit.to_dict() for outcome in outcomes],
        "issues": [issue.to_dict() for issue in source_issues + field_issues],
    }
    data = {outcome.result.field_name: outcome.result.to_dict() for outcome in outcomes}
    return RunResult(meta=meta, data=data, audit=audit)


def _file_mtime(path: Path) -> str | None:
    """ISO timestamp of the last modification, or None when unreadable."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def _run_source(source: SourceConfig, root: Path | None) -> tuple[list[_FieldOutcome], list[Issue]]:
    """Resolve one source folder's file, then extract all its configured fields."""
    configured = [(sheet, field_cfg) for sheet in source.sheets for field_cfg in sheet.fields]
    if not configured:
        return [], []
    source_issues: list[Issue] = []

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
            source_issues.append(
                make_issue(
                    None,
                    IssueCode.MULTIPLE_FILES,
                    f"Folder '{source.folder}' berisi {len(files)} file Excel ({names}). "
                    f"Yang dipakai: {file_path.name} (paling baru diubah).",
                )
            )

    if file_code is not None and file_msg is not None:
        return [
            _failed_outcome(sheet, field_cfg, source.folder, file_code, file_msg, None)
            for sheet, field_cfg in configured
        ], source_issues

    if file_path is None:  # unreachable; narrows the type for the checker
        return [], source_issues
    file_ref = _FileRef(folder=source.folder, name=file_path.name, modified=_file_mtime(file_path))
    try:
        wb = load_workbook_pair(file_path)
    except ExcelFileError as exc:
        return [
            _failed_outcome(
                sheet, field_cfg, source.folder, IssueCode.FILE_UNREADABLE, str(exc), file_ref
            )
            for sheet, field_cfg in configured
        ], source_issues

    outcomes: list[_FieldOutcome] = []
    try:
        titles = wb.sheet_titles()
        cache: dict[str, SheetData] = {}
        for sheet_cfg in source.sheets:
            for field_cfg in sheet_cfg.fields:
                outcomes.append(_extract_field_safe(wb, cache, titles, sheet_cfg, field_cfg, file_ref))
    finally:
        wb.close()
    return outcomes, source_issues


def _failed_outcome(
    sheet_cfg: SheetConfig,
    field_cfg: FieldConfig,
    folder: str,
    code: IssueCode,
    message: str,
    file_ref: _FileRef | None,
) -> _FieldOutcome:
    """A field that could not run at all (file/sheet level failure)."""
    audit = FieldAudit(field_name=field_cfg.output_name, status="error", errors=[message])
    result = FieldResult(
        field_name=field_cfg.output_name,
        value=None,
        status="error",
        folder=folder,
        file=file_ref.name if file_ref else None,
        file_modified=file_ref.modified if file_ref else None,
        sheet=sheet_cfg.name,
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
    return _FieldOutcome(result, audit, [make_issue(field_cfg.output_name, code, message)])


def _resolve_sheet(titles: list[str], cfg: SheetConfig) -> str:
    """Match the configured sheet name against actual titles using MatchMode."""
    probe = KeywordConfig(text=cfg.name, match_mode=cfg.match_mode, is_unique=True)
    matches = [title for title in titles if matches_text(normalize_text(title), probe)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        available = ", ".join(titles)
        raise ExtractionError(
            IssueCode.SHEET_NOT_FOUND,
            f"Sheet '{cfg.name}' tidak ada di file. Sheet yang tersedia: {available}.",
        )
    raise ExtractionError(
        IssueCode.SHEET_AMBIGUOUS,
        f"Nama sheet '{cfg.name}' cocok dengan {len(matches)} sheet: {', '.join(matches)}. "
        "Pakai nama yang lebih spesifik.",
    )


def _extract_field_safe(
    wb: LoadedWorkbook,
    cache: dict[str, SheetData],
    titles: list[str],
    sheet_cfg: SheetConfig,
    field_cfg: FieldConfig,
    file_ref: _FileRef,
) -> _FieldOutcome:
    """Resolve the sheet and extract, converting any failure into an audit issue."""
    try:
        title = _resolve_sheet(titles, sheet_cfg)
        if title not in cache:
            cache[title] = build_sheet_data(wb.values_wb[title], wb.formulas_wb[title], title)
        return _extract_field(cache[title], title, field_cfg, file_ref)
    except ExtractionError as exc:
        return _failed_outcome(sheet_cfg, field_cfg, file_ref.folder, exc.code, exc.message, file_ref)
    except Exception:
        logger.exception("Unexpected error extracting field %s", field_cfg.output_name)
        return _failed_outcome(
            sheet_cfg,
            field_cfg,
            file_ref.folder,
            IssueCode.INTERNAL_ERROR,
            "Terjadi kesalahan tak terduga saat mengambil data ini. Detail lengkap ada di file log.",
            file_ref,
        )


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


def _extract_field(
    sheet: SheetData, title: str, cfg: FieldConfig, file_ref: _FileRef
) -> _FieldOutcome:
    """Extract one field from a loaded sheet. Never raises; failures become issues."""
    warnings: list[str] = []
    errors: list[str] = []
    issues: list[Issue] = []

    def add(code: IssueCode, message: str) -> None:
        issue = make_issue(cfg.output_name, code, message)
        issues.append(issue)
        if issue.level == "error":
            errors.append(message)
        else:
            warnings.append(message)

    # Row keyword: search + disambiguate, capturing the failure for the audit.
    row_audit = _keyword_audit(cfg.row_keyword)
    row_positions = sheet.find_positions(cfg.row_keyword)
    row_res, row_err = _try_disambiguate(row_positions, cfg.row_keyword, sheet)
    _fill_keyword_audit(row_audit, row_positions, row_res)
    if row_err is not None:
        add(row_err.code, row_err.message)

    # Column keyword (optional): same treatment; both keywords stay auditable.
    col_audit: KeywordAudit | None = None
    col_res: DisambiguationResult | None = None
    if cfg.col_keyword is not None:
        col_audit = _keyword_audit(cfg.col_keyword)
        col_positions = sheet.find_positions(cfg.col_keyword)
        col_res, col_err = _try_disambiguate(col_positions, cfg.col_keyword, sheet)
        _fill_keyword_audit(col_audit, col_positions, col_res)
        if col_err is not None:
            add(col_err.code, col_err.message)

    for res in (row_res, col_res):
        if res is not None:
            for code, message in res.warnings:
                add(code, message)

    row_address = address_of(row_res.selected) if row_res is not None else None
    col_address = address_of(col_res.selected) if col_res is not None else None
    if row_res is None or (cfg.col_keyword is not None and col_res is None):
        audit = FieldAudit(
            field_name=cfg.output_name,
            status="error",
            row_keyword=row_audit,
            col_keyword=col_audit,
            warnings=warnings,
            errors=errors,
        )
        result = FieldResult(
            field_name=cfg.output_name,
            value=None,
            status="error",
            folder=file_ref.folder,
            file=file_ref.name,
            file_modified=file_ref.modified,
            sheet=title,
            value_address=None,
            row_keyword_address=row_address,
            col_keyword_address=col_address,
            raw_value=None,
            type_found="empty",
            merged=False,
            merged_range=None,
            hidden=False,
            from_formula=False,
        )
        return _FieldOutcome(result, audit, issues)

    # Value cell: intersection of row/column keyword, or a shift from the row keyword.
    if cfg.col_keyword is not None and col_res is not None:
        target = (row_res.selected[0], col_res.selected[1])
        col_address = address_of(col_res.selected)
    else:
        delta = _direction_delta(cfg.value_direction, cfg.value_offset)
        target = (row_res.selected[0] + delta[0], row_res.selected[1] + delta[1])
        col_address = None
    row_address = address_of(row_res.selected)

    if target[0] >= 1 and target[1] >= 1:
        read = sheet.value_at(*target)
        value_address: str | None = address_of(target)
    else:
        read = ValueRead(value=None)
        value_address = None

    value = read.value
    if read.merged and read.merged_range and value_address:
        add(
            IssueCode.MERGED_CELL,
            f"Nilai di {value_address} berasal dari sel gabungan {read.merged_range}.",
        )
    if read.from_formula and value is None:
        add(
            IssueCode.FORMULA_NOT_CALCULATED,
            f"Rumus di {value_address} belum dihitung oleh Excel, nilainya kosong.",
        )
    elif value is None or (isinstance(value, str) and not value.strip()):
        if not cfg.allow_empty:
            if value_address:
                add(IssueCode.EMPTY_VALUE, f"Tidak ada nilai di {value_address}.")
            else:
                add(IssueCode.EMPTY_VALUE, "Tidak ada nilai (posisi hasil geser di luar sheet).")
    if isinstance(value, str) and value in _EXCEL_ERRORS:
        add(IssueCode.EXCEL_ERROR_VALUE, f"Sel {value_address} berisi kesalahan Excel {value}.")
    elif (
        value is not None
        and cfg.data_type is not DataType.ANY
        and _type_mismatch(value, cfg.data_type)
    ):
        add(
            IssueCode.TYPE_MISMATCH,
            f"Nilai di {value_address} bukan {_TYPE_LABELS[cfg.data_type]} "
            f"(terbaca: {_type_of(value)}); nilai asli tetap disimpan.",
        )

    final_value = value.isoformat() if isinstance(value, datetime | date) else value
    status = "error" if errors else "warning" if warnings else "ok"
    audit = FieldAudit(
        field_name=cfg.output_name,
        status=status,
        row_keyword=row_audit,
        col_keyword=col_audit,
        warnings=warnings,
        errors=errors,
    )
    result = FieldResult(
        field_name=cfg.output_name,
        value=final_value,
        status=status,
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
    return _FieldOutcome(result, audit, issues)
