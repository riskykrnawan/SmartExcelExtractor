"""Langkah 1: pick the parent folder and check the sub-folders to read."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWizardPage,
)

from core.models import Profile, SourceConfig
from ui.i18n import t
from ui.settings import Settings


class StepSources(QWizardPage):
    """Wizard page 1: folder induk plus a checklist of its sub-folders."""

    def __init__(
        self,
        get_profile: Callable[[], Profile],
        on_change: Callable[[], None],
        settings: Settings,
    ) -> None:
        super().__init__()
        self._get_profile = get_profile
        self._on_change = on_change
        self._settings = settings
        self.setTitle(t("s1.title"))
        self.setSubTitle(t("s1.subtitle"))

        layout = QVBoxLayout(self)
        folder_row = QHBoxLayout()
        self.parent_label = QLabel()
        folder_row.addWidget(self.parent_label)
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        folder_row.addWidget(self.folder_edit, 1)
        self.pick_button = QPushButton()
        self.pick_button.clicked.connect(self._pick_folder)
        folder_row.addWidget(self.pick_button)
        layout.addLayout(folder_row)

        self.subfolders_label = QLabel()
        layout.addWidget(self.subfolders_label)
        self.folder_list = QListWidget()
        self.folder_list.itemChanged.connect(self._sync_sources)
        layout.addWidget(self.folder_list, 1)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.hint_label)
        self._apply_texts()

    def _apply_texts(self) -> None:
        """Set the static widget texts in the active language."""
        self.setTitle(t("s1.title"))
        self.setSubTitle(t("s1.subtitle"))
        self.parent_label.setText(t("s1.label_parent"))
        self.pick_button.setText(t("s1.btn_pick"))
        self.subfolders_label.setText(t("s1.label_subfolders"))

    def retranslate(self) -> None:
        """Re-apply texts and rescan after a language change."""
        self._apply_texts()
        self.refresh()

    def initializePage(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Re-read the profile and rescan the sub-folder list."""
        profile = self._get_profile()
        self.folder_edit.setText(profile.input_root or t("s1.not_selected"))
        self.folder_list.blockSignals(True)
        self.folder_list.clear()
        root = Path(profile.input_root) if profile.input_root else None
        if root is None:
            self.hint_label.setText(t("s1.hint_start"))
        elif not root.is_dir():
            self.hint_label.setText(t("s1.hint_missing"))
        else:
            self.hint_label.setText(t("s1.hint_info"))
            existing = {source.folder: source.enabled for source in profile.sources}
            for path in sorted(entry for entry in root.iterdir() if entry.is_dir()):
                item = QListWidgetItem(path.name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.Checked if existing.get(path.name, False) else Qt.Unchecked
                )
                self.folder_list.addItem(item)
        self.folder_list.blockSignals(False)

    def _pick_folder(self) -> None:
        profile = self._get_profile()
        start = profile.input_root or self._settings.get("last_dir") or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, t("s1.dialog_title"), start)
        if not chosen:
            return
        profile.input_root = chosen
        self._settings.set("last_dir", chosen)
        self._on_change()
        self.refresh()

    def _sync_sources(self, *_args: object) -> None:
        """Mirror the checkboxes into the profile, keeping configured sheets/fields."""
        profile = self._get_profile()
        checked = {
            self.folder_list.item(index).text()
            for index in range(self.folder_list.count())
            if self.folder_list.item(index).checkState() == Qt.Checked
        }
        listed = {
            self.folder_list.item(index).text() for index in range(self.folder_list.count())
        }
        existing_names = {source.folder for source in profile.sources}
        updated: list[SourceConfig] = []
        for source in profile.sources:
            # Only folders visible in the list are touched; missing folders keep
            # their configuration (a disconnected drive must not wipe settings).
            if source.folder in listed:
                source.enabled = source.folder in checked
            updated.append(source)
        for name in sorted(checked):
            if name not in existing_names:
                updated.append(SourceConfig(folder=name, enabled=True))
        profile.sources = updated
        self._on_change()
