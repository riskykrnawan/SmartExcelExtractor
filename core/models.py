"""Configuration models for a profile (Pydantic v2).

Validation messages are plain Indonesian because non-technical users read them
directly in the UI and CLI.
"""
from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MatchMode(StrEnum):
    """How a keyword is compared against a cell (UI shows plain-language labels)."""

    EXACT = "exact"  # UI: Sama persis (default)
    CONTAINS = "contains"  # UI: Mengandung
    STARTS_WITH = "starts_with"  # UI: Diawali dengan
    ENDS_WITH = "ends_with"  # UI: Diakhiri dengan
    REGEX = "regex"  # UI: mode Lanjutan (hidden by default)


class DataType(StrEnum):
    """Expected value type for a field."""

    ANY = "any"  # UI: Apa saja (default)
    NUMBER = "number"  # UI: Angka
    TEXT = "text"  # UI: Teks
    DATE = "date"  # UI: Tanggal


class ValueDirection(StrEnum):
    """Where the value sits relative to the row keyword (when there is no column keyword)."""

    RIGHT = "right"
    LEFT = "left"
    DOWN = "down"
    UP = "up"


class DisambiguationMode(StrEnum):
    """How one occurrence is picked when a keyword appears more than once."""

    BY_ADDRESS = "by_address"
    NEAR_KEYWORD = "near_keyword"
    NOT_NEAR_KEYWORD = "not_near_keyword"


_OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_ADDRESS_RE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")


class KeywordConfig(BaseModel):
    """One keyword rule: the text to look for and how to pick a cell."""

    text: str = ""
    match_mode: MatchMode = MatchMode.EXACT
    case_sensitive: bool = False
    is_unique: bool = True
    disambiguation: DisambiguationMode | None = None
    reference_address: str | None = None
    reference_keyword: KeywordConfig | None = None
    radius: int = Field(default=10, ge=1, le=10_000)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("reference_address")
    @classmethod
    def _normalize_address(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        address = value.strip().upper()
        if not _ADDRESS_RE.match(address):
            raise ValueError("Alamat sel tidak dikenali. Contoh format yang benar: I45.")
        return address

    @model_validator(mode="after")
    def _check_rules(self) -> KeywordConfig:
        if self.match_mode is MatchMode.REGEX and self.text:
            try:
                re.compile(self.text)
            except re.error as exc:
                raise ValueError(f"Mode Lanjutan: pola tidak valid ({exc}).") from exc
        if self.is_unique:
            return self
        if self.disambiguation is None:
            raise ValueError(
                "Belum memilih cara menentukan tulisan yang dipakai "
                "('Kalau muncul lebih dari sekali...')."
            )
        if self.disambiguation is DisambiguationMode.BY_ADDRESS:
            if not self.reference_address:
                raise ValueError("Isian alamat sel belum diisi (contoh: I45).")
        elif not self.reference_address and not (
            self.reference_keyword is not None and self.reference_keyword.text
        ):
            raise ValueError("Isian pembanding (alamat sel atau tulisan) belum diisi.")
        return self


class FieldConfig(BaseModel):
    """One extraction rule: a unique output name plus row/column keywords."""

    output_name: str
    row_keyword: KeywordConfig
    col_keyword: KeywordConfig | None = None
    value_direction: ValueDirection = ValueDirection.RIGHT
    value_offset: int = Field(default=1, ge=1, le=10_000)
    data_type: DataType = DataType.ANY
    allow_empty: bool = False

    @field_validator("output_name")
    @classmethod
    def _check_output_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nama untuk hasil ini tidak boleh kosong.")
        if not _OUTPUT_NAME_RE.match(value):
            raise ValueError(
                "Nama untuk hasil ini hanya boleh berisi huruf (a-z, A-Z), angka, dan garis bawah (_)."
            )
        return value

    @model_validator(mode="after")
    def _check_keywords(self) -> FieldConfig:
        if not self.row_keyword.text:
            raise ValueError(f"Field '{self.output_name}': 'Cari baris yang bertuliskan...' belum diisi.")
        if self.col_keyword is not None and not self.col_keyword.text:
            raise ValueError(
                f"Field '{self.output_name}': 'Cari kolom yang bertuliskan...' kosong - "
                "kalau tidak memakai kolom, kosongkan saja pilihannya."
            )
        return self


class SheetConfig(BaseModel):
    """A sheet inside a source folder; the name may match with any MatchMode."""

    name: str
    match_mode: MatchMode = MatchMode.EXACT
    fields: list[FieldConfig] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nama sheet tidak boleh kosong.")
        return value


class SourceConfig(BaseModel):
    """A checked sub-folder of the input root (relative name keeps profiles portable)."""

    folder: str
    enabled: bool = True
    sheets: list[SheetConfig] = Field(default_factory=list)

    @field_validator("folder")
    @classmethod
    def _strip_folder(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nama folder sumber tidak boleh kosong.")
        return value


class Profile(BaseModel):
    """A full configuration: one profile per factory ("Pabrik A")."""

    model_config = ConfigDict(validate_assignment=True)

    schema_version: int = 1
    name: str
    input_root: str | None = None
    sources: list[SourceConfig] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_profile_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nama profil tidak boleh kosong.")
        return value

    @field_validator("input_root")
    @classmethod
    def _blank_root_to_none(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _check_unique_names(self) -> Profile:
        seen_sources: set[str] = set()
        seen_outputs: set[str] = set()
        for source in self.sources:
            if source.folder in seen_sources:
                raise ValueError(f"Sumber folder '{source.folder}' muncul lebih dari sekali.")
            seen_sources.add(source.folder)
            seen_sheets: set[str] = set()
            for sheet in source.sheets:
                if sheet.name in seen_sheets:
                    raise ValueError(
                        f"Sheet '{sheet.name}' muncul lebih dari sekali di sumber '{source.folder}'."
                    )
                seen_sheets.add(sheet.name)
                for field in sheet.fields:
                    if field.output_name in seen_outputs:
                        raise ValueError(
                            f"Nama hasil '{field.output_name}' dipakai lebih dari satu kali dalam profil."
                        )
                    seen_outputs.add(field.output_name)
        return self
