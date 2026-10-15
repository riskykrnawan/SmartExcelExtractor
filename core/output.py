"""Output schema v2: compact/full documents, content hashes, and the run summary.

The engine only knows the extraction; this module decides what the client sees.
See `docs/SPEC.md` (revisi v2) and `docs/schema/result-v2.json`.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from .audit import Item, Issue, RunResult

#: Version of the output document (independent of `Profile.schema_version`).
OUTPUT_SCHEMA_VERSION = 2

Mode = Literal["compact", "full"]
MODES: tuple[str, ...] = ("compact", "full")


def content_hash(values: dict[str, Any]) -> str:
    """SHA-256 over the values only, so a new `run_at` never changes the hash."""
    canonical = json.dumps(
        values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def summarize(items: list[Item]) -> dict[str, int]:
    """`meta.summary`: one count per value (item x field), plus the sheet count."""
    statuses = [result.status for item in items for result in item.fields.values()]
    sheets = {(item.folder, item.file, item.sheet) for item in items}
    return {
        "sheets": len(sheets),
        "total_fields": len(statuses),
        "ok": statuses.count("ok"),
        "warning": statuses.count("warning"),
        "error": statuses.count("error"),
    }


def worst_issue(issues: list[Issue]) -> Issue | None:
    """The issue the compact output keeps for a field: the most severe, then the first."""
    if not issues:
        return None
    return min(issues, key=lambda issue: issue.level != "error")


def _issue_to_dict(issue: Issue, at: str | None) -> dict[str, Any]:
    return {"status": issue.level, "code": issue.code.value, "at": at}


def _detail(item: Item) -> dict[str, dict[str, Any]]:
    """Full-mode per-field trace: where every value came from."""
    return {
        name: {
            "status": result.status,
            "value_address": result.value_address,
            "row_keyword_address": result.row_keyword_address,
            "col_keyword_address": result.col_keyword_address,
            "raw_value": result.raw_value,
            "type_found": result.type_found,
            "merged_range": result.merged_range,
            "from_formula": result.from_formula,
            "hidden": result.hidden,
        }
        for name, result in item.fields.items()
    }


def item_to_dict(item: Item, mode: Mode = "compact") -> dict[str, Any]:
    """One `data` entry: values plus only what deviates from `ok`."""
    values = item.values()
    issues: dict[str, dict[str, Any]] = {}
    for name, result in item.fields.items():
        issue = worst_issue(item.issues.get(name, []))
        if issue is None:
            continue
        entry = _issue_to_dict(issue, result.value_address)
        raw = result.raw_value
        if raw is not None and raw != ("" if result.value is None else str(result.value)):
            entry["raw"] = raw
        if result.merged_range:
            entry["merged_range"] = result.merged_range
        issues[name] = entry
    payload: dict[str, Any] = {
        "key": item.key,
        "status": item.status,
        "source": {
            "folder": item.folder,
            "file": item.file,
            "file_modified": item.file_modified,
        },
        "sheet": item.sheet,
        "values": values,
        "issues": issues,
        "content_hash": content_hash(values),
    }
    if item.key is None:
        del payload["key"]  # no identity = no field at all (keputusan user), not null
    if item.key_issue is not None:
        payload["key_issue"] = {
            "status": item.key_issue.level,
            "code": item.key_issue.code.value,
            "message": item.key_issue.message,
        }
    if mode == "full":
        payload["detail"] = _detail(item)
    return payload


def meta_to_dict(result: RunResult, mode: Mode) -> dict[str, Any]:
    """The `meta` block; `input_root` and other local paths are deliberately absent."""
    meta = result.meta
    return {
        "app_version": meta.get("app_version"),
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "mode": mode,
        "profile": meta.get("profile"),
        "run_at": meta.get("run_at"),
        "summary": meta.get("summary"),
        "unmatched_sheets": meta.get("unmatched_sheets", []),
    }


def build_document(result: RunResult, mode: Mode = "compact") -> dict[str, Any]:
    """The `output/*.json` document: `{"meta", "data"}` (no audit, see docs/SPEC.md).

    `data` groups the entries per source folder, then per sheet name (docs/SPEC.md poin 4).
    """
    data: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for item in result.items:
        data.setdefault(item.folder or "", {}).setdefault(item.sheet, []).append(
            item_to_dict(item, mode)
        )
    return {"meta": meta_to_dict(result, mode), "data": data}
