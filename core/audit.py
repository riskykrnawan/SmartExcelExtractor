"""Issue codes, audit records, and summary for one extraction run.

Levels (also documented in docs/SPEC.md):
- error  : FILE_NOT_FOUND, FILE_UNREADABLE, SHEET_NOT_FOUND, SHEET_AMBIGUOUS,
  KEYWORD_NOT_FOUND, UNIQUE_VIOLATION, AMBIGUOUS_AFTER_DISAMBIGUATION, INTERNAL_ERROR
- warning: everything else. MULTIPLE_FILES is recorded once per source, not per field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast


class IssueCode(StrEnum):
    """Every code the engine may emit (see docs/SPEC.md)."""

    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_UNREADABLE = "FILE_UNREADABLE"
    MULTIPLE_FILES = "MULTIPLE_FILES"
    SHEET_NOT_FOUND = "SHEET_NOT_FOUND"
    SHEET_AMBIGUOUS = "SHEET_AMBIGUOUS"
    KEYWORD_NOT_FOUND = "KEYWORD_NOT_FOUND"
    UNIQUE_VIOLATION = "UNIQUE_VIOLATION"
    AMBIGUOUS_AFTER_DISAMBIGUATION = "AMBIGUOUS_AFTER_DISAMBIGUATION"
    ADDRESS_DRIFT = "ADDRESS_DRIFT"
    EMPTY_VALUE = "EMPTY_VALUE"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    FORMULA_NOT_CALCULATED = "FORMULA_NOT_CALCULATED"
    EXCEL_ERROR_VALUE = "EXCEL_ERROR_VALUE"
    MERGED_CELL = "MERGED_CELL"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Codes that fail a field (status "error"); all others only mark it ("warning").
ERROR_CODES: frozenset[IssueCode] = frozenset(
    {
        IssueCode.FILE_NOT_FOUND,
        IssueCode.FILE_UNREADABLE,
        IssueCode.SHEET_NOT_FOUND,
        IssueCode.SHEET_AMBIGUOUS,
        IssueCode.KEYWORD_NOT_FOUND,
        IssueCode.UNIQUE_VIOLATION,
        IssueCode.AMBIGUOUS_AFTER_DISAMBIGUATION,
        IssueCode.INTERNAL_ERROR,
    }
)


def make_issue(field_name: str | None, code: IssueCode, message: str) -> Issue:
    """Build an issue with its level derived from the code."""
    level = "error" if code in ERROR_CODES else "warning"
    return Issue(field_name=field_name, level=level, code=code, message=message)


class ExtractionError(Exception):
    """A per-field failure carrying an issue code, a friendly message, and candidates."""

    def __init__(self, code: IssueCode, message: str, candidates: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.candidates = candidates or []


@dataclass
class Issue:
    """One entry of `audit.issues`."""

    field_name: str | None
    level: str
    code: IssueCode
    message: str

    def to_dict(self) -> dict[str, Any]:
        """JSON form: {"field", "level", "code", "message"}."""
        return {
            "field": self.field_name,
            "level": self.level,
            "code": self.code.value,
            "message": self.message,
        }


@dataclass
class FieldAudit:
    """`audit.fields` entry: what happened while extracting one field."""

    field_name: str
    status: str
    row_keyword: KeywordAudit | None = None
    col_keyword: KeywordAudit | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON form matching docs/SPEC.md."""
        return {
            "field": self.field_name,
            "status": self.status,
            "row_keyword": self.row_keyword.to_dict() if self.row_keyword else None,
            "col_keyword": self.col_keyword.to_dict() if self.col_keyword else None,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass
class FieldResult:
    """`data` entry: the extracted value plus its full provenance."""

    field_name: str
    value: Any
    status: str
    folder: str | None
    file: str | None
    file_modified: str | None
    sheet: str | None
    value_address: str | None
    row_keyword_address: str | None
    col_keyword_address: str | None
    raw_value: str | None
    type_found: str
    merged: bool
    merged_range: str | None
    hidden: bool
    from_formula: bool

    def to_dict(self) -> dict[str, Any]:
        """JSON form matching docs/SPEC.md (plus `merged_range` for audit detail)."""
        return {
            "value": self.value,
            "status": self.status,
            "source": {
                "folder": self.folder,
                "file": self.file,
                "file_modified": self.file_modified,
                "sheet": self.sheet,
            },
            "location": {
                "value_address": self.value_address,
                "row_keyword_address": self.row_keyword_address,
                "col_keyword_address": self.col_keyword_address,
            },
            "value_meta": {
                "raw_value": self.raw_value,
                "type_found": self.type_found,
                "merged": self.merged,
                "merged_range": self.merged_range,
                "hidden": self.hidden,
                "from_formula": self.from_formula,
            },
        }


def build_summary(statuses: list[str]) -> dict[str, int]:
    """Count field statuses into the `meta.summary` block."""
    return {
        "total_fields": len(statuses),
        "ok": statuses.count("ok"),
        "warning": statuses.count("warning"),
        "error": statuses.count("error"),
    }


@dataclass
class RunResult:
    """The complete output of one extraction run."""

    meta: dict[str, Any]
    data: dict[str, dict[str, Any]]
    audit: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """JSON form: {"meta", "data", "audit"} with stable key order."""
        return {"meta": self.meta, "data": self.data, "audit": self.audit}

    @property
    def summary(self) -> dict[str, Any]:
        """The `meta.summary` block: total/ok/warning/error counts."""
        return cast(dict[str, Any], self.meta["summary"])


@dataclass
class KeywordAudit:
    """Audit trail for one keyword of a field (row, column, or comparison)."""

    text: str
    match_mode: str
    is_unique: bool
    candidates: list[str] = field(default_factory=list)
    selected: str | None = None
    disambiguation: str | None = None
    reference: str | None = None
    drift: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON form; keys are uniform even when a key does not apply (null)."""
        return {
            "text": self.text,
            "match_mode": self.match_mode,
            "is_unique": self.is_unique,
            "candidates": list(self.candidates),
            "selected": self.selected,
            "disambiguation": self.disambiguation,
            "reference": self.reference,
            "drift": self.drift,
        }
