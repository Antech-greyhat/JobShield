"""Transactional SQLite history and report review with a persistent audit trail."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator
from uuid import uuid4

from .models import (
    ConflictError, JobPosting, NotFoundError, REPORT_STATUSES, ReportSubmission,
    SCAN_STATUSES, ValidationError, integer_field, text_field,
)


SCHEMA_VERSION = 1
DEFAULT_DATABASE = Path(".jobshield") / "jobshield.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Repository:
    """Open one connection per operation so the local HTTP server can use threads."""

    def __init__(self, path: str | Path = DEFAULT_DATABASE):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValidationError(f"Database schema {version} is newer than supported schema {SCHEMA_VERSION}.")
            if version == 0:
                connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS scans (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        title TEXT NOT NULL,
                        company_name TEXT NOT NULL,
                        source TEXT NOT NULL,
                        score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
                        status TEXT NOT NULL CHECK(status IN ('unknown','safe','warning','danger')),
                        posting_json TEXT NOT NULL,
                        analysis_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS scans_created ON scans(created_at DESC, id);
                    CREATE INDEX IF NOT EXISTS scans_status ON scans(status, created_at DESC);
                    CREATE TABLE IF NOT EXISTS reports (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        company_name TEXT NOT NULL,
                        job_url TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','approved','dismissed')),
                        version INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE INDEX IF NOT EXISTS reports_status ON reports(status, created_at DESC);
                    CREATE TABLE IF NOT EXISTS report_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                        created_at TEXT NOT NULL,
                        previous_status TEXT,
                        status TEXT NOT NULL,
                        note TEXT NOT NULL,
                        version INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS events_report ON report_events(report_id, sequence);
                    PRAGMA user_version = 1;
                    COMMIT;
                """)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _scan_document(row: sqlite3.Row) -> dict:
        document = dict(row)
        document["posting"] = json.loads(document.pop("posting_json"))
        document["analysis"] = json.loads(document.pop("analysis_json"))
        return document

    def save_scan(self, posting: JobPosting, analysis: dict, source: str = "") -> dict:
        score = integer_field(analysis.get("score"), "score", 0, 100)
        status = analysis.get("status")
        if status not in SCAN_STATUSES:
            raise ValidationError("Scan status is invalid.")
        source = text_field(source, "source", limit=2048)
        identifier = str(uuid4())
        created = utc_now()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO scans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, created, posting.title, posting.company_name, source, score, status,
                 json.dumps(posting.to_dict(), allow_nan=False), json.dumps(analysis, allow_nan=False)),
            )
            row = connection.execute("SELECT * FROM scans WHERE id = ?", (identifier,)).fetchone()
            return self._scan_document(row)

    def get_scan(self, identifier: str) -> dict:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM scans WHERE id = ?", (identifier,)).fetchone()
            if row is None:
                raise NotFoundError("Scan not found.")
            return self._scan_document(row)

    @staticmethod
    def _page(limit: int, offset: int) -> None:
        integer_field(limit, "limit", 1, 200)
        integer_field(offset, "offset", 0, 1_000_000)

    @staticmethod
    def _filters(status: str, query: str, statuses: tuple[str, ...]) -> tuple[str, list]:
        clauses, parameters = [], []
        if status:
            if status not in statuses:
                raise ValidationError(f"status must be one of: {', '.join(statuses)}.")
            clauses.append("status = ?")
            parameters.append(status)
        query = text_field(query, "query", limit=300)
        if query:
            # Escape LIKE metacharacters so a search for '%' remains a literal search.
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("company_name LIKE ? ESCAPE '\\'")
            parameters.append("%" + escaped + "%")
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), parameters

    def list_scans(self, *, status: str = "", query: str = "", limit: int = 50, offset: int = 0) -> dict:
        self._page(limit, offset)
        where, values = self._filters(status, query, SCAN_STATUSES)
        with self._connection() as connection:
            total = connection.execute("SELECT COUNT(*) FROM scans" + where, values).fetchone()[0]
            rows = connection.execute(
                "SELECT id, created_at, title, company_name, source, score, status FROM scans" + where
                + " ORDER BY created_at DESC, id LIMIT ? OFFSET ?", [*values, limit, offset],
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def delete_scan(self, identifier: str) -> None:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM scans WHERE id = ?", (identifier,))
            if cursor.rowcount == 0:
                raise NotFoundError("Scan not found.")

    def create_report(self, submission: ReportSubmission) -> dict:
        identifier, created = str(uuid4()), utc_now()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO reports (id, created_at, updated_at, company_name, job_url, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (identifier, created, created, submission.company_name, submission.job_url, submission.reason),
            )
            connection.execute(
                "INSERT INTO report_events (report_id, created_at, previous_status, status, note, version) "
                "VALUES (?, ?, NULL, 'pending', 'Report submitted locally.', 1)",
                (identifier, created),
            )
            return self._get_report(connection, identifier)

    @staticmethod
    def _get_report(connection: sqlite3.Connection, identifier: str) -> dict:
        row = connection.execute("SELECT * FROM reports WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise NotFoundError("Report not found.")
        report = dict(row)
        report["events"] = [dict(event) for event in connection.execute(
            "SELECT created_at, previous_status, status, note, version FROM report_events "
            "WHERE report_id = ? ORDER BY sequence", (identifier,),
        )]
        return report

    def get_report(self, identifier: str) -> dict:
        with self._connection() as connection:
            return self._get_report(connection, identifier)

    def list_reports(self, *, status: str = "", query: str = "", limit: int = 50, offset: int = 0) -> dict:
        self._page(limit, offset)
        where, values = self._filters(status, query, REPORT_STATUSES)
        with self._connection() as connection:
            total = connection.execute("SELECT COUNT(*) FROM reports" + where, values).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM reports" + where + " ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def review_report(self, identifier: str, status: str, note: str, expected_version: int) -> dict:
        if status not in REPORT_STATUSES:
            raise ValidationError(f"status must be one of: {', '.join(REPORT_STATUSES)}.")
        note = text_field(note, "note", required=True, limit=10_000)
        integer_field(expected_version, "version", 1, 2_147_483_647)
        with self._connection() as connection:
            # Acquire the write lock before reading to prevent a stale reviewer
            # from silently overwriting another review made at the same time.
            connection.execute("BEGIN IMMEDIATE")
            current = self._get_report(connection, identifier)
            if current["version"] != expected_version:
                raise ConflictError("Report changed since it was read. Reload it and use its current version.")
            previous = current["status"]
            if previous == status:
                raise ConflictError("Report already has that status.")
            if previous != "pending" and status != "pending":
                raise ConflictError("Reopen a reviewed report as pending before reviewing it again.")
            updated, version = utc_now(), expected_version + 1
            connection.execute(
                "UPDATE reports SET status = ?, updated_at = ?, version = ? WHERE id = ?",
                (status, updated, version, identifier),
            )
            connection.execute(
                "INSERT INTO report_events (report_id, created_at, previous_status, status, note, version) "
                "VALUES (?, ?, ?, ?, ?, ?)", (identifier, updated, previous, status, note, version),
            )
            return self._get_report(connection, identifier)

    def statistics(self, days: int = 30) -> dict:
        integer_field(days, "days", 1, 365)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="milliseconds")
        with self._connection() as connection:
            scans = {status: 0 for status in SCAN_STATUSES}
            scans.update({row["status"]: row["count"] for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM scans GROUP BY status"
            )})
            reports = {status: 0 for status in REPORT_STATUSES}
            reports.update({row["status"]: row["count"] for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM reports GROUP BY status"
            )})
            average = connection.execute("SELECT AVG(score) FROM scans WHERE status != 'unknown'").fetchone()[0]
            daily = [dict(row) for row in connection.execute(
                "SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS scans, "
                "SUM(CASE WHEN status = 'danger' THEN 1 ELSE 0 END) AS danger "
                "FROM scans WHERE created_at >= ? GROUP BY date ORDER BY date", (since,),
            )]
        return {
            "scan_count": sum(scans.values()), "scan_statuses": scans,
            "report_count": sum(reports.values()), "report_statuses": reports,
            "average_score": round(average, 2) if average is not None else None,
            "daily_scans": daily, "days": days,
        }
