import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from jobshield.batch import batch_csv, read_batch, scan_batch_file, write_output
from jobshield.documents import html_text, posting_from_html, read_local_text, read_posting
from jobshield.models import ValidationError
from jobshield.service import JobShieldService


JOB = "Job description: Engineer. Responsibilities: Build tools. Salary: KES 100,000."


class DocumentTests(unittest.TestCase):
    def test_scripts_styles_and_hidden_content_are_not_scanned(self):
        html = """<title>Developer</title><style>.foo { color: red; }</style>
        <script>registration fee</script><div hidden>pay for training</div>
        <div aria-hidden="true">mpesa</div><p>Job <b>description</b>: Engineer.</p>
        <p>Responsibilities: Build tools. Salary: KES 100,000.</p>"""
        posting = posting_from_html(html)
        self.assertNotIn("fee", posting.text)
        self.assertNotIn("mpesa", posting.text)
        self.assertIn("Job description", posting.text)
        self.assertEqual(posting.title, "Developer")

    def test_inline_markup_and_html_entities_preserve_words(self):
        self.assertEqual(html_text("<p>Job <b>description</b> &amp; requirements</p>"), "Job description & requirements")

    def test_jobposting_jsonld_extracts_company_and_description(self):
        schema = {"@graph": [{"@type": "JobPosting", "title": "Engineer", "description": f"<p>{JOB}</p>",
                              "hiringOrganization": {"name": "Safaricom", "sameAs": "https://safaricom.co.ke"}}]}
        posting = posting_from_html(f'<script type="application/ld+json">{json.dumps(schema)}</script>')
        self.assertEqual(posting.text, JOB)
        self.assertEqual(posting.company_name, "Safaricom")
        self.assertEqual(posting.company_website, "https://safaricom.co.ke")

    def test_invalid_metadata_falls_back_to_visible_content(self):
        posting = posting_from_html(f'<script type="application/ld+json">broken</script><p>{JOB}</p>')
        self.assertEqual(posting.text, JOB)

    def test_multiple_job_records_require_separate_inputs(self):
        schema = [{"@type": "JobPosting", "description": JOB}] * 2
        with self.assertRaisesRegex(ValidationError, "multiple"):
            posting_from_html(f'<script type="application/ld+json">{json.dumps(schema)}</script>')

    def test_file_reader_supports_bom_and_enforces_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "posting.txt"
            path.write_text(JOB, encoding="utf-8-sig")
            self.assertEqual(read_posting(path).text, JOB)
            with self.assertRaisesRegex(ValidationError, "exceeds"):
                read_local_text(path, max_bytes=5)
            path.write_bytes(b"\xff\xff")
            with self.assertRaisesRegex(ValidationError, "UTF-8"):
                read_posting(path)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.service = JobShieldService(self.root / "history.sqlite3")

    def file(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_partial_batch_returns_errors_and_saves_only_valid_rows(self):
        path = self.file("jobs.json", json.dumps([{"text": JOB}, {"text": ""}, {"text": JOB + " Registration fee."}]))
        result = scan_batch_file(self.service, path, save=True)
        self.assertEqual(result["summary"]["succeeded"], 2)
        self.assertEqual(result["errors"][0]["row"], 2)
        self.assertEqual(self.service.repository.list_scans()["total"], 2)

    def test_csv_import_handles_multiline_text_and_boolean_fields(self):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=["text", "application_fee"])
        writer.writeheader()
        writer.writerow({"text": JOB + "\nMore information.", "application_fee": "yes"})
        rows = read_batch(self.file("jobs.csv", stream.getvalue()))
        self.assertIs(rows[0]["application_fee"], True)
        self.assertIn("\nMore information", rows[0]["text"])

    def test_csv_schema_errors_are_clear(self):
        for content in ["title\nA", "text,text\nA,B", "text\nA,B", "text,application_fee\nA,maybe"]:
            with self.subTest(content=content), self.assertRaises(ValidationError):
                read_batch(self.file("jobs.csv", content))

    def test_jsonl_supports_blank_lines_and_reports_bad_line(self):
        valid = json.dumps({"text": JOB})
        self.assertEqual(len(read_batch(self.file("jobs.jsonl", valid + "\n\n" + valid))), 2)
        with self.assertRaisesRegex(ValidationError, "line 3"):
            read_batch(self.file("jobs.jsonl", valid + "\n\nbroken"))

    def test_batch_size_limits_and_wrong_container_are_rejected(self):
        for value in [[], {}, [{"text": JOB}] * 501]:
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValidationError):
                read_batch(self.file("jobs.json", json.dumps(value)))

    def test_csv_export_quotes_formula_cells_and_keeps_input_order(self):
        result = self.service.analyze_batch([{"text": JOB, "title": "=HYPERLINK(1)"}, {"text": ""}])
        rows = list(csv.DictReader(io.StringIO(batch_csv(result))))
        self.assertEqual(rows[0]["title"], "'=HYPERLINK(1)")
        self.assertEqual([row["row"] for row in rows], ["1", "2"])
        self.assertTrue(rows[1]["error"])

    def test_output_replacement_is_complete_and_input_cannot_be_overwritten(self):
        path = self.file("result.json", "old")
        write_output(path, '{"complete": true}\n')
        self.assertEqual(json.loads(path.read_text()), {"complete": True})
        with self.assertRaises(ValidationError):
            write_output(path, "replacement", input_path=path)
        self.assertEqual(json.loads(path.read_text()), {"complete": True})
        self.assertEqual(list(self.root.glob(".jobshield-*.tmp")), [])
