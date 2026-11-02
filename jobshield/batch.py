"""Import job collections and export portable JSON or spreadsheet-safe CSV."""

from __future__ import annotations

import csv
from dataclasses import fields
import io
import json
import os
from pathlib import Path
import tempfile

from .documents import read_local_text
from .models import JobPosting, ValidationError
from .service import JobShieldService


MAX_BATCH_BYTES = 10_000_000
MAX_BATCH_ROWS = 500
CSV_FIELDS = {field.name for field in fields(JobPosting)}


def read_batch(path: str | Path, format: str = "auto") -> list:
    path = Path(path)
    if format == "auto":
        format = {".csv": "csv", ".jsonl": "jsonl", ".ndjson": "jsonl", ".json": "json"}.get(path.suffix.lower(), "")
        if not format:
            raise ValidationError("Cannot infer batch format. Use --format json, jsonl, or csv.")
    source = read_local_text(path, MAX_BATCH_BYTES)
    if format == "json":
        try:
            rows = json.loads(source)
        except json.JSONDecodeError as error:
            raise ValidationError(f"Invalid JSON at line {error.lineno}: {error.msg}.") from error
        if not isinstance(rows, list):
            raise ValidationError("Batch JSON must contain an array of posting objects.")
    elif format == "jsonl":
        rows = []
        for line_number, line in enumerate(source.splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValidationError(f"Invalid JSON on line {line_number}: {error.msg}.") from error
            if len(rows) > MAX_BATCH_ROWS:
                raise ValidationError(f"A batch can contain at most {MAX_BATCH_ROWS} postings.")
    elif format == "csv":
        rows = _read_csv(source)
    else:
        raise ValidationError("Batch format must be auto, json, jsonl, or csv.")
    if not 1 <= len(rows) <= MAX_BATCH_ROWS:
        raise ValidationError(f"A batch must contain between 1 and {MAX_BATCH_ROWS} postings.")
    return rows


def _read_csv(source: str) -> list[dict]:
    # csv's default field limit is smaller than an accepted posting. Restore the
    # process setting afterward because other tools may share this interpreter.
    previous_limit = csv.field_size_limit()
    csv.field_size_limit(MAX_BATCH_BYTES)
    try:
        reader = csv.DictReader(io.StringIO(source, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers or "text" not in headers:
            raise ValidationError("CSV needs a header row containing the text column.")
        if len(set(headers)) != len(headers):
            raise ValidationError("CSV header names must be unique.")
        unknown = set(headers) - CSV_FIELDS
        if unknown:
            raise ValidationError(f"Unsupported CSV columns: {', '.join(sorted(unknown))}.")
        rows = []
        for line_number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValidationError(f"CSV row {line_number} does not match the header width.")
            if "application_fee" in row:
                value = row["application_fee"].strip().lower()
                if value not in {"", "false", "true", "no", "yes", "0", "1"}:
                    raise ValidationError(f"CSV row {line_number}: application_fee must be true/false or yes/no.")
                row["application_fee"] = value in {"true", "yes", "1"}
            rows.append(row)
            if len(rows) > MAX_BATCH_ROWS:
                raise ValidationError(f"A batch can contain at most {MAX_BATCH_ROWS} postings.")
        return rows
    except csv.Error as error:
        raise ValidationError(f"Invalid CSV: {error}.") from error
    finally:
        csv.field_size_limit(previous_limit)


def scan_batch_file(service: JobShieldService, path: str | Path, *, format: str = "auto", save: bool = False) -> dict:
    return service.analyze_batch(read_batch(path, format), save=save)


def spreadsheet_cell(value: object) -> str:
    """Prevent user-supplied job titles and URLs from becoming spreadsheet formulas."""
    text = str(value) if value is not None else ""
    probe = text.lstrip()
    if text.startswith(("\t", "\r", "\n")) or probe.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def batch_csv(result: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=[
        "row", "id", "title", "company_name", "url", "score", "status", "flags", "error",
    ], lineterminator="\n")
    writer.writeheader()
    records = []
    for item in result["items"]:
        posting, analysis = item["posting"], item["analysis"]
        records.append({
            "row": item["row"], "id": item.get("id", ""),
            "title": posting["title"], "company_name": posting["company_name"],
            "url": posting["url"], "score": analysis["score"], "status": analysis["status"],
            "flags": " | ".join(flag["message"] for flag in analysis["flags"]), "error": "",
        })
    records.extend({"row": error["row"], "error": error["error"]} for error in result["errors"])
    for record in sorted(records, key=lambda row: row["row"]):
        writer.writerow({key: spreadsheet_cell(value) for key, value in record.items()})
    return output.getvalue()


def serialize_batch(result: dict, format: str = "json") -> str:
    if format == "json":
        return json.dumps(result, indent=2, allow_nan=False) + "\n"
    if format == "csv":
        return batch_csv(result)
    raise ValidationError("Output format must be json or csv.")


def write_output(path: str | Path, text: str, *, input_path: str | Path | None = None) -> None:
    destination = Path(path).resolve()
    if input_path is not None and destination == Path(input_path).resolve():
        raise ValidationError("Output must not overwrite the input posting file.")
    # Write beside the destination so replacement stays atomic on the same disk.
    descriptor, temporary = tempfile.mkstemp(prefix=".jobshield-", suffix=".tmp", dir=destination.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
