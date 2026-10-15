"""JSON writer: file naming, collision handling, structure, and modes."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from core.audit import FieldResult, Item, RunResult
from core.json_writer import write_json

FIXED_NOW = datetime(2026, 10, 14, 8, 30, 0)


def make_result(profile_name: str = "Pabrik A") -> RunResult:
    """Minimal v2 result: one item with one ok field."""
    field = FieldResult(
        field_name="prod_hi",
        value=1523.5,
        status="ok",
        folder="input",
        file="produksi.xlsx",
        file_modified="2026-10-14T07:00:00",
        sheet="Produksi",
        value_address="L45",
        row_keyword_address="A45",
        col_keyword_address=None,
        raw_value=None,
        type_found="number",
        merged=False,
        merged_range=None,
        hidden=False,
        from_formula=False,
    )
    item = Item(
        key="2026-10-14",
        status="ok",
        folder="input",
        file="produksi.xlsx",
        file_modified="2026-10-14T07:00:00",
        sheet="Produksi",
        fields={"prod_hi": field},
    )
    meta: dict[str, Any] = {
        "app_version": "2.0.0",
        "profile": profile_name,
        "run_at": FIXED_NOW.isoformat(),
        "summary": {"sheets": 1, "total_fields": 1, "ok": 1, "warning": 0, "error": 0},
        "unmatched_sheets": [],
    }
    return RunResult(meta=meta, data={}, audit={"fields": [], "issues": []}, items=[item])


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_filename_follows_profile_and_timestamp(tmp_path: Path) -> None:
    path = write_json(make_result(), tmp_path, now=FIXED_NOW)
    assert path.name == "Pabrik A_20261014_083000.json"
    assert path.parent == tmp_path


def test_content_has_meta_and_data_without_audit(tmp_path: Path) -> None:
    payload = read(write_json(make_result(), tmp_path, now=FIXED_NOW))
    assert set(payload) == {"meta", "data"}
    assert payload["meta"]["schema_version"] == 2
    assert payload["meta"]["mode"] == "compact"
    entry = payload["data"]["input"]["Produksi"][0]
    assert entry["key"] == "2026-10-14"
    assert entry["values"]["prod_hi"] == 1523.5
    assert "detail" not in entry


def test_full_mode_gets_suffix_and_detail(tmp_path: Path) -> None:
    path = write_json(make_result(), tmp_path, mode="full", now=FIXED_NOW)
    assert path.name == "Pabrik A_20261014_083000_full.json"
    payload = read(path)
    assert payload["meta"]["mode"] == "full"
    entry = payload["data"]["input"]["Produksi"][0]["detail"]["prod_hi"]
    assert entry["value_address"] == "L45"
    assert entry["merged_range"] is None and entry["status"] == "ok"


def test_same_values_same_content_hash(tmp_path: Path) -> None:
    first = read(write_json(make_result(), tmp_path, now=FIXED_NOW))
    second = read(write_json(make_result(), tmp_path, now=FIXED_NOW))
    first_entry = first["data"]["input"]["Produksi"][0]
    second_entry = second["data"]["input"]["Produksi"][0]
    assert first_entry["content_hash"] == second_entry["content_hash"]


def test_unsafe_characters_replaced(tmp_path: Path) -> None:
    path = write_json(make_result("Pabrik/A:Raya"), tmp_path, now=FIXED_NOW)
    assert "/" not in path.name and ":" not in path.name


def test_collision_gets_suffix_instead_of_overwrite(tmp_path: Path) -> None:
    first = write_json(make_result(), tmp_path, now=FIXED_NOW)
    second = write_json(make_result(), tmp_path, now=FIXED_NOW)
    assert first != second
    assert second.name.endswith("_1.json")
    assert first.exists() and second.exists()


def test_data_is_grouped_by_folder_then_sheet(tmp_path: Path) -> None:
    """`data` groups entries per folder, then per sheet; one sheet can hold several."""
    result = make_result()
    other_folder = replace(result.items[0], folder="lain", sheet="Harian")
    second_in_sheet = replace(result.items[0], key=None)
    result.items.extend([other_folder, second_in_sheet])
    payload = read(write_json(result, tmp_path, now=FIXED_NOW))
    assert set(payload["data"]) == {"input", "lain"}
    assert payload["data"]["lain"]["Harian"][0]["values"]["prod_hi"] == 1523.5
    assert len(payload["data"]["input"]["Produksi"]) == 2


def test_key_is_omitted_when_the_item_has_none(tmp_path: Path) -> None:
    """Without an identity the entry simply has no `key` field (keputusan user)."""
    result = make_result()
    result.items[0].key = None
    payload = read(write_json(result, tmp_path, now=FIXED_NOW))
    assert "key" not in payload["data"]["input"]["Produksi"][0]

