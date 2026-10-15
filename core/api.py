"""Read-only HTTP API over one extraction snapshot (docs/SPEC.md poin 5).

Endpoints (stdlib only, no new dependency):
    GET /reports?from=&to=&changed_since=&hashes=&mode=&month=&year= -> {meta, items}
    GET /reports/{key}?mode=full                                     -> {meta, item}
    GET /schema                                                      -> JSON Schema

The engine stays stateless: the client sends the `hashes` it already has, and one
process serves the snapshot(s) produced by `provider` (one run per month/year).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .audit import RunResult
from .output import MODES, Mode, build_document, item_to_dict, meta_to_dict

logger = logging.getLogger(__name__)

#: Schema served at GET /schema (doc file beside the app, see docs/SPEC.md poin 4).
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "schema" / "result-v2.json"

#: Gives the snapshot for one manual period (month, year); not a date guess.
SnapshotProvider = Callable[[int | None, int | None], RunResult]


class ApiRequestError(Exception):
    """A rejected request; `message` is returned to the client as JSON."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _one(query: dict[str, list[str]], name: str) -> str | None:
    """First non-empty value of a query parameter."""
    values = query.get(name) or []
    return values[0].strip() if values and values[0].strip() else None


def mode_of(query: dict[str, list[str]]) -> Mode:
    """Output mode of one request (`compact` unless asked otherwise)."""
    mode = _one(query, "mode") or "compact"
    if mode not in MODES:
        raise ApiRequestError(f"Mode '{mode}' tidak dikenal. Pilihan: {', '.join(MODES)}.")
    return cast(Mode, mode)


def _moment(value: str, name: str) -> datetime:
    """Parse an ISO date/time query value (naive: only the moment is compared)."""
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        raise ApiRequestError(
            f"Isian '{name}' bukan tanggal ISO. Contoh yang benar: 2026-10-14."
        ) from None


def _key_date(key: str | None) -> date | None:
    """The date of an item key, or None when the key is not a date."""
    if not key:
        return None
    try:
        return datetime.fromisoformat(key).date()
    except ValueError:
        return None


def _filtered(items: list[dict[str, Any]], query: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Apply `from`/`to` (date keys, inclusive) and `hashes` (already known)."""
    known = {h.strip() for h in (_one(query, "hashes") or "").split(",") if h.strip()}
    start_text = _one(query, "from")
    end_text = _one(query, "to")
    start = _moment(start_text, "from").date() if start_text else None
    end = _moment(end_text, "to").date() if end_text else None
    picked: list[dict[str, Any]] = []
    for entry in items:
        if entry["content_hash"] in known:
            continue
        if start or end:
            key_date = _key_date(entry.get("key"))
            # A key that is not a date can never fall inside a date range.
            if key_date is None or (start is not None and key_date < start) or (
                end is not None and key_date > end
            ):
                continue
        picked.append(entry)
    return picked


def reports_payload(result: RunResult, query: dict[str, list[str]]) -> dict[str, Any]:
    """`GET /reports` body: `{meta, items: [...]}` with the requested filters."""
    mode = mode_of(query)
    document = build_document(result, mode)
    items = [
        entry
        for sheets in document["data"].values()
        for entries in sheets.values()
        for entry in entries
    ]
    changed_text = _one(query, "changed_since")
    if changed_text:
        run_at = document["meta"].get("run_at")
        # One process = one snapshot: a client that already has this run gets nothing.
        if run_at and _moment(changed_text, "changed_since") >= _moment(str(run_at), "run_at"):
            return {"meta": document["meta"], "items": []}
    return {"meta": document["meta"], "items": _filtered(items, query)}


def report_payload(result: RunResult, key: str, query: dict[str, list[str]]) -> dict[str, Any]:
    """`GET /reports/{key}` body: `{meta, item}`."""
    mode = mode_of(query)
    for item in result.items:
        if item.key == key:
            return {"meta": meta_to_dict(result, mode), "item": item_to_dict(item, mode)}
    raise ApiRequestError(f"Data dengan identitas '{key}' tidak ada di hasil ini.", status=404)


def _period(
    query: dict[str, list[str]], default: tuple[int | None, int | None]
) -> tuple[int | None, int | None]:
    """Manual month/year for this request; the value given at start-up is the default."""
    month_text = _one(query, "month")
    year_text = _one(query, "year")
    if month_text is None and year_text is None:
        return default
    month, year = default
    if month_text is not None:
        if not month_text.isdigit() or not 1 <= int(month_text) <= 12:
            raise ApiRequestError(f"Bulan '{month_text}' tidak benar. Isi angka 1 sampai 12.")
        month = int(month_text)
    if year_text is not None:
        if not year_text.isdigit() or not 1900 <= int(year_text) <= 2999:
            raise ApiRequestError(f"Tahun '{year_text}' tidak benar. Contoh yang benar: 2026.")
        year = int(year_text)
    return month, year

class _Handler(BaseHTTPRequestHandler):
    """One report server; `provider` and `default_period` are set in `make_server`."""

    provider: SnapshotProvider
    default_period: tuple[int | None, int | None] = (None, None)
    server_version = f"SmartExcelExtractor/{__version__}"

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        """Answer one read request; every failure becomes JSON, never a stack trace."""
        try:
            self._route()
        except ApiRequestError as exc:
            self._send_json({"error": str(exc)}, exc.status)
        except Exception:
            logger.exception("API request failed: %s", self.path)
            self._send_json({"error": "Terjadi kesalahan di server. Detail ada di file log."}, 500)

    def do_POST(self) -> None:  # noqa: N802
        """Only reads are supported."""
        self._send_json({"error": "Hanya permintaan baca (GET) yang didukung."}, 405)

    do_PUT = do_PATCH = do_DELETE = do_POST

    def _route(self) -> None:
        """Write the answer for the requested address."""
        parts = urlsplit(self.path)
        path = unquote(parts.path).rstrip("/") or "/"
        query = parse_qs(parts.query)
        if path == "/schema":
            self._send_schema()
            return
        result = self.provider(*_period(query, self.default_period))
        if path == "/reports":
            self._send_json(reports_payload(result, query))
            return
        prefix = "/reports/"
        if path.startswith(prefix):
            self._send_json(report_payload(result, path[len(prefix) :], query))
            return
        raise ApiRequestError(
            f"Alamat '{path}' tidak dikenal. Yang tersedia: /reports, "
            "/reports/<identitas>, /schema.",
            status=404,
        )

    def _send_schema(self) -> None:
        """Serve the JSON Schema file described in docs/SPEC.md poin 4."""
        if not SCHEMA_PATH.is_file():
            raise ApiRequestError("Berkas skema hasil tidak ada di aplikasi ini.", status=404)
        self._send_bytes(SCHEMA_PATH.read_bytes(), "application/schema+json")

    def _send_json(self, payload: Any, status: int = 200) -> None:
        """Write a minified JSON answer."""
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        self._send_bytes(body.encode("utf-8"), "application/json; charset=utf-8", status)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib name
        """Send access logs to the log file, not to the console."""
        logger.info("%s %s", self.address_string(), format % args)

    def log_error(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.warning("%s %s", self.address_string(), format % args)


def make_server(
    provider: SnapshotProvider,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    period: tuple[int | None, int | None] = (None, None),
) -> ThreadingHTTPServer:
    """A report server for `provider`; the caller decides when to serve it."""
    handler = cast(
        type[BaseHTTPRequestHandler],
        type(
            "ReportsHandler",
            (_Handler,),
            {"provider": staticmethod(provider), "default_period": period},
        ),
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(
    provider: SnapshotProvider,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    period: tuple[int | None, int | None] = (None, None),
) -> None:
    """Serve the reports until Ctrl+C."""
    with make_server(provider, host=host, port=port, period=period) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Report server stopped by user")
