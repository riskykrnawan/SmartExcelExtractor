"""JSON writer: file naming, collision handling, structure."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.audit import RunResult
from core.json_writer import write_json

FIXED_NOW = datetime(2026, 10, 14, 8, 30, 0)


def make_result(profile_name: str = "Pabrik A") -> RunResult:
    """Minimal result for writer tests."""
    return RunResult(
        meta={"profile": profile_name, "run_at": FIXED_NOW.isoformat(), "summary": {}},
        data={"prod_hi": {"value": 1523.5, "status": "ok"}},
        audit={"fields": [], "issues": []},
    )


def test_filename_follows_profile_and_timestamp(tmp_path: Path) -> None:
    path = write_json(make_result(), tmp_path, now=FIXED_NOW)
    assert path.name == "Pabrik A_20261014_083000.json"
    assert path.parent == tmp_path


def test_content_parses_and_has_top_level_keys(tmp_path: Path) -> None:
    path = write_json(make_result(), tmp_path, now=FIXED_NOW)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {"meta", "data", "audit"}
    assert payload["data"]["prod_hi"]["value"] == 1523.5


def test_unsafe_characters_replaced(tmp_path: Path) -> None:
    path = write_json(make_result("Pabrik/A:Raya"), tmp_path, now=FIXED_NOW)
    assert "/" not in path.name and ":" not in path.name


def test_collision_gets_suffix_instead_of_overwrite(tmp_path: Path) -> None:
    first = write_json(make_result(), tmp_path, now=FIXED_NOW)
    second = write_json(make_result(), tmp_path, now=FIXED_NOW)
    assert first != second
    assert second.name.endswith("_1.json")
    assert first.exists() and second.exists()
