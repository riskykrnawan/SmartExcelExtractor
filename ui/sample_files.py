"""Locate sample Excel files and their sheet names for dropdowns and preview."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from core.cell_index import list_excel_files, load_workbook_pair
from core.models import Profile

logger = logging.getLogger(__name__)

#: path -> (file modification time, sheet names). See sheet_titles().
_TITLE_CACHE: dict[Path, tuple[float, list[str]]] = {}


@dataclass(frozen=True)
class SampleFile:
    """One selectable sample: the newest Excel file of a source folder."""

    folder: str
    input_root: str
    path: Path

    @property
    def label(self) -> str:
        """Display text for the sample dropdown."""
        return f"{self.folder} - {self.path.name}"


def sample_files(profile: Profile) -> list[SampleFile]:
    """Newest Excel file of every enabled source (folders may not exist yet)."""
    samples: list[SampleFile] = []
    if not profile.input_root:
        return samples
    root = Path(profile.input_root)
    for source in profile.sources:
        if not source.enabled:
            continue
        files = list_excel_files(root / source.folder)
        if files:
            samples.append(
                SampleFile(folder=source.folder, input_root=profile.input_root, path=files[0])
            )
    return samples


def sheet_titles(sample: SampleFile) -> list[str]:
    """Sheet names inside a sample file; empty when the file cannot be opened.

    Cached per file and modification time: the tree in Langkah 2 asks for these on every
    rebuild, and reopening a large workbook each time made the window feel stuck.
    """
    try:
        stamp = sample.path.stat().st_mtime
    except OSError:
        return []
    cached = _TITLE_CACHE.get(sample.path)
    if cached is not None and cached[0] == stamp:
        return list(cached[1])
    try:
        wb = load_workbook_pair(sample.path)
    except Exception:  # noqa: BLE001 - the dropdown simply stays manual
        logger.warning("Cannot read sheet names of %s", sample.path)
        return []
    try:
        titles = wb.sheet_titles()
    finally:
        wb.close()
    _TITLE_CACHE[sample.path] = (stamp, titles)
    return list(titles)
