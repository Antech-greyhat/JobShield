from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from jobshield.models import ConflictError, JobPosting, NotFoundError, ReportSubmission, ValidationError
from jobshield.service import JobShieldService
from jobshield.storage import Repository


JOB = "Job description: Developer. Responsibilities: Build software. Salary: KES 100,000."


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "history.sqlite3"
        self.repository = Repository(self.path)

    def save(self, score=100, status="safe", company="Acme"):
        posting = JobPosting.from_mapping({"text": JOB, "company_name": company, "title": "Developer"})
        return self.repository.save_scan(posting, {"score": score, "status": status, "flags": []})

    def report(self):
        return self.repository.create_report(ReportSubmission.from_mapping({
            "company_name": "Example", "job_url": "https://example.com/jobs/1", "reason": "Requests a fee.",
        }))

    def test_scan_survives_reopening_database(self):
        saved = self.save()
        restored = Repository(self.path).get_scan(saved["id"])
        self.assertEqual(saved, restored)
        self.assertEqual(restored["posting"]["text"], JOB)

    def test_history_filters_and_pagination(self):
        self.save(company="Acme")
        self.save(score=30, status="danger", company="Acme")
        self.save(company="Other")
        page = self.repository.list_scans(query="Acme", limit=1)
        self.assertEqual((page["total"], len(page["items"])), (2, 1))
        next_page = self.repository.list_scans(query="Acme", limit=1, offset=1)
        self.assertNotEqual(page["items"][0]["id"], next_page["items"][0]["id"])
        self.assertEqual(self.repository.list_scans(status="danger")["total"], 1)
        self.assertNotIn("posting", page["items"][0])

    def test_search_escapes_sql_like_wildcards(self):
        self.save(company="100% Jobs")
        self.save(company="Other")
        self.assertEqual(self.repository.list_scans(query="%")["total"], 1)
        self.assertEqual(self.repository.list_scans(query="' OR 1=1 --")["total"], 0)

    def test_delete_removes_only_requested_scan(self):
        first, second = self.save(), self.save()
        self.repository.delete_scan(first["id"])
        self.assertEqual(self.repository.get_scan(second["id"])["id"], second["id"])
        with self.assertRaises(NotFoundError):
            self.repository.get_scan(first["id"])
        with self.assertRaises(NotFoundError):
            self.repository.delete_scan(first["id"])

    def test_review_reopen_and_dismiss_preserve_audit_events(self):
        report = self.report()
        approved = self.repository.review_report(report["id"], "approved", "Evidence checked.", 1)
        self.assertEqual((approved["status"], approved["version"]), ("approved", 2))
        reopened = self.repository.review_report(report["id"], "pending", "New information.", 2)
        dismissed = self.repository.review_report(report["id"], "dismissed", "Resolved.", reopened["version"])
        self.assertEqual([event["status"] for event in dismissed["events"]],
                         ["pending", "approved", "pending", "dismissed"])
        self.assertEqual(Repository(self.path).get_report(report["id"]), dismissed)

    def test_stale_review_and_invalid_transition_do_not_change_report(self):
        report = self.report()
        current = self.repository.review_report(report["id"], "approved", "Confirmed.", 1)
        for status, version in [("dismissed", 1), ("dismissed", 2), ("approved", 2)]:
            with self.subTest(status=status, version=version), self.assertRaises(ConflictError):
                self.repository.review_report(report["id"], status, "Another review.", version)
            self.assertEqual(self.repository.get_report(report["id"]), current)

    def test_concurrent_review_allows_only_one_winner(self):
        report = self.report()

        def review(status):
            try:
                return self.repository.review_report(report["id"], status, "Reviewed.", 1)["status"]
            except ConflictError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(review, ["approved", "dismissed"]))
        self.assertEqual(outcomes.count("conflict"), 1)
        self.assertEqual(len(self.repository.get_report(report["id"])["events"]), 2)

    def test_statistics_exclude_unknown_from_average(self):
        self.save()
        self.save(score=20, status="danger")
        self.save(score=0, status="unknown")
        self.report()
        stats = self.repository.statistics()
        self.assertEqual((stats["scan_count"], stats["average_score"], stats["report_count"]), (3, 60, 1))
        self.assertEqual(stats["daily_scans"][0]["scans"], 3)

    def test_invalid_filters_are_rejected(self):
        for arguments in [{"limit": 0}, {"offset": -1}, {"status": "bogus"}, {"limit": True}]:
            with self.subTest(arguments=arguments), self.assertRaises(ValidationError):
                self.repository.list_scans(**arguments)

    def test_newer_schema_is_not_overwritten(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA user_version = 99")
        with self.assertRaisesRegex(ValidationError, "newer"):
            Repository(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 99)

    def test_unsaved_analysis_does_not_create_database(self):
        path = Path(self.directory.name) / "unsaved.sqlite3"
        service = JobShieldService(path)
        service.assess({"text": JOB})
        self.assertFalse(path.exists())
