"""Main window: the profile bar on top and the three-step wizard below."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
)

from pydantic import ValidationError

from core.models import Profile
from core.paths import app_dir
from core.profiles import (
    ProfileError,
    create_profile,
    delete_profile,
    duplicate_profile,
    export_profile,
    find_profile,
    format_validation_error,
    import_profile,
    list_profiles,
    load_profile,
    rename_profile,
    save_profile,
)
from ui.settings import Settings
from ui.step1_sources import StepSources
from ui.step2_fields import StepData
from ui.step3_run import StepRun

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """The application window: profile management plus the three wizard steps."""

    def __init__(
        self,
        *,
        profiles_directory: Path | None = None,
        settings_path: Path | None = None,
        output_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._profiles_directory = profiles_directory
        self._settings = Settings(settings_path or app_dir() / "settings.json")
        self._output_dir = output_dir or app_dir() / "output"
        self._profile: Profile | None = None
        self._profile_path: Path | None = None
        self._loading = False
        self.setWindowTitle("SmartExcelExtractor")
        self.resize(1150, 780)

        central = QWidget()
        layout = QVBoxLayout(central)
        top = QHBoxLayout()
        top.addWidget(QLabel("Profil:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(220)
        self.profile_combo.currentIndexChanged.connect(self._on_combo_changed)
        top.addWidget(self.profile_combo)
        button_row = QHBoxLayout()
        for label, slot in (
            ("Baru", self._new_profile),
            ("Salin", self._duplicate_profile),
            ("Ubah Nama", self._rename_profile),
            ("Hapus", self._delete_profile),
            ("Impor", self._import_profile),
            ("Ekspor", self._export_profile),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            button_row.addWidget(button)
        top.addLayout(button_row)
        top.addStretch(1)
        layout.addLayout(top)

        self.wizard = QWizard()
        self.wizard.setButtonText(QWizard.BackButton, "Kembali")
        self.wizard.setButtonText(QWizard.NextButton, "Lanjut")
        self.wizard.setButtonText(QWizard.FinishButton, "Selesai")
        self.wizard.setButtonText(QWizard.CancelButton, "Tutup")
        self.wizard.rejected.connect(self.close)
        self.page_sources = StepSources(self._current, self.auto_save, self._settings)
        self.page_fields = StepData(self._current, self.auto_save)
        self.page_run = StepRun(self._current, self._output_dir)
        for page in (self.page_sources, self.page_fields, self.page_run):
            self.wizard.addPage(page)
        layout.addWidget(self.wizard, 1)
        self.setCentralWidget(central)
        self.statusBar()
        self._restore_session()

    def _current(self) -> Profile:
        """The open profile; the window always has one after start-up."""
        if self._profile is None:  # defensive: never expected
            raise RuntimeError("Tidak ada profil yang terbuka.")
        return self._profile

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        self.page_run.stop()
        super().closeEvent(event)

    def _restore_session(self) -> None:
        """Open the profile used last time, creating the first one when needed."""
        paths = list_profiles(self._profiles_directory)
        if not paths:
            try:
                profile = create_profile("Profil Baru", self._profiles_directory)
            except ProfileError as exc:
                self._warn("Tidak bisa membuat profil baru", exc)
                return
            paths = [save_profile(profile, directory=self._profiles_directory)]
        remembered = self._settings.get("last_profile")
        chosen = next((path for path in paths if str(path) == remembered), paths[0])
        self._select_path(chosen)

    def _select_path(self, path: Path) -> None:
        """Show a profile in the combo box and load it into the wizard."""
        self._refresh_combo(path)
        self._load_profile_path(path)

    def _refresh_combo(self, selected: Path | None) -> None:
        self._loading = True
        self.profile_combo.clear()
        for path in list_profiles(self._profiles_directory):
            try:
                name = load_profile(path).name
            except ProfileError:
                name = path.stem
            self.profile_combo.addItem(name, str(path))
        if selected is not None:
            index = self.profile_combo.findData(str(selected))
            if index >= 0:
                self.profile_combo.setCurrentIndex(index)
        self._loading = False

    def _load_profile_path(self, path: Path) -> None:
        try:
            profile = load_profile(path)
        except ProfileError as exc:
            self._warn("Profil tidak bisa dibuka", exc)
            return
        self._profile = profile
        self._profile_path = path
        self._settings.set("last_profile", str(path))
        self.setWindowTitle(f"SmartExcelExtractor - {profile.name}")
        self.page_sources.refresh()
        self.page_fields.refresh()

    def _on_combo_changed(self, index: int) -> None:
        if self._loading or index < 0:
            return
        path = Path(str(self.profile_combo.itemData(index)))
        if path == self._profile_path:
            return
        self._load_profile_path(path)

    def auto_save(self) -> None:
        """Write the current profile to disk; called after every edit."""
        if self._profile is None or self._profile_path is None:
            return
        try:
            save_profile(self._profile, self._profile_path)
        except OSError as exc:
            self.statusBar().showMessage(f"Perubahan belum tersimpan: {exc}", 5000)
            return
        self.statusBar().showMessage("Perubahan tersimpan otomatis.", 2000)

    def _new_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Profil baru", "Nama profil:")
        if not ok or not name.strip():
            return
        try:
            profile = create_profile(name.strip(), self._profiles_directory)
        except (ProfileError, ValidationError) as exc:
            self._warn("Tidak bisa membuat profil", exc)
            return
        self._select_path(find_profile(profile.name, self._profiles_directory))

    def _duplicate_profile(self) -> None:
        if self._profile_path is None:
            return
        name, ok = QInputDialog.getText(
            self, "Salin profil", "Nama profil baru:", text=f"{self._current().name} (salinan)"
        )
        if not ok or not name.strip():
            return
        try:
            path = duplicate_profile(self._profile_path, name.strip(), self._profiles_directory)
        except (ProfileError, ValidationError) as exc:
            self._warn("Tidak bisa menyalin profil", exc)
            return
        self._select_path(path)

    def _rename_profile(self) -> None:
        if self._profile_path is None:
            return
        name, ok = QInputDialog.getText(
            self, "Ubah nama profil", "Nama baru:", text=self._current().name
        )
        if not ok or not name.strip():
            return
        try:
            path = rename_profile(self._profile_path, name.strip(), self._profiles_directory)
        except (ProfileError, ValidationError) as exc:
            self._warn("Tidak bisa mengubah nama profil", exc)
            return
        self._select_path(path)

    def _delete_profile(self) -> None:
        if self._profile_path is None:
            return
        answer = QMessageBox.question(
            self,
            "Hapus profil",
            f"Hapus profil '{self._current().name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            delete_profile(self._profile_path)
        except ProfileError as exc:
            self._warn("Tidak bisa menghapus profil", exc)
            return
        self._profile = None
        self._profile_path = None
        self._restore_session()

    def _import_profile(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Impor profil", str(app_dir()), "File profil (*.json)"
        )
        if not source:
            return
        try:
            path = import_profile(Path(source), self._profiles_directory)
        except ProfileError as exc:
            self._warn("Tidak bisa mengimpor profil", exc)
            return
        self._select_path(path)

    def _export_profile(self) -> None:
        if self._profile_path is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Ekspor profil",
            str(Path.home() / f"{self._current().name}.json"),
            "File profil (*.json)",
        )
        if not target:
            return
        try:
            export_profile(self._profile_path, Path(target))
        except ProfileError as exc:
            self._warn("Tidak bisa mengekspor profil", exc)
            return
        self.statusBar().showMessage(f"Profil diekspor ke {target}", 5000)

    def _warn(self, title: str, exc: Exception) -> None:
        """Show a friendly problem box (the full detail already goes to the log file)."""
        message = (
            "\n".join(format_validation_error(exc))
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        logger.warning("%s: %s", title, message)
        QMessageBox.warning(self, title, message)
