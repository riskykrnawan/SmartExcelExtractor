"""HTTP API: routing, filters, and error answers (docs/SPEC.md poin 5)."""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from typing import Any

import pytest

from core.api import _filtered, make_server
from tests.test_json_writer import make_result


def call(connection: HTTPConnection, method: str, path: str) -> tuple[int, str, str]:
    """(status, content type, body) for one request."""
    connection.request(method, path)
    response = connection.getresponse()
    return response.status, response.getheader("Content-Type", ""), response.read().decode("utf-8")


def body(connection: HTTPConnection, path: str) -> dict[str, Any]:
    status, _, text = call(connection, "GET", path)
    assert status == 200, text
    return json.loads(text)


@pytest.fixture
def asked() -> list[tuple[int | None, int | None]]:
    """Records the manual period the handler asked the provider for."""
    return []


@pytest.fixture
def api(asked: list[tuple[int | None, int | None]]) -> Iterator[HTTPConnection]:
    """A report server on a free port with one snapshot of one item."""
    result = make_result()

    def provider(month: int | None, year: int | None) -> Any:
        asked.append((month, year))
        return result

    server = make_server(provider, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    connection = HTTPConnection(host, port, timeout=5)
    try:
        yield connection
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_reports_returns_meta_and_items(api: HTTPConnection) -> None:
    payload = body(api, "/reports")
    assert set(payload) == {"meta", "items"}
    assert payload["meta"]["mode"] == "compact"
    item = payload["items"][0]
    assert item["key"] == "2026-10-14" and item["values"]["prod_hi"] == 1523.5
    assert item["content_hash"] and "detail" not in item


def test_item_can_be_asked_by_key_in_full_mode(api: HTTPConnection) -> None:
    payload = body(api, "/reports/2026-10-14?mode=full")
    assert set(payload) == {"meta", "item"}
    assert payload["item"]["detail"]["prod_hi"]["value_address"] == "L45"


def test_unknown_key_is_404(api: HTTPConnection) -> None:
    status, _, text = call(api, "GET", "/reports/2026-10-15")
    assert status == 404 and "2026-10-15" in json.loads(text)["error"]


def test_unknown_path_is_404(api: HTTPConnection) -> None:
    status, _, text = call(api, "GET", "/laporan")
    assert status == 404 and "/reports" in json.loads(text)["error"]


def test_write_method_is_405(api: HTTPConnection) -> None:
    status, _, text = call(api, "POST", "/reports")
    assert status == 405 and "GET" in json.loads(text)["error"]


def test_hashes_drop_the_items_the_client_already_has(api: HTTPConnection) -> None:
    known = body(api, "/reports")["items"][0]["content_hash"]
    assert body(api, f"/reports?hashes={known}")["items"] == []
    assert len(body(api, "/reports?hashes=lain")["items"]) == 1


def test_from_to_filter_the_date_keys(api: HTTPConnection) -> None:
    assert body(api, "/reports?from=2026-10-15")["items"] == []
    assert body(api, "/reports?to=2026-10-14")["items"] != []
    assert body(api, "/reports?from=2026-10-01&to=2026-10-31")["items"] != []


def test_date_filter_skips_entries_without_a_key() -> None:
    entry = {"content_hash": "abc", "status": "ok"}  # no identity: the field is absent
    assert _filtered([entry], {}) == [entry]
    assert _filtered([entry], {"from": ["2026-10-01"]}) == []


def test_changed_since_a_newer_moment_returns_nothing(api: HTTPConnection) -> None:
    assert body(api, "/reports?changed_since=2026-10-14T09:00:00")["items"] == []
    assert body(api, "/reports?changed_since=2026-10-14T08:00:00")["items"] != []


def test_bad_mode_is_400(api: HTTPConnection) -> None:
    status, _, text = call(api, "GET", "/reports?mode=besar")
    assert status == 400 and "compact" in json.loads(text)["error"]


def test_bad_month_is_400(api: HTTPConnection, asked: list[tuple[int | None, int | None]]) -> None:
    status, _, text = call(api, "GET", "/reports?month=13")
    assert status == 400 and "1 sampai 12" in json.loads(text)["error"]
    assert asked == []


def test_manual_period_reaches_the_provider(
    api: HTTPConnection, asked: list[tuple[int | None, int | None]]
) -> None:
    body(api, "/reports?month=10&year=2026")
    assert asked[-1] == (10, 2026)


def test_schema_is_served_for_clients(api: HTTPConnection) -> None:
    status, content_type, text = call(api, "GET", "/schema")
    assert status == 200 and "schema+json" in content_type
    assert "item" in json.loads(text)["$defs"]
