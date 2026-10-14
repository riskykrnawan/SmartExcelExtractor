#!/usr/bin/env python3
"""Headless runner for scheduled jobs.

Contoh:
    python cli.py run --profile pabrik_a.json --input "C:\\Laporan\\input"
    python cli.py validate --profile pabrik_a.json
    python cli.py list-profiles

Exit codes: 0 = sukses (warning tetap 0), 1 = ada field gagal, 2 = profil/argumen bermasalah.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from core import __version__
from core.extractor import run_extraction
from core.json_writer import write_json
from core.logging_config import setup_logging
from core.models import Profile
from core.paths import app_dir
from core.profiles import ProfileError, find_profile, list_profiles, load_profile

logger = logging.getLogger(__name__)


def _load(profile_arg: str) -> Profile:
    return load_profile(find_profile(profile_arg))


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
    try:
        profile = _load(args.profile)
    except ProfileError as exc:
        print(f"Profil tidak bisa dipakai: {exc}", file=sys.stderr)
        return 2
    if args.input:
        profile.input_root = args.input
    if not profile.input_root:
        print(
            "Folder induk belum diatur. Pakai --input atau atur lewat aplikasi.",
            file=sys.stderr,
        )
        return 2
    if not any(source.enabled for source in profile.sources):
        print("Belum ada sumber (folder) yang dicentang di profil ini.", file=sys.stderr)
        return 2

    try:
        result = run_extraction(profile)
    except Exception:
        logger.exception("Extraction failed completely for profile %s", profile.name)
        print(
            f"Ekstraksi gagal total. Detail ada di file log: {log_path}",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(args.output) if args.output else app_dir() / "output"
    path = write_json(result, output_dir)

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


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="cli.py", description="SmartExcelExtractor - ekstraksi laporan Excel berbasis keyword."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Jalankan ekstraksi, tulis hasil JSON.")
    run_p.add_argument("--profile", required=True, help="Nama atau file profil.")
    run_p.add_argument("--input", help="Folder induk (menimpa folder induk di profil).")
    run_p.add_argument("--output", help="Folder hasil JSON (default: output/ di samping aplikasi).")
    run_p.set_defaults(func=cmd_run)

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
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
