"""Command-line access to scanning, local history, batch analysis, and moderation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from typing import Sequence

from . import __version__
from .batch import scan_batch_file, serialize_batch, write_output
from .companies import CompanyDirectory
from .documents import read_local_text, read_posting
from .models import MAX_TEXT_LENGTH, NotFoundError, REPORT_STATUSES, SCAN_STATUSES, ValidationError
from .scanner import DEFAULT_RULES_PATH, analyze_job_text, load_keywords
from .server import LocalAPIServer
from .service import JobShieldService
from .storage import DEFAULT_DATABASE, Repository


def _page_arguments(parser: argparse.ArgumentParser, statuses: tuple[str, ...]) -> None:
    parser.add_argument("--status", choices=statuses, default="")
    parser.add_argument("--query", default="", help="Filter by company name.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JobShield: local recruitment analysis and reporting.")
    parser.add_argument("--version", action="version", version="JobShield " + __version__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE, help="SQLite history and reports file.")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="Scan plain text using the browser's scoring rules.")
    source = scan.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Job posting text to analyze.")
    source.add_argument("--file", type=Path, help="UTF-8 text file.")
    source.add_argument("--stdin", action="store_true", help="Read text from standard input.")
    scan.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--save", action="store_true", help="Store this scan in local history.")

    assess = commands.add_parser("assess", help="Check a structured JSON posting or saved HTML page.")
    assess.add_argument("--file", type=Path, required=True)
    assess.add_argument("--format", choices=("auto", "json", "html", "text"), default="auto")
    assess.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    assess.add_argument("--save", action="store_true")
    assess.add_argument("--json", action="store_true")

    batch = commands.add_parser("batch", help="Analyze a JSON, JSONL, or CSV collection of jobs.")
    batch.add_argument("--file", type=Path, required=True)
    batch.add_argument("--format", choices=("auto", "json", "jsonl", "csv"), default="auto")
    batch.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    batch.add_argument("--save", action="store_true")
    batch.add_argument("--output", type=Path, help="Write results atomically to this path.")
    batch.add_argument("--output-format", choices=("json", "csv"), default="json")

    history = commands.add_parser("history", help="List saved scans or read one full result.")
    _page_arguments(history, SCAN_STATUSES)
    history.add_argument("--id", help="Return one saved scan including its original posting.")

    delete = commands.add_parser("delete-scan", help="Remove one saved scan from local history.")
    delete.add_argument("id")

    report = commands.add_parser("report", help="Submit a report to the local review queue.")
    report.add_argument("--company", required=True)
    report.add_argument("--url", required=True)
    report.add_argument("--reason", required=True)

    reports = commands.add_parser("reports", help="List local reports or read one with its audit trail.")
    _page_arguments(reports, REPORT_STATUSES)
    reports.add_argument("--id")

    review = commands.add_parser("review", help="Review or reopen a local report.")
    review.add_argument("id")
    review.add_argument("--status", choices=REPORT_STATUSES, required=True)
    review.add_argument("--note", required=True)
    review.add_argument("--version", type=int, required=True, help="Current report version, for conflict detection.")

    companies = commands.add_parser("companies", help="Search the bundled company directory.")
    companies.add_argument("--query", default="")

    stats = commands.add_parser("stats", help="Summarize saved scans and local report statuses.")
    stats.add_argument("--days", type=int, default=30)

    serve = commands.add_parser("serve", help="Start the local token-authenticated HTTP API.")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    serve.add_argument("--allow-origin", action="append", default=[], help="Explicit localhost or Chrome extension origin.")
    serve.add_argument("--token-env", default="JOBSHIELD_API_TOKEN", help="Environment variable containing the API token.")
    return parser


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, allow_nan=False))


def _print_analysis(value: dict) -> None:
    analysis = value.get("analysis", value)
    if "id" in value:
        print(f"Saved scan: {value['id']}")
    print(f"Status: {analysis['status']}")
    print(f"Trust score: {analysis['score']}/100")
    for flag in analysis["flags"]:
        print(f"- {flag['message']}: {flag['description']}")
    for signal in analysis.get("positive_signals", []):
        print(f"+ {signal}")
    print("Heuristic analysis only; verify the employer independently.")


def _run_scan(args: argparse.Namespace) -> int:
    if args.file is not None:
        text = read_local_text(args.file)
    elif args.stdin:
        text = sys.stdin.read(MAX_TEXT_LENGTH + 1)
    else:
        text = args.text
    if not text.strip():
        raise ValidationError("Job text cannot be empty or whitespace only.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValidationError(f"Job text must be at most {MAX_TEXT_LENGTH:,} characters.")
    if args.save:
        service = JobShieldService(args.db, rules_path=args.rules)
        result = service.scan_text(text, save=True, source=str(args.file or "command-line"))
    else:
        result = analyze_job_text(text, load_keywords(args.rules))
    (_print_json if args.json else _print_analysis)(result)
    return 0


def _run_server(args: argparse.Namespace) -> int:
    configured_token = os.environ.get(args.token_env)
    token = configured_token if configured_token is not None else secrets.token_urlsafe(32)
    service = JobShieldService(args.db, rules_path=args.rules)
    with LocalAPIServer(service, token, port=args.port, origins=tuple(args.allow_origin)) as server:
        port = server.server_address[1]
        print(f"JobShield API: http://127.0.0.1:{port}", flush=True)
        if configured_token is None:
            print(f"Session bearer token: {token}", flush=True)
        else:
            print(f"Using API token from {args.token_env}.", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    command = args.command
    if command == "scan":
        return _run_scan(args)
    if command == "assess":
        posting = read_posting(args.file, args.format)
        service = JobShieldService(args.db, rules_path=args.rules)
        result = service.assess(posting, save=args.save, source=str(args.file))
        (_print_json if args.json else _print_analysis)(result)
        return 0
    if command == "batch":
        if args.output is not None and args.output.resolve() == args.file.resolve():
            raise ValidationError("Output must not overwrite the input posting file.")
        service = JobShieldService(args.db, rules_path=args.rules)
        result = scan_batch_file(service, args.file, format=args.format, save=args.save)
        serialized = serialize_batch(result, args.output_format)
        if args.output:
            write_output(args.output, serialized, input_path=args.file)
            print(f"Wrote {result['summary']['succeeded']} results and {result['summary']['failed']} errors to {args.output}.")
        else:
            print(serialized, end="")
        return 1 if result["errors"] else 0
    if command == "serve":
        return _run_server(args)
    if command == "companies":
        _print_json({"items": CompanyDirectory.load().search(args.query)})
        return 0

    repository = Repository(args.db)
    if command in {"history", "reports"}:
        if args.id:
            result = repository.get_scan(args.id) if command == "history" else repository.get_report(args.id)
        else:
            listing = repository.list_scans if command == "history" else repository.list_reports
            result = listing(status=args.status, query=args.query, limit=args.limit, offset=args.offset)
        _print_json(result)
    elif command == "delete-scan":
        repository.delete_scan(args.id)
        _print_json({"deleted": args.id})
    elif command == "report":
        service = JobShieldService(args.db)
        _print_json(service.submit_report({"company_name": args.company, "job_url": args.url, "reason": args.reason}))
    elif command == "review":
        _print_json(repository.review_report(args.id, args.status, args.note, args.version))
    elif command == "stats":
        _print_json(repository.statistics(args.days))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Preserve the original python jobshield.py --text/--file/--stdin interface.
    if arguments and arguments[0] in {"--text", "--file", "--stdin", "--rules", "--json"}:
        arguments.insert(0, "scan")
    parser = build_parser()
    args = parser.parse_args(arguments)
    try:
        return _dispatch(args)
    except (OSError, UnicodeError, ValueError, RecursionError, NotFoundError, sqlite3.Error) as error:
        parser.exit(2, f"jobshield: error: {error}\n")
    except KeyboardInterrupt:
        return 130
