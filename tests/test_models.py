"""Profile validation: rules enforced, messages in plain Indonesian."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models import (
    DisambiguationMode,
    FieldConfig,
    KeywordConfig,
    MatchMode,
    Profile,
    SheetConfig,
    SourceConfig,
)


def field(output_name: str = "hasil", **kwargs: object) -> FieldConfig:
    """Build a valid field; kwargs override row/col keyword defaults."""
    row = kwargs.pop("row", None) or KeywordConfig(text="Label")
    col = kwargs.pop("col", None)
    return FieldConfig(output_name=output_name, row_keyword=row, col_keyword=col, **kwargs)  # type: ignore[arg-type]


class TestFieldValidation:
    def test_output_name_rejects_spaces(self) -> None:
        with pytest.raises(ValidationError, match="huruf"):
            FieldConfig(output_name="prod hi", row_keyword=KeywordConfig(text="Label"))

    def test_output_name_rejects_empty(self) -> None:
        with pytest.raises(ValidationError, match="tidak boleh kosong"):
            FieldConfig(output_name="  ", row_keyword=KeywordConfig(text="Label"))

    def test_empty_row_keyword_rejected(self) -> None:
        with pytest.raises(ValidationError, match="belum diisi"):
            FieldConfig(output_name="x", row_keyword=KeywordConfig(text=""))

    def test_empty_col_keyword_rejected(self) -> None:
        with pytest.raises(ValidationError, match="kosongkan saja"):
            FieldConfig(
                output_name="x",
                row_keyword=KeywordConfig(text="Label"),
                col_keyword=KeywordConfig(text=""),
            )

    def test_value_offset_default_is_one(self) -> None:
        assert field().value_offset == 1


class TestKeywordRules:
    def test_unique_keyword_needs_no_disambiguation(self) -> None:
        KeywordConfig(text="Label")  # default is_unique=True: no error

    def test_not_unique_requires_disambiguation_choice(self) -> None:
        with pytest.raises(ValidationError, match="muncul lebih dari sekali"):
            KeywordConfig(text="Label", is_unique=False)

    def test_by_address_requires_address(self) -> None:
        with pytest.raises(ValidationError, match="alamat sel"):
            KeywordConfig(text="Label", is_unique=False, disambiguation=DisambiguationMode.BY_ADDRESS)

    def test_near_keyword_requires_reference(self) -> None:
        with pytest.raises(ValidationError, match="pembanding"):
            KeywordConfig(text="Label", is_unique=False, disambiguation=DisambiguationMode.NEAR_KEYWORD)

    def test_address_is_normalized_and_validated(self) -> None:
        keyword = KeywordConfig(
            text="Label",
            is_unique=False,
            disambiguation=DisambiguationMode.BY_ADDRESS,
            reference_address=" i45 ",
        )
        assert keyword.reference_address == "I45"
        with pytest.raises(ValidationError, match="tidak dikenali"):
            KeywordConfig(
                text="Label",
                is_unique=False,
                disambiguation=DisambiguationMode.BY_ADDRESS,
                reference_address="bukanalamat",
            )

    def test_radius_default_is_ten(self) -> None:
        assert KeywordConfig(text="Label").radius == 10

    def test_invalid_regex_rejected(self) -> None:
        with pytest.raises(ValidationError, match="pola tidak valid"):
            KeywordConfig(text="([unclosed", match_mode=MatchMode.REGEX)


class TestProfileValidation:
    def _profile(self, **overrides: object) -> Profile:
        specs = {
            "name": "Pabrik Uji",
            "sources": [
                SourceConfig(
                    folder="prod_harian",
                    sheets=[SheetConfig(name="Produksi", fields=[field("prod_hi")])],
                )
            ],
        }
        specs.update(overrides)
        return Profile(**specs)  # type: ignore[arg-type]

    def test_valid_profile_roundtrip(self) -> None:
        profile = self._profile()
        assert Profile.model_validate(profile.model_dump()) == profile

    def test_duplicate_output_name_rejected(self) -> None:
        # Inside one sheet a repeat would silently drop a value (values are keyed by name).
        with pytest.raises(ValidationError, match="dipakai lebih dari satu kali"):
            self._profile(
                sources=[
                    SourceConfig(
                        folder="prod_harian",
                        sheets=[
                            SheetConfig(
                                name="Produksi",
                                fields=[field("prod_hi"), field("prod_hi")],
                            )
                        ],
                    ),
                ]
            )

    def test_same_output_name_in_two_sheets_is_allowed(self) -> None:
        profile = self._profile(
            sources=[
                SourceConfig(
                    folder="prod_harian",
                    sheets=[
                        SheetConfig(name="01", fields=[field("prod_hi")]),
                        SheetConfig(name="02", fields=[field("prod_hi")]),
                    ],
                ),
            ]
        )
        assert [sheet.fields[0].output_name for sheet in profile.sources[0].sheets] == [
            "prod_hi",
            "prod_hi",
        ]

    def test_duplicate_source_folder_rejected(self) -> None:
        with pytest.raises(ValidationError, match="lebih dari sekali"):
            self._profile(
                sources=[
                    SourceConfig(folder="prod_harian"),
                    SourceConfig(folder="prod_harian"),
                ]
            )

    def test_duplicate_sheet_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="lebih dari sekali"):
            self._profile(
                sources=[
                    SourceConfig(
                        folder="prod_harian",
                        sheets=[SheetConfig(name="Produksi"), SheetConfig(name="Produksi")],
                    )
                ]
            )

    def test_empty_sheet_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="tidak boleh kosong"):
            SheetConfig(name=" ")

    def test_blank_input_root_becomes_none(self) -> None:
        assert self._profile(input_root="  ").input_root is None
