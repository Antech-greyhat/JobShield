from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from jobshield.cli import main


JOB = "Job description: Engineer. Responsibilities: Build tools. Salary: KES 100,000."


class CLIWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.database = self.root / "history.sqlite3"

    def command(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--db", str(self.database), *arguments])
        return code, output.getvalue()

    def json_command(self, *arguments):
        code, output = self.command(*arguments)
        self.assertEqual(code, 0)
        return json.loads(output)

    def test_save_history_stats_and_delete_scan(self):
        scan = self.json_command("scan", "--text", JOB, "--save", "--json")
        self.assertEqual(self.json_command("history", "--id", scan["id"]), scan)
        self.assertEqual(self.json_command("history")["total"], 1)
        self.assertEqual(self.json_command("stats")["scan_count"], 1)
        self.assertEqual(self.json_command("delete-scan", scan["id"])["deleted"], scan["id"])
        self.assertEqual(self.json_command("history")["total"], 0)

    def test_report_review_and_audit_can_be_run_from_cli(self):
        report = self.json_command("report", "--company", "Example", "--url", "https://example.com/job",
                                   "--reason", "Asks for a fee.")
        reviewed = self.json_command("review", report["id"], "--status", "dismissed", "--note", "Resolved.", "--version", "1")
        self.assertEqual(reviewed["version"], 2)
        self.assertEqual(self.json_command("reports", "--id", report["id"]), reviewed)
        self.assertEqual(self.json_command("reports", "--status", "dismissed")["total"], 1)

    def test_assess_saved_html(self):
        path = self.root / "job.html"
        path.write_text(f"<title>Engineer</title><article>{JOB}</article>", encoding="utf-8")
        result = self.json_command("assess", "--file", str(path), "--json")
        self.assertEqual(result["posting"]["title"], "Engineer")
        self.assertEqual(result["analysis"]["score"], 100)
        self.assertFalse(self.database.exists())

    def test_batch_exports_json_and_signals_partial_failure(self):
        path, output = self.root / "jobs.json", self.root / "results.json"
        path.write_text(json.dumps([{"text": JOB}, {}]), encoding="utf-8")
        code, message = self.command("batch", "--file", str(path), "--output", str(output))
        self.assertEqual(code, 1)
        self.assertIn("1 results and 1 errors", message)
        self.assertEqual(json.loads(output.read_text())["summary"]["failed"], 1)

    def test_batch_refuses_to_overwrite_input_before_saving(self):
        path = self.root / "jobs.json"
        source = json.dumps([{"text": JOB}])
        path.write_text(source, encoding="utf-8")
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
            self.command("batch", "--file", str(path), "--output", str(path), "--save")
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(path.read_text(), source)
        self.assertFalse(self.database.exists())

    def test_company_search_works_without_database(self):
        companies = self.json_command("companies", "--query", "kcb")
        self.assertEqual(companies["items"][0]["domain"], "kcbgroup.com")
        self.assertFalse(self.database.exists())
