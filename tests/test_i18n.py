"""Localization: every key has both languages, switching works, placeholders fill."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from ui import i18n


@pytest.fixture(autouse=True)
def _reset_language() -> Iterator[None]:
    """Each test starts in the default language and restores it afterwards."""
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


def test_default_language_is_english() -> None:
    assert i18n.current_language() == "en"
    assert i18n.t("s3.btn_run") == "Run Extraction"


def test_switch_to_indonesian() -> None:
    i18n.set_language("id")
    assert i18n.current_language() == "id"
    assert i18n.t("s3.btn_run") == "Jalankan Ekstraksi"


def test_unknown_language_keeps_the_current_one() -> None:
    i18n.set_language("id")
    i18n.set_language("de")  # not offered
    assert i18n.current_language() == "id"


def test_placeholders_are_filled() -> None:
    text = i18n.t("s3.summary_result", total=15, ok=10, warning=3, error=2)
    assert text == "15 data: 10 OK, 3 need review, 2 failed."


def test_placeholders_are_filled_in_indonesian() -> None:
    i18n.set_language("id")
    text = i18n.t("s3.summary_result", total=15, ok=10, warning=3, error=2)
    assert text == "15 data: 10 berhasil, 3 perlu dicek, 2 gagal."


def test_status_labels_use_real_emoji_not_html_entities() -> None:
    """Regression: '&#128994;' leaked as literal text because QLabel is not HTML."""
    for key in ("pv.status_ok", "pv.status_warning", "pv.status_error"):
        for code in ("id", "en"):
            i18n.set_language(code)
            assert "&#" not in i18n.t(key), key


def test_unknown_key_returns_the_key() -> None:
    assert i18n.t("does.not.exist") == "does.not.exist"


def test_every_key_has_both_languages_and_is_non_empty() -> None:
    for key, entry in i18n._STRINGS.items():
        assert set(entry) == {"id", "en"}, key
        assert entry["id"].strip(), key
        assert entry["en"].strip(), key


def test_placeholders_match_across_languages() -> None:
    """The same {placeholders} exist in id and en so format() never breaks."""
    import re

    for key, entry in i18n._STRINGS.items():
        id_ph = set(re.findall(r"{(\w+)}", entry["id"]))
        en_ph = set(re.findall(r"{(\w+)}", entry["en"]))
        assert id_ph == en_ph, key
