"""Field edit form: plain-language labels plus a live preview pane."""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from pydantic import ValidationError

from core.models import (
    DataType,
    DisambiguationMode,
    FieldConfig,
    KeywordConfig,
    MatchMode,
    Profile,
    SheetConfig,
    SourceConfig,
    ValueDirection,
)
from core.profiles import format_validation_error, replace_sources
from ui.preview import PreviewPane

#: UI labels for the matching modes; "Lanjutan" stays hidden by default.
MATCH_MODE_LABELS: list[tuple[str, MatchMode]] = [
    ("Sama persis", MatchMode.EXACT),
    ("Mengandung", MatchMode.CONTAINS),
    ("Diawali dengan", MatchMode.STARTS_WITH),
    ("Diakhiri dengan", MatchMode.ENDS_WITH),
    ("Lanjutan", MatchMode.REGEX),
]
HIDDEN_MODE_INDEX = 4  # the "Lanjutan" entry

DISAMBIGUATION_LABELS: list[tuple[str, DisambiguationMode]] = [
    ("Paling dekat ke alamat sel yang saya tentukan", DisambiguationMode.BY_ADDRESS),
    ("Paling dekat ke tulisan pembanding", DisambiguationMode.NEAR_KEYWORD),
    ("Tidak dekat dengan tulisan pembanding", DisambiguationMode.NOT_NEAR_KEYWORD),
]

REFERENCE_MODE_LABELS: list[tuple[str, MatchMode]] = MATCH_MODE_LABELS[:4]

DATA_TYPE_LABELS: list[tuple[str, DataType]] = [
    ("Apa saja", DataType.ANY),
    ("Angka", DataType.NUMBER),
    ("Teks", DataType.TEXT),
    ("Tanggal", DataType.DATE),
]

DIRECTION_LABELS: list[tuple[str, ValueDirection]] = [
    ("di sebelah kanan", ValueDirection.RIGHT),
    ("di sebelah kiri", ValueDirection.LEFT),
    ("di bawah", ValueDirection.DOWN),
    ("di atas", ValueDirection.UP),
]

TIP_NAME = (
    "Huruf, angka, dan garis bawah saja. Contoh: prod_hi. "
    "Nama harus berbeda dari data lain di profil ini."
)
TIP_ROW = (
    "Tulis tulisan yang ada di baris, misalnya: Produksi Harian. "
    "Spasi berlebih dan huruf besar/kecil mengikuti pilihan di bawah."
)
TIP_COL = (
    "Tulis tulisan di kolom yang nilainya diambil, misalnya: Total. "
    "Kalau datanya berbentuk 'label: nilai', kosongkan saja isian ini."
)


def mode_help_text(mode: MatchMode, text: str, case_sensitive: bool) -> str:
    """One plain-language sentence with live examples for the chosen mode."""
    sample = text.strip() or "Produksi Harian"
    if mode is MatchMode.EXACT:
        variants = f"'{sample}'"
        if not case_sensitive:
            variants += f", '{sample.lower()}'"
        return f"Akan cocok dengan: {variants} - Tidak cocok dengan: '{sample} Total'"
    if mode is MatchMode.CONTAINS:
        return f"Akan cocok dengan: 'Rekap {sample}' - Tidak cocok dengan: '{sample[:-1]}'"
    if mode is MatchMode.STARTS_WITH:
        return f"Akan cocok dengan: '{sample} 01' - Tidak cocok dengan: 'Rekap {sample}'"
    if mode is MatchMode.ENDS_WITH:
        return f"Akan cocok dengan: 'Rekap {sample}' - Tidak cocok dengan: '{sample} 01'"
    return "Mode Lanjutan: pola tulisan khusus, untuk pengguna terlatih saja."


def select_by_data(combo: QComboBox, data: object) -> None:
    """Select the combo entry whose stored value equals `data`."""
    for index in range(combo.count()):
        if combo.itemData(index) == data:
            combo.setCurrentIndex(index)
            return


def fill_combo(combo: QComboBox, labels: Sequence[tuple[str, object]]) -> None:
    """Fill a combo box from (label, value) pairs."""
    for label, value in labels:
        combo.addItem(label, value)


class HelpButton(QToolButton):
    """A small '?' button that shows a plain-language tip when clicked."""

    def __init__(self, tip: str) -> None:
        super().__init__()
        self.setText("?")
        self.setToolTip(tip)
        self.setFixedWidth(24)
        self.clicked.connect(
            lambda: QToolTip.showText(self.mapToGlobal(QPoint(0, self.height())), tip, self)
        )


class KeywordEditor(QWidget):
    """One keyword: text, match mode, case option, uniqueness, disambiguation."""

    changed = Signal()

    def __init__(
        self,
        prompt: str,
        tooltip: str,
        *,
        with_unique: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._with_unique = with_unique
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(QLabel(f"<b>{prompt}</b>"))
        head.addWidget(HelpButton(tooltip))
        head.addStretch(1)
        layout.addLayout(head)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Tulis kata kunci...")
        layout.addWidget(self.edit)

        options = QHBoxLayout()
        options.addWidget(QLabel("Cara mencocokkan:"))
        self.mode_combo = QComboBox()
        fill_combo(self.mode_combo, MATCH_MODE_LABELS)
        # Qt6 has no per-item hide flag; hide the popup row instead.
        self.mode_combo.view().setRowHidden(HIDDEN_MODE_INDEX, True)  # "Lanjutan"
        options.addWidget(self.mode_combo)
        self.case_check = QCheckBox("Bedakan huruf besar/kecil")
        options.addWidget(self.case_check)
        options.addStretch(1)
        layout.addLayout(options)

        self.help_label = QLabel("")
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.help_label)

        self.unique_check = QCheckBox("Tulisan ini hanya muncul satu kali di sheet")
        self.unique_check.setChecked(True)
        layout.addWidget(self.unique_check)

        self.extra_group = QGroupBox("Kalau muncul lebih dari sekali...")
        extra_layout = QVBoxLayout(self.extra_group)
        extra_layout.addWidget(QLabel("Cara memilih yang dipakai:"))
        self.disambiguation_combo = QComboBox()
        fill_combo(self.disambiguation_combo, DISAMBIGUATION_LABELS)
        extra_layout.addWidget(self.disambiguation_combo)

        self.extra_stack = QStackedWidget()
        self.extra_stack.addWidget(self._build_address_page())
        self.extra_stack.addWidget(self._build_near_page())
        self.extra_stack.addWidget(self._build_away_page())
        extra_layout.addWidget(self.extra_stack)
        layout.addWidget(self.extra_group)

        self.edit.textChanged.connect(self._on_any_change)
        self.mode_combo.currentIndexChanged.connect(self._on_any_change)
        self.case_check.toggled.connect(self._on_any_change)
        self.unique_check.toggled.connect(self._on_visibility_change)
        self.disambiguation_combo.currentIndexChanged.connect(self._on_disambiguation_change)
        for widget in (
            self.address_edit,
            self.near_text_edit,
            self.near_address_edit,
            self.away_text_edit,
            self.away_address_edit,
        ):
            widget.textChanged.connect(self.changed)
        for combo in (self.near_mode_combo, self.away_mode_combo):
            combo.currentIndexChanged.connect(self.changed)
        self.radius_spin.valueChanged.connect(self.changed)
        self._update_help()
        self._update_visibility()

    def _build_address_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Alamat sel acuan (contoh: I45):"))
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("Contoh: I45")
        layout.addWidget(self.address_edit)
        return page

    def _build_reference_inputs(self, layout: QVBoxLayout) -> tuple[QLineEdit, QComboBox, QLineEdit]:
        """Shared 'comparison' inputs: text + its own mode + optional address."""
        layout.addWidget(QLabel("Tulisan pembanding (contoh: SECTION PRODUKSI):"))
        text_edit = QLineEdit()
        layout.addWidget(text_edit)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Cara mencocokkan pembanding:"))
        mode_combo = QComboBox()
        fill_combo(mode_combo, REFERENCE_MODE_LABELS)
        mode_row.addWidget(mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)
        layout.addWidget(QLabel("...atau alamat sel (kosongkan bila memakai tulisan):"))
        address_edit = QLineEdit()
        address_edit.setPlaceholderText("Contoh: I45")
        layout.addWidget(address_edit)
        return text_edit, mode_combo, address_edit

    def _build_near_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.near_text_edit, self.near_mode_combo, self.near_address_edit = (
            self._build_reference_inputs(layout)
        )
        return page

    def _build_away_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.away_text_edit, self.away_mode_combo, self.away_address_edit = (
            self._build_reference_inputs(layout)
        )
        radius_row = QHBoxLayout()
        radius_row.addWidget(QLabel("Jarak 'dekat' (jumlah sel):"))
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(1, 10_000)
        self.radius_spin.setValue(10)
        radius_row.addWidget(self.radius_spin)
        radius_row.addStretch(1)
        layout.addLayout(radius_row)
        layout.addWidget(QLabel("Kemunculan dalam jarak ini dianggap dekat dan dibuang."))
        return page

    def config(self) -> KeywordConfig:
        """Build the keyword from the current inputs (pydantic validates the rules)."""
        disambiguation: DisambiguationMode | None = None
        reference_address: str | None = None
        reference_keyword: KeywordConfig | None = None
        is_unique = self.unique_check.isChecked()
        if self._with_unique and not is_unique:
            disambiguation = DisambiguationMode(self.disambiguation_combo.currentData())
            if disambiguation is DisambiguationMode.BY_ADDRESS:
                reference_address = self.address_edit.text().strip() or None
            elif disambiguation is DisambiguationMode.NEAR_KEYWORD:
                reference_address = self.near_address_edit.text().strip() or None
                ref_text = self.near_text_edit.text().strip()
                if ref_text:
                    reference_keyword = KeywordConfig(
                        text=ref_text,
                        match_mode=MatchMode(self.near_mode_combo.currentData()),
                    )
            else:
                reference_address = self.away_address_edit.text().strip() or None
                ref_text = self.away_text_edit.text().strip()
                if ref_text:
                    reference_keyword = KeywordConfig(
                        text=ref_text,
                        match_mode=MatchMode(self.away_mode_combo.currentData()),
                    )
        return KeywordConfig(
            text=self.edit.text(),
            match_mode=MatchMode(self.mode_combo.currentData()),
            case_sensitive=self.case_check.isChecked(),
            is_unique=is_unique,
            disambiguation=disambiguation,
            reference_address=reference_address,
            reference_keyword=reference_keyword,
            radius=self.radius_spin.value(),
        )

    def set_config(self, config: KeywordConfig | None) -> None:
        """Load a keyword into the widgets (None resets to the defaults)."""
        self._loading = True
        try:
            self.edit.setText(config.text if config else "")
            select_by_data(self.mode_combo, config.match_mode if config else MatchMode.EXACT)
            self.case_check.setChecked(config.case_sensitive if config else False)
            self.unique_check.setChecked(config.is_unique if config else True)
            select_by_data(
                self.disambiguation_combo,
                (config.disambiguation if config else None) or DisambiguationMode.BY_ADDRESS,
            )
            reference_keyword = config.reference_keyword if config else None
            reference_address = config.reference_address if config else None
            if reference_keyword is not None:
                self.near_text_edit.setText(reference_keyword.text)
                select_by_data(self.near_mode_combo, reference_keyword.match_mode)
                self.away_text_edit.setText(reference_keyword.text)
                select_by_data(self.away_mode_combo, reference_keyword.match_mode)
            else:
                self.near_text_edit.setText("")
                self.away_text_edit.setText("")
            self.near_address_edit.setText(reference_address or "")
            self.away_address_edit.setText(reference_address or "")
            self.address_edit.setText(reference_address or "")
            self.radius_spin.setValue(config.radius if config else 10)
        finally:
            self._loading = False
        self._on_disambiguation_change(emit=False)
        self._update_help()
        self._update_visibility()

    def _on_any_change(self, *_args: object) -> None:
        self._update_help()
        self.changed.emit()

    def _on_visibility_change(self, *_args: object) -> None:
        self._update_visibility()
        self.changed.emit()

    def _on_disambiguation_change(self, *_args: object, emit: bool = True) -> None:
        mode = DisambiguationMode(self.disambiguation_combo.currentData())
        page = {
            DisambiguationMode.BY_ADDRESS: 0,
            DisambiguationMode.NEAR_KEYWORD: 1,
            DisambiguationMode.NOT_NEAR_KEYWORD: 2,
        }[mode]
        self.extra_stack.setCurrentIndex(page)
        if emit and not self._loading:
            self.changed.emit()

    def _update_help(self) -> None:
        mode = MatchMode(self.mode_combo.currentData())
        self.help_label.setText(
            mode_help_text(mode, self.edit.text(), self.case_check.isChecked())
        )

    def _update_visibility(self) -> None:
        """Unique/disambiguation blocks only exist for a filled, non-unique keyword."""
        has_text = bool(self.edit.text().strip())
        self.unique_check.setVisible(self._with_unique and has_text)
        self.extra_group.setVisible(self._with_unique and has_text and not self.unique_check.isChecked())


class FieldFormDialog(QDialog):
    """Edit one field: plain-language form on the left, live preview on the right."""

    def __init__(
        self,
        parent: QWidget | None,
        profile: Profile,
        folder: str,
        sheet: SheetConfig,
        field: FieldConfig | None,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._folder = folder
        self._sheet = sheet
        self._original = field
        self._loading = False
        #: The validated sources to apply after a successful save (set in accept).
        self.sources: list[SourceConfig] | None = None
        self.field: FieldConfig | None = None
        self.setWindowTitle("Data baru" if field is None else f"Ubah data '{field.output_name}'")
        self.resize(1150, 740)

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form = QVBoxLayout(form_widget)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("<b>Nama untuk hasil ini</b>"))
        name_row.addWidget(HelpButton(TIP_NAME))
        name_row.addStretch(1)
        form.addLayout(name_row)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Contoh: prod_hi")
        form.addWidget(self.name_edit)

        self.row_editor = KeywordEditor("Cari baris yang bertuliskan...", TIP_ROW)
        form.addWidget(self.row_editor)
        self.col_editor = KeywordEditor(
            "Cari kolom yang bertuliskan (boleh dikosongkan)...", TIP_COL
        )
        form.addWidget(self.col_editor)

        self.offset_group = QGroupBox("Kalau kolom kosong, ambil nilai yang...")
        offset_row = QHBoxLayout(self.offset_group)
        self.direction_combo = QComboBox()
        fill_combo(self.direction_combo, DIRECTION_LABELS)
        offset_row.addWidget(self.direction_combo)
        offset_row.addWidget(QLabel("dari tulisan baris, geser"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(1, 10_000)
        self.offset_spin.setValue(1)
        offset_row.addWidget(self.offset_spin)
        offset_row.addWidget(QLabel("sel"))
        offset_row.addStretch(1)
        form.addWidget(self.offset_group)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("<b>Tipe data yang diharapkan</b>"))
        self.type_combo = QComboBox()
        fill_combo(self.type_combo, DATA_TYPE_LABELS)
        type_row.addWidget(self.type_combo)
        type_row.addStretch(1)
        form.addLayout(type_row)
        form.addWidget(
            QLabel("Kalau nilainya tidak sesuai, muncul peringatan; nilai asli tetap disimpan.")
        )
        self.allow_empty_check = QCheckBox("Nilai kosong tidak dianggap masalah")
        form.addWidget(self.allow_empty_check)
        form.addWidget(QLabel("Kalau tidak dicentang, nilai kosong ditandai 'perlu dicek'."))
        form.addStretch(1)
        form_scroll.setWidget(form_widget)
        body.addWidget(form_scroll, 3)

        self.preview = PreviewPane()
        self.preview.setMinimumWidth(430)
        body.addWidget(self.preview, 2)
        root.addLayout(body, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Simpan")
        buttons.button(QDialogButtonBox.Cancel).setText("Batal")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._populate()
        self.name_edit.textChanged.connect(self._on_changed)
        self.row_editor.changed.connect(self._on_changed)
        self.col_editor.changed.connect(self._on_changed)
        self.col_editor.edit.textChanged.connect(self._on_col_text_changed)
        self.direction_combo.currentIndexChanged.connect(self._on_changed)
        self.offset_spin.valueChanged.connect(self._on_changed)
        self.type_combo.currentIndexChanged.connect(self._on_changed)
        self.allow_empty_check.toggled.connect(self._on_changed)
        self._update_offset_visibility()
        self.preview.set_context(profile, sheet, self.current_field)

    def _populate(self) -> None:
        """Load the current field (or defaults) into the widgets."""
        field = self._original
        self._loading = True
        try:
            self.name_edit.setText(field.output_name if field else "")
            self.row_editor.set_config(field.row_keyword if field else None)
            self.col_editor.set_config(field.col_keyword if field else None)
            select_by_data(
                self.direction_combo, field.value_direction if field else ValueDirection.RIGHT
            )
            self.offset_spin.setValue(field.value_offset if field else 1)
            select_by_data(self.type_combo, field.data_type if field else DataType.ANY)
            self.allow_empty_check.setChecked(field.allow_empty if field else False)
        finally:
            self._loading = False

    def _on_changed(self, *_args: object) -> None:
        if not self._loading:
            self.preview.schedule_refresh()

    def _on_col_text_changed(self, *_args: object) -> None:
        self._update_offset_visibility()
        self._on_changed()

    def _update_offset_visibility(self) -> None:
        """The offset block only exists when there is no column keyword."""
        self.offset_group.setVisible(not self.col_editor.edit.text().strip())

    def current_field(self) -> FieldConfig | None:
        """Current field for the live preview; None while the form is incomplete."""
        try:
            return self._build_field()
        except ValidationError:
            return None

    def _build_field(self) -> FieldConfig:
        """Compose the FieldConfig; pydantic raises plain-Indonesian errors."""
        col_keyword = None
        if self.col_editor.edit.text().strip():
            col_keyword = self.col_editor.config()
        return FieldConfig(
            output_name=self.name_edit.text(),
            row_keyword=self.row_editor.config(),
            col_keyword=col_keyword,
            value_direction=ValueDirection(self.direction_combo.currentData()),
            value_offset=self.offset_spin.value(),
            data_type=DataType(self.type_combo.currentData()),
            allow_empty=self.allow_empty_check.isChecked(),
        )

    def _prospective_sources(self, field: FieldConfig) -> list[SourceConfig]:
        """The profile's sources with this field added or replaced."""
        sources: list[SourceConfig] = []
        for source in self._profile.sources:
            if source.folder != self._folder:
                sources.append(source)
                continue
            sheets: list[SheetConfig] = []
            for sheet in source.sheets:
                if sheet.name != self._sheet.name:
                    sheets.append(sheet)
                    continue
                fields: list[FieldConfig] = []
                for existing in sheet.fields:
                    replacing = (
                        self._original is not None
                        and existing.output_name == self._original.output_name
                    )
                    fields.append(field if replacing else existing)
                if self._original is None:
                    fields.append(field)
                sheets.append(sheet.model_copy(update={"fields": fields}))
            sources.append(source.model_copy(update={"sheets": sheets}))
        return sources

    def accept(self) -> None:
        """Validate the whole profile view, then hand the result to the caller."""
        try:
            field = self._build_field()
            sources = self._prospective_sources(field)
            replace_sources(self._profile, sources)
        except ValidationError as exc:
            QMessageBox.warning(
                self, "Data belum bisa disimpan", "\n".join(format_validation_error(exc))
            )
            return
        except ValueError as exc:
            QMessageBox.warning(self, "Data belum bisa disimpan", str(exc))
            return
        self.field = field
        self.sources = sources
        super().accept()
