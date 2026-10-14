"""Deterministic JSON writer for extraction results."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .audit import RunResult

_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def write_json(result: RunResult, output_dir: Path, *, now: datetime | None = None) -> Path:
    """Write the result to `output_dir/{profile}_{YYYYMMDD_HHMMSS}.json`.

    An existing file with the same name gets a numeric suffix instead of being
    overwritten. Returns the written path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now().astimezone()).strftime("%Y%m%d_%H%M%S")
    profile_name = str(result.meta.get("profile") or "profil")
    safe_name = _UNSAFE_FILENAME.sub("_", profile_name).strip() or "profil"
    path = output_dir / f"{safe_name}_{stamp}.json"
    suffix = 1
    while path.exists():
        path = output_dir / f"{safe_name}_{stamp}_{suffix}.json"
        suffix += 1
    text = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")
    return path
