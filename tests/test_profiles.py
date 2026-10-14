"""Profile CRUD: create, duplicate, rename, delete, import/export, friendly errors."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.profiles import (
    ProfileError,
    create_profile,
    delete_profile,
    duplicate_profile,
    export_profile,
    find_profile,
    import_profile,
    list_profiles,
    load_profile,
    rename_profile,
    save_profile,
)


def test_create_and_load_roundtrip(tmp_path: Path) -> None:
    profile = create_profile("Pabrik Uji", directory=tmp_path)
    assert profile.name == "Pabrik Uji"
    saved = tmp_path / "Pabrik Uji.json"
    assert saved.is_file()
    assert load_profile(saved).name == "Pabrik Uji"


def test_create_duplicate_name_rejected(tmp_path: Path) -> None:
    create_profile("Pabrik Uji", directory=tmp_path)
    with pytest.raises(ProfileError, match="sudah ada"):
        create_profile("Pabrik Uji", directory=tmp_path)


def test_list_profiles_sorted(tmp_path: Path) -> None:
    create_profile("B", directory=tmp_path)
    create_profile("A", directory=tmp_path)
    assert [p.name for p in list_profiles(directory=tmp_path)] == ["A.json", "B.json"]


def test_find_profile_by_name(tmp_path: Path) -> None:
    create_profile("Pabrik A", directory=tmp_path)
    assert find_profile("Pabrik A", directory=tmp_path).name == "Pabrik A.json"
    assert find_profile("Pabrik A.json", directory=tmp_path).name == "Pabrik A.json"
    with pytest.raises(ProfileError, match="tidak ditemukan"):
        find_profile("Hilang", directory=tmp_path)


def test_duplicate_profile(tmp_path: Path) -> None:
    create_profile("Pabrik A", directory=tmp_path)
    source = tmp_path / "Pabrik A.json"
    new_path = duplicate_profile(source, "Pabrik B", directory=tmp_path)
    assert new_path.name == "Pabrik B.json"
    assert load_profile(new_path).name == "Pabrik B"
    assert source.exists()  # original untouched


def test_rename_profile_moves_file(tmp_path: Path) -> None:
    create_profile("Lama", directory=tmp_path)
    old = tmp_path / "Lama.json"
    new_path = rename_profile(old, "Baru", directory=tmp_path)
    assert not old.exists()
    assert new_path.name == "Baru.json"
    assert load_profile(new_path).name == "Baru"


def test_delete_profile(tmp_path: Path) -> None:
    create_profile("Hapus Saya", directory=tmp_path)
    path = tmp_path / "Hapus Saya.json"
    delete_profile(path)
    assert not path.exists()
    with pytest.raises(ProfileError, match="tidak ditemukan"):
        delete_profile(path)


def test_export_and_import_validate(tmp_path: Path) -> None:
    create_profile("Asli", directory=tmp_path)
    exported = export_profile(tmp_path / "Asli.json", tmp_path / "keluar.json")
    assert load_profile(exported).name == "Asli"
    # Import into a different folder: same name already exists in the source folder.
    other = tmp_path / "folder_lain"
    imported = import_profile(exported, directory=other)
    assert load_profile(imported).name == "Asli"
    with pytest.raises(ProfileError, match="sudah ada"):
        import_profile(exported, directory=other)


def test_import_rejects_invalid_json(tmp_path: Path) -> None:
    broken = tmp_path / "rusak.json"
    broken.write_text("{bukan json", encoding="utf-8")
    with pytest.raises(ProfileError, match="tidak bisa dibaca"):
        import_profile(broken, directory=tmp_path)


def test_load_rejects_invalid_config_with_plain_message(tmp_path: Path) -> None:
    path = tmp_path / "salah.json"
    path.write_text(
        json.dumps({"name": "X", "sources": [{"folder": "a", "sheets": [{"name": "S",
            "fields": [{"output_name": "satu", "row_keyword": {"text": "Label"}},
                       {"output_name": "satu", "row_keyword": {"text": "Label"}}]}]}]}),
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="dipakai lebih dari satu kali"):
        load_profile(path)


def test_load_missing_file_friendly(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="tidak ditemukan"):
        load_profile(tmp_path / "tidak-ada.json")


def test_save_profile_explicit_path(tmp_path: Path) -> None:
    profile = create_profile("Bebas", directory=tmp_path)
    other = save_profile(profile, tmp_path / "sub" / "lain.json")
    assert other.is_file()
    assert load_profile(other).name == "Bebas"
