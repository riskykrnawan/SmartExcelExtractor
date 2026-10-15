#!/usr/bin/env python3
"""Headless runner for scheduled jobs and the read-only report API.

Contoh:
    python cli.py run --profile pabrik_a.json --input "C:\\Laporan\\input"
    python cli.py run --profile pabrik_a.json --mode full --month 10 --year 2026
    python cli.py mapping suggest --file sampel.xlsx --sheet Produksi --out draf.csv
    python cli.py mapping export --profile pabrik_a.json --out mapping.csv
    python cli.py mapping import --profile pabrik_a.json --csv mapping.csv [--replace]
    python cli.py serve --profile pabrik_a.json --port 8765
    python cli.py validate --profile pabrik_a.json
    python cli.py list-profiles

Exit codes: 0 = sukses (warning tetap 0), 1 = ada field gagal, 2 = profil/argumen bermasalah.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from core import __version__
from core.api import serve
from core.audit import RunResult
from core.cell_index import ExcelFileError
from core.extractor import run_extraction
from core.json_writer import write_json
from core.logging_config import setup_logging
from core.mapping import MappingError, export_csv, import_csv, suggest_csv
from core.models import Profile
from core.output import MODES
from core.paths import app_dir
from core.profiles import (
    ProfileError,
    find_profile,
    format_validation_error,
    list_profiles,
    load_profile,
    replace_sources,
    save_profile,
)

logger = logging.getLogger(__name__)


def _load_path(profile_arg: str) -> Path:
    """The profile file for a name or path given on the command line."""
    return find_profile(profile_arg)


def _load(profile_arg: str) -> Profile:
    return load_profile(_load_path(profile_arg))


def _prepare(args: argparse.Namespace) -> Profile | None:
    """Load the profile and check the run prerequisites.

    Prints the reason and returns None when the run cannot start.
    """
    try:
        profile = _load(args.profile)
    except ProfileError as exc:
        print(f"Profil tidak bisa dipakai: {exc}", file=sys.stderr)
        return None
    if args.input:
        profile.input_root = args.input
    if not profile.input_root:
        print(
            "Folder induk belum diatur. Pakai --input atau atur lewat aplikasi.",
            file=sys.stderr,
        )
        return None
    if not any(source.enabled for source in profile.sources):
        print("Belum ada sumber (folder) yang dicentang di profil ini.", file=sys.stderr)
        return None
    return profile



def _count_fields(profile: Profile) -> tuple[int, int]:
    fields = sum(len(sheet.fields) for source in profile.sources for sheet in source.sheets)
    enabled = sum(
        len(sheet.fields)
        for source in profile.sources
        if source.enabled
        for sheet in source.sheets
    )
    return fields, enabled


def cmd_run(args: argparse.Namespace) -> int:
    log_path = setup_logging()
    profile = _prepare(args)
    if profile is None:
        return 2

    try:
        result = run_extraction(profile, period_year=args.year, period_month=args.month)
    except Exception:
        logger.exception("Extraction failed completely for profile %s", profile.name)
        print(
            f"Ekstraksi gagal total. Detail ada di file log: {log_path}",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(args.output) if args.output else app_dir() / "output"
    path = write_json(result, output_dir, mode=args.mode)

    summary = result.summary
    print(f"Profil : {profile.name}")
    print(f"Waktu  : {result.meta['run_at']}")
    print(
        f"Hasil  : {summary['total_fields']} data - "
        f"{summary['ok']} OK, {summary['warning']} perlu dicek, {summary['error']} gagal"
    )
    for issue in result.audit["issues"]:
        mark = "GAGAL" if issue["level"] == "error" else "CEK  "
        where = issue["field"] or "(sumber)"
        print(f"  [{mark}] {where}: {issue['message']}")
    print(f"File   : {path}")
    return 1 if summary["error"] else 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        profile = _load(args.profile)
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    fields, enabled = _count_fields(profile)
    print(f"Profil '{profile.name}' valid: {enabled} dari {fields} data akan dijalankan.")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    paths = list_profiles()
    if not paths:
        print("Belum ada profil.")
        return 0
    for path in paths:
        try:
            name = load_profile(path).name
        except ProfileError:
            name = f"{path.stem} (tidak valid)"
        print(f"- {name}  [{path.name}]")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    log_path = setup_logging()
    profile = _prepare(args)
    if profile is None:
        return 2

    try:
        result = run_extraction(profile, period_year=args.year, period_month=args.month)
    except Exception:
        logger.exception("Extraction failed completely for profile %s", profile.name)
        print(
            f"Ekstraksi gagal total. Detail ada di file log: {log_path}",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(args.output) if args.output else app_dir() / "output"
    path = write_json(result, output_dir, mode=args.mode)
    cache: dict[tuple[int | None, int | None], RunResult] = {(args.month, args.year): result}

    def snapshot(month: int | None, year: int | None) -> RunResult:
        """One run per manual period (`?month=&year=`); later calls reuse it."""
        key = (month, year)
        if key not in cache:
            cache[key] = run_extraction(profile, period_year=year, period_month=month)
        return cache[key]

    print(f"Profil : {profile.name}")
    print(f"Hasil  : {path}")
    print(f"Alamat : http://{args.host}:{args.port}/reports")
    print("Tekan Ctrl+C untuk berhenti.")
    serve(snapshot, host=args.host, port=args.port, period=(args.month, args.year))
    return 0


def cmd_mapping_suggest(args: argparse.Namespace) -> int:
    try:
        rows = suggest_csv(
            Path(args.file), args.sheet, args.folder, Path(args.out) if args.out else None
        )
    except (MappingError, ExcelFileError) as exc:
        print(f"Draf mapping tidak bisa dibuat: {exc}", file=sys.stderr)
        return 2
    if args.out:
        print(f"{len(rows)} data ditulis ke {args.out}")
        print("Buka file itu, rapikan namanya, lalu muat dengan 'mapping import'.")
    return 0


def cmd_mapping_export(args: argparse.Namespace) -> int:
    try:
        profile = _load(args.profile)
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rows = export_csv(profile, Path(args.out) if args.out else None)
    if args.out:
        print(f"{len(rows)} data dari profil '{profile.name}' ditulis ke {args.out}")
    return 0


def cmd_mapping_import(args: argparse.Namespace) -> int:
    try:
        path = _load_path(args.profile)
        profile = load_profile(path)
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if profile.sources and not args.replace:
        print(
            "Profil ini sudah punya sumber data. Pakai --replace kalau isinya memang ingin diganti.",
            file=sys.stderr,
        )
        return 2
    try:
        profile = replace_sources(profile, import_csv(Path(args.csv)))
    except MappingError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValidationError as exc:
        print("Mapping tidak bisa dipakai: " + "; ".join(format_validation_error(exc)), file=sys.stderr)
        return 2
    save_profile(profile, path)
    fields = sum(
        len(sheet.fields) for source in profile.sources for sheet in source.sheets
    )
    print(f"{fields} data dari {len(profile.sources)} folder disimpan ke profil '{profile.name}'.")
    return 0



def _month_arg(text: str) -> int:
    """Command-line month: 1 to 12 only."""
    if not text.isdigit() or not 1 <= int(text) <= 12:
        raise argparse.ArgumentTypeError("Bulan harus angka 1 sampai 12.")
    return int(text)


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    """Options shared by `run` and `serve`."""
    parser.add_argument("--input", help="Folder induk (menimpa folder induk di profil).")
    parser.add_argument("--output", help="Folder hasil JSON (default: output/ di samping aplikasi).")
    parser.add_argument(
        "--mode", choices=MODES, default="compact", help="Bentuk hasil JSON (default: compact)."
    )
    parser.add_argument(
        "--month", type=_month_arg, help="Bulan untuk identitas dari nama sheet (1-12)."
    )
    parser.add_argument("--year", type=int, help="Tahun untuk identitas dari nama sheet.")


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="cli.py", description="SmartExcelExtractor - ekstraksi laporan Excel berbasis keyword."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Jalankan ekstraksi, tulis hasil JSON.")
    run_p.add_argument("--profile", required=True, help="Nama atau file profil.")
    _add_run_options(run_p)
    run_p.set_defaults(func=cmd_run)

    serve_p = sub.add_parser("serve", help="Sajikan hasil sebagai laporan siap-baca di jaringan lokal.")
    serve_p.add_argument("--profile", required=True, help="Nama atau file profil.")
    _add_run_options(serve_p)
    serve_p.add_argument("--host", default="127.0.0.1", help="Alamat yang dipakai (default: 127.0.0.1).")
    serve_p.add_argument("--port", type=int, default=8765, help="Nomor pintu (default: 8765).")
    serve_p.set_defaults(func=cmd_serve)

    mapping_p = sub.add_parser("mapping", help="Buat, simpan, dan muat mapping massal (CSV).")
    mapping_sub = mapping_p.add_subparsers(dest="mapping_command", required=True)

    suggest_p = mapping_sub.add_parser("suggest", help="Buat draf mapping dari satu sheet contoh.")
    suggest_p.add_argument("--file", required=True, help="File Excel contoh.")
    suggest_p.add_argument("--sheet", required=True, help="Nama sheet contoh.")
    suggest_p.add_argument("--folder", default="", help="Folder yang akan dipakai di profil.")
    suggest_p.add_argument("--out", help="File CSV hasil (default: tampil di layar).")
    suggest_p.set_defaults(func=cmd_mapping_suggest)

    export_p = mapping_sub.add_parser("export", help="Simpan mapping profil ke CSV.")
    export_p.add_argument("--profile", required=True, help="Nama atau file profil.")
    export_p.add_argument("--out", help="File CSV hasil (default: tampil di layar).")
    export_p.set_defaults(func=cmd_mapping_export)

    import_p = mapping_sub.add_parser("import", help="Muat mapping CSV ke profil.")
    import_p.add_argument("--profile", required=True, help="Nama atau file profil.")
    import_p.add_argument("--csv", required=True, help="File CSV mapping.")
    import_p.add_argument(
        "--replace", action="store_true", help="Ganti seluruh sumber data yang sudah ada."
    )
    import_p.set_defaults(func=cmd_mapping_import)

    validate_p = sub.add_parser("validate", help="Periksa profil tanpa ekstraksi.")
    validate_p.add_argument("--profile", required=True, help="Nama atau file profil.")
    validate_p.set_defaults(func=cmd_validate)

    list_p = sub.add_parser("list-profiles", help="Daftar profil yang tersedia.")
    list_p.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return int(args.func(args))
    except (ProfileError, MappingError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
