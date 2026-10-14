"""Shared fixtures: messy sample workbooks generated once per session."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.generate_samples import generate


@pytest.fixture(scope="session")
def samples_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate the three sample variants once for the whole test session."""
    root = tmp_path_factory.mktemp("samples")
    for variant in ("a", "b", "c"):
        generate(root, variant)
    return root


@pytest.fixture(scope="session")
def input_a(samples_root: Path) -> Path:
    """Sample input for variant a (base layout)."""
    return samples_root / "input_a"


@pytest.fixture(scope="session")
def input_b(samples_root: Path) -> Path:
    """Sample input for variant b (data shifted +3 rows, +1 column)."""
    return samples_root / "input_b"
