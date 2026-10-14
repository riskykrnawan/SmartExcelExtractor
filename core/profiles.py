"""Profile CRUD. Profiles live in `profiles/` beside the application.

All errors are ProfileError with plain Indonesian messages (no stack traces).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import Profile, SourceConfig
from .paths import app_dir

_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Indonesian labels for config locations shown in validation messages.
_LOC_LABELS = {
    "name": "Nama profil",
    "input_root": "Folder induk",
    "sources": "Sumber",
    "folder": "Nama folder",
    "sheets": "Sheet",
    "fields": "Data",
    "output_name": "Nama untuk hasil ini",
    "row_keyword": "Keyword baris",
    "col_keyword": "Keyword kolom",
    "reference_keyword": "Pembanding",
    "text": "Tulisan",
    "reference_address": "Alamat sel acuan",
    "disambiguation": "Pilihan cara memilih",
    "radius": "Jarak 'dekat'",
    "match_mode": "Cara pencocokan",
}


class ProfileError(Exception):
    """A profile problem with a message meant for non-technical users."""


def profiles_dir(directory: Path | None = None) -> Path:
    """The profile folder beside the app (or an explicit directory, e.g. in tests)."""
    path = directory if directory is not None else app_dir() / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _loc_label(loc: tuple[Any, ...]) -> str:
    """Translate a pydantic error location into plain Indonesian labels."""
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            if parts:
                parts[-1] = f"{parts[-1]} #{item + 1}"
            continue
        label = _LOC_LABELS.get(str(item))
        if label and (not parts or label != parts[-1]):
            parts.append(label)
    return " > ".join(parts)


def format_validation_error(exc: ValidationError) -> list[str]:
    """Turn pydantic errors into deduplicated plain-Indonesian sentences."""
    messages: list[str] = []
    for err in exc.errors():
        msg = str(err["msg"])
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        label = _loc_label(tuple(err.get("loc", ())))
        line = f"{label}: {msg}" if label else msg
        if line not in messages:
            messages.append(line)
    return messages


def load_profile(path: Path) -> Profile:
    """Read and validate a profile file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProfileError(f"File profil '{path.name}' tidak ditemukan.") from None
    except json.JSONDecodeError as exc:
        raise ProfileError(
            f"File profil '{path.name}' tidak bisa dibaca (bukan file profil yang benar)."
        ) from exc
    if not isinstance(raw, dict):
        raise ProfileError(f"File profil '{path.name}' tidak berisi data profil yang benar.")
    try:
        return Profile.model_validate(raw)
    except ValidationError as exc:
        raise ProfileError(
            "Profil belum valid:\n- " + "\n- ".join(format_validation_error(exc))
        ) from exc


def _safe_filename(name: str) -> str:
    """Turn a profile name into a safe file name (Windows-safe characters)."""
    return _UNSAFE_FILENAME.sub("_", name.strip()) or "profil"


def save_profile(profile: Profile, path: Path | None = None, *, directory: Path | None = None) -> Path:
    """Write `profile` to disk and return its path."""
    target = path if path is not None else profiles_dir(directory) / f"{_safe_filename(profile.name)}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target


def _ensure_name_free(name: str, directory: Path | None, exclude: Path | None = None) -> None:
    """Raise ProfileError when a profile with this name already exists."""
    target = profiles_dir(directory) / f"{_safe_filename(name)}.json"
    if target.exists() and target != exclude:
        raise ProfileError(f"Profil bernama '{name}' sudah ada.")


def create_profile(name: str, directory: Path | None = None) -> Profile:
    """Create and save a new empty profile."""
    profile = Profile(name=name)
    _ensure_name_free(profile.name, directory)
    save_profile(profile, directory=directory)
    return profile


def list_profiles(directory: Path | None = None) -> list[Path]:
    """All profile files, sorted by name."""
    return sorted(profiles_dir(directory).glob("*.json"))


def find_profile(name_or_path: str | Path, directory: Path | None = None) -> Path:
    """Resolve a profile given as a path or as a name inside the profile folder."""
    candidate = Path(str(name_or_path)).expanduser()
    try:
        if candidate.is_file():
            return candidate
    except OSError:
        pass  # Names that are not paths simply fall through to the folder lookup.
    for name in (str(name_or_path), f"{name_or_path}.json"):
        target = profiles_dir(directory) / _safe_filename(name)
        if target.is_file():
            return target
    raise ProfileError(f"Profil '{name_or_path}' tidak ditemukan di folder profil.")


def duplicate_profile(path: Path, new_name: str, directory: Path | None = None) -> Path:
    """Copy a profile under a new name."""
    profile = load_profile(path)
    profile.name = new_name  # re-validates via validate_assignment
    _ensure_name_free(new_name, directory)
    return save_profile(profile, directory=directory)


def rename_profile(path: Path, new_name: str, directory: Path | None = None) -> Path:
    """Rename a profile (file name follows the profile name)."""
    profile = load_profile(path)
    profile.name = new_name
    target = profiles_dir(directory) / f"{_safe_filename(new_name)}.json"
    if target == path:
        return save_profile(profile, path)
    _ensure_name_free(new_name, directory, exclude=path)
    save_profile(profile, target)
    path.unlink()
    return target


def delete_profile(path: Path) -> None:
    """Delete a profile file."""
    try:
        path.unlink()
    except FileNotFoundError:
        raise ProfileError(f"File profil '{path.name}' tidak ditemukan.") from None


def import_profile(source: Path, directory: Path | None = None) -> Path:
    """Validate an external profile file and copy it into the profile folder."""
    profile = load_profile(source)
    _ensure_name_free(profile.name, directory)
    return save_profile(profile, directory=directory)


def export_profile(path: Path, dest: Path) -> Path:
    """Validate a profile and write a copy to `dest`."""
    profile = load_profile(path)
    return save_profile(profile, dest)


def replace_sources(profile: Profile, sources: list[SourceConfig]) -> Profile:
    """Validate a modified source list by constructing the profile.

    Raises pydantic ValidationError with plain-Indonesian messages when the
    result would be invalid (duplicate names, empty keywords, ...).
    """
    return Profile(name=profile.name, input_root=profile.input_root, sources=sources)
