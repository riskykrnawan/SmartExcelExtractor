"""Deterministic JSON writer for extraction results (output schema v2)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .audit import RunResult
from .output import Mode, build_document

_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def write_json(
    result: RunResult,
    output_dir: Path,
    *,
    mode: Mode = "compact",
    now: datetime | None = None,
) -> Path:
    """Write the result to `output_dir/{profile}_{YYYYMMDD_HHMMSS}.json`.

    Full mode adds a `_full` suffix so both files stay apart. An existing file with
    the same name gets a numeric suffix instead of being overwritten. The document
    is the client-facing v2 schema (`core.output`); the audit stays in the app.
    Returns the written path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now().astimezone()).strftime("%Y%m%d_%H%M%S")
    profile_name = str(result.meta.get("profile") or "profil")
    safe_name = _UNSAFE_FILENAME.sub("_", profile_name).strip() or "profil"
    tail = "_full" if mode == "full" else ""
    path = output_dir / f"{safe_name}_{stamp}{tail}.json"
    counter = 1
    while path.exists():
        path = output_dir / f"{safe_name}_{stamp}{tail}_{counter}.json"
        counter += 1
    text = json.dumps(build_document(result, mode), ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")
    return path

