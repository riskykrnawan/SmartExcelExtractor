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
from ui.i18n import t
from ui.preview import PreviewPane

#: Index of the "Lanjutan" (advanced) match mode; it stays hidden by default.
HIDDEN_MODE_INDEX = 4


def match_mode_labels() -> list[tuple[str, MatchMode]]:
    """Matching-mode labels, in the active language."""
    return [
        (t("mode.exact"), MatchMode.EXACT),
        (t("mode.contains"), MatchMode.CONTAINS),
        (t("mode.starts"), MatchMode.STARTS_WITH),
        (t("mode.ends"), MatchMode.ENDS_WITH),
        (t("mode.regex"), MatchMode.REGEX),
    ]


def reference_mode_labels() -> list[tuple[str, MatchMode]]:
    """Match modes offered for a comparison keyword (no advanced mode)."""
    return match_mode_labels()[:4]


def disambiguation_labels() -> list[tuple[str, DisambiguationMode]]:
    """Disambiguation-choice labels, in the active language."""
    return [
        (t("dis.by_address"), DisambiguationMode.BY_ADDRESS),
        (t("dis.near"), DisambiguationMode.NEAR_KEYWORD),
        (t("dis.not_near"), DisambiguationMode.NOT_NEAR_KEYWORD),
    ]


def data_type_labels() -> list[tuple[str, DataType]]:
    """Data-type labels, in the active language."""
    return [
        (t("type.any"), DataType.ANY),
        (t("type.number"), DataType.NUMBER),
        (t("type.text"), DataType.TEXT),
        (t("type.date"), DataType.DATE),
    ]


def direction_labels() -> list[tuple[str, ValueDirection]]:
    """Value-direction labels, in the active language."""
    return [
        (t("dir.right"), ValueDirection.RIGHT),
        (t("dir.left"), ValueDirection.LEFT),
        (t("dir.down"), ValueDirection.DOWN),
        (t("dir.up"), ValueDirection.UP),
    ]

def mode_help_text(mode: MatchMode, text: str, case_sensitive: bool) -> str:
    """One plain-language sentence with live examples for the chosen mode."""
    sample = text.strip() or "Produksi Harian"
    if mode is MatchMode.EXACT:
        variants = f"'{sample}'"
        if not case_sensitive:
            variants += f", '{sample.lower()}'"
        return t("help.exact", matches=variants, sample=sample)
    if mode is MatchMode.CONTAINS:
        return t("help.contains", sample=sample, short=sample[:-1])
    if mode is MatchMode.STARTS_WITH:
        return t("help.starts", sample=sample)
    if mode is MatchMode.ENDS_WITH:
        return t("help.ends", sample=sample)
    return t("help.regex")


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
        self.edit.setPlaceholderText(t("ke.placeholder"))
        layout.addWidget(self.edit)

        options = QHBoxLayout()
        options.addWidget(QLabel(t("ke.label_match")))
        self.mode_combo = QComboBox()
        fill_combo(self.mode_combo, match_mode_labels())
        # Qt6 has no per-item hide flag; hide the popup row instead.
        self.mode_combo.view().setRowHidden(HIDDEN_MODE_INDEX, True)  # "Lanjutan"
        options.addWidget(self.mode_combo)
        self.case_check = QCheckBox(t("ke.case"))
        options.addWidget(self.case_check)
        options.addStretch(1)
        layout.addLayout(options)

        self.help_label = QLabel("")
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.help_label)

        self.unique_check = QCheckBox(t("ke.unique"))
        self.unique_check.setChecked(True)
        layout.addWidget(self.unique_check)

        self.extra_group = QGroupBox(t("ke.extra_group"))
        extra_layout = QVBoxLayout(self.extra_group)
        extra_layout.addWidget(QLabel(t("ke.label_choose")))
        self.disambiguation_combo = QComboBox()
        fill_combo(self.disambiguation_combo, disambiguation_labels())
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
        layout.addWidget(QLabel(t("ke.address_label")))
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText(t("ke.address_placeholder"))
        layout.addWidget(self.address_edit)
        return page

    def _build_reference_inputs(self, layout: QVBoxLayout) -> tuple[QLineEdit, QComboBox, QLineEdit]:
        """Shared 'comparison' inputs: text + its own mode + optional address."""
        layout.addWidget(QLabel(t("ke.ref_label")))
        text_edit = QLineEdit()
        layout.addWidget(text_edit)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(t("ke.ref_match")))
        mode_combo = QComboBox()
        fill_combo(mode_combo, reference_mode_labels())
        mode_row.addWidget(mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)
        layout.addWidget(QLabel(t("ke.ref_address")))
        address_edit = QLineEdit()
        address_edit.setPlaceholderText(t("ke.address_placeholder"))
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
        radius_row.addWidget(QLabel(t("ke.radius_label")))
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(1, 10_000)
        self.radius_spin.setValue(10)
        radius_row.addWidget(self.radius_spin)
        radius_row.addStretch(1)
        layout.addLayout(radius_row)
        layout.addWidget(QLabel(t("ke.radius_note")))
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
        self.setWindowTitle(
            t("ff.title_new") if field is None else t("ff.title_edit", name=field.output_name)
        )
        self.resize(1150, 740)

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form = QVBoxLayout(form_widget)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(t("ff.label_name")))
        name_row.addWidget(HelpButton(t("tip.name")))
        name_row.addStretch(1)
        form.addLayout(name_row)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(t("ff.name_placeholder"))
        form.addWidget(self.name_edit)

        self.row_editor = KeywordEditor(t("ff.prompt_row"), t("tip.row"))
        form.addWidget(self.row_editor)
        self.col_editor = KeywordEditor(t("ff.prompt_col"), t("tip.col"))
        form.addWidget(self.col_editor)

        self.offset_group = QGroupBox(t("ff.offset_group"))
        offset_row = QHBoxLayout(self.offset_group)
        self.direction_combo = QComboBox()
        fill_combo(self.direction_combo, direction_labels())
        offset_row.addWidget(self.direction_combo)
        offset_row.addWidget(QLabel(t("ff.offset_from")))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(1, 10_000)
        self.offset_spin.setValue(1)
        offset_row.addWidget(self.offset_spin)
        offset_row.addWidget(QLabel(t("ff.offset_cells")))
        offset_row.addStretch(1)
        form.addWidget(self.offset_group)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(t("ff.label_type")))
        self.type_combo = QComboBox()
        fill_combo(self.type_combo, data_type_labels())
        type_row.addWidget(self.type_combo)
        type_row.addStretch(1)
        form.addLayout(type_row)
        form.addWidget(QLabel(t("ff.type_note")))
        self.allow_empty_check = QCheckBox(t("ff.allow_empty"))
        form.addWidget(self.allow_empty_check)
        form.addWidget(QLabel(t("ff.allow_empty_note")))
        form.addStretch(1)
        form_scroll.setWidget(form_widget)
        body.addWidget(form_scroll, 3)

        self.preview = PreviewPane()
        self.preview.setMinimumWidth(430)
        body.addWidget(self.preview, 2)
        root.addLayout(body, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(t("ff.btn_save"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("ff.btn_cancel"))
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
                self, t("ff.err_save"), "\n".join(format_validation_error(exc))
            )
            return
        except ValueError as exc:
            QMessageBox.warning(self, t("ff.err_save"), str(exc))
            return
        self.field = field
        self.sources = sources
        super().accept()
