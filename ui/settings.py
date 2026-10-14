"""Remember the last folder and profile between sessions (settings.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Settings:
    """Tiny JSON key-value store stored beside the application.

    Losing this file only means the app forgets the last folder; never fatal.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {"last_profile": None, "last_dir": None}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass

    def get(self, key: str) -> Any:
        """Return a stored value or None."""
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        """Store a value; write failures are ignored (convenience only)."""
        self._data[key] = value
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            pass
