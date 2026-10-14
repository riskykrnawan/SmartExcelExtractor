"""CLI: run/validate/list exit codes and JSON output."""
from __future__ import annotations

import json
from pathlib import Path

import cli as cli_module
from core.profiles import save_profile
from tests.test_extractor import profile_for


def test_run_writes_json_and_exits_zero_without_errors(input_a: Path, tmp_path: Path) -> None:
    profile = profile_for(input_a, unique_violation=False)
    path = save_profile(profile, tmp_path / "bersih.json")
    out = tmp_path / "out"
    code = cli_module.main(["run", "--profile", str(path), "--output", str(out)])
    assert code == 0
    files = list(out.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["meta"]["profile"] == "Pabrik Uji"
    assert payload["meta"]["summary"]["error"] == 0


def test_run_exits_one_when_a_field_fails(input_a: Path, tmp_path: Path) -> None:
    profile = profile_for(input_a)
    path = save_profile(profile, tmp_path / "gagal.json")
    code = cli_module.main(["run", "--profile", str(path), "--output", str(tmp_path / "out")])
    assert code == 1


def test_run_requires_input_root(tmp_path: Path) -> None:
    profile = profile_for(tmp_path)
    profile.input_root = None
    path = save_profile(profile, tmp_path / "tanpa-akar.json")
    code = cli_module.main(["run", "--profile", str(path), "--output", str(tmp_path / "out")])
    assert code == 2


def test_run_missing_profile_exits_two(tmp_path: Path) -> None:
    code = cli_module.main(["run", "--profile", str(tmp_path / "hilang.json")])
    assert code == 2


def test_validate_ok(input_a: Path, tmp_path: Path) -> None:
    path = save_profile(profile_for(input_a), tmp_path / "uji.json")
    assert cli_module.main(["validate", "--profile", str(path)]) == 0


def test_validate_broken_profile_exits_two(tmp_path: Path) -> None:
    broken = tmp_path / "salah.json"
    broken.write_text("{rusak", encoding="utf-8")
    assert cli_module.main(["validate", "--profile", str(broken)]) == 2


def test_list_profiles_runs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "list_profiles", lambda: [])
    assert cli_module.main(["list-profiles"]) == 0


def test_no_command_prints_help(capsys) -> None:
    assert cli_module.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()
