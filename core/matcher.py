"""Text normalization and keyword matching modes (exact/contains/starts/ends/regex)."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .models import KeywordConfig, MatchMode


def normalize_text(value: Any) -> str:
    """Convert a cell value to normalized text.

    Newlines/tabs become spaces, repeated spaces collapse, ends are stripped.
    Numbers keep their value (1523.0 -> "1523"), dates/datetimes become ISO text.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, bool):
        text = "TRUE" if value else "FALSE"
    elif isinstance(value, datetime | date):
        text = value.isoformat()
    elif isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value)
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return re.sub(r" +", " ", text).strip()


def fold_text(text: str) -> str:
    """Case-folded key used by the cell index (matching ignores case by default)."""
    return text.lower()


def _regex_search(pattern: str, text: str, case_sensitive: bool) -> bool:
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.search(pattern, text, flags) is not None
    except re.error:
        # An invalid pattern is rejected during config validation; guard anyway.
        return False


def matches_text(cell_text: str, keyword: KeywordConfig) -> bool:
    """Match already-normalized cell text against a keyword under its configured mode.

    `cell_text` must be the output of `normalize_text`. Case folding follows
    `keyword.case_sensitive`; regex mode uses the raw pattern as written.
    """
    if keyword.match_mode is MatchMode.REGEX:
        return _regex_search(keyword.text, cell_text, keyword.case_sensitive)
    kw = normalize_text(keyword.text)
    if not keyword.case_sensitive:
        cell_text = fold_text(cell_text)
        kw = fold_text(kw)
    if not kw:
        return False
    mode = keyword.match_mode
    if mode is MatchMode.EXACT:
        return cell_text == kw
    if mode is MatchMode.CONTAINS:
        return kw in cell_text
    if mode is MatchMode.STARTS_WITH:
        return cell_text.startswith(kw)
    if mode is MatchMode.ENDS_WITH:
        return cell_text.endswith(kw)
    # All other modes (regex) returned at the top; the checker proves exhaustiveness.
