import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from jobshield import analyze_job_text, load_keywords


ROOT = Path(__file__).resolve().parents[1]
VALID_JOB = "Job description: Engineering. Responsibilities: Build tools. Salary: KES 100,000."


class ScannerTests(unittest.TestCase):
    def test_ordinary_job_has_no_flags(self):
        self.assertEqual(analyze_job_text(VALID_JOB), {"score": 100, "flags": [], "status": "safe"})

    def test_non_job_text_is_unknown(self):
        result = analyze_job_text("Welcome to our website.")
        self.assertEqual((result["score"], result["status"]), (0, "unknown"))
        self.assertEqual(result["flags"][0]["message"], "Not a Job Posting")
        self.assertEqual(analyze_job_text(""), {"score": 0, "flags": [], "status": "unknown"})

    def test_repeating_one_job_indicator_does_not_qualify(self):
        self.assertEqual(analyze_job_text("Hiring hiring hiring")["status"], "unknown")

    def test_scam_phrase_is_case_insensitive_and_counted_once(self):
        result = analyze_job_text(VALID_JOB + " REGISTRATION FEE. Registration fee.")
        self.assertEqual((result["score"], result["status"]), (60, "warning"))
        self.assertEqual(len(result["flags"]), 1)

    def test_multiple_risks_clamp_score_to_zero(self):
        result = analyze_job_text(VALID_JOB + " Pay for training. Registration fee via mpesa.")
        self.assertEqual((result["score"], result["status"]), (0, "danger"))
        self.assertEqual(len(result["flags"]), 3)

    def test_missing_compensation_reduces_score(self):
        result = analyze_job_text("Responsibilities: Build tools. Requirements: Python.")
        self.assertEqual(result["score"], 90)
        self.assertEqual(result["flags"][0]["message"], "No salary information provided")

    def test_status_boundaries(self):
        for weight, score, status in [(30, 70, "safe"), (31, 69, "warning"),
                                      (60, 40, "warning"), (61, 39, "danger")]:
            with self.subTest(weight=weight):
                rules = [{"term": "deposit", "weight": weight, "description": "Upfront fee."}]
                result = analyze_job_text(VALID_JOB + " Deposit required.", rules)
                self.assertEqual((result["score"], result["status"]), (score, status))

    def test_malformed_rules_are_rejected(self):
        valid = {"term": "deposit", "weight": 20, "description": "Upfront fee."}
        invalid = [{}, [], ["deposit"],
                   [{**valid, "term": " "}], [{**valid, "description": ""}],
                   [valid, {**valid, "term": "DEPOSIT"}]]
        invalid.extend([{**valid, "weight": value}] for value in [True, -1, 0, 101, 2.5, "20"])
        for rules in invalid:
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                analyze_job_text(VALID_JOB, rules)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-scanner parity")
    def test_matches_browser_scanner_for_every_rule_combination(self):
        rules = load_keywords()
        samples = ["", "Welcome", "Hiring hiring", "Responsibilities and requirements"]
        for included in itertools.product((False, True), repeat=len(rules)):
            phrases = [rule["term"] for rule, enabled in zip(rules, included) if enabled]
            samples.append(VALID_JOB + " " + " ".join(phrases))
        samples.extend([VALID_JOB.upper() + " REGISTRATION FEE", VALID_JOB + " mpesa mpesa"])
        # Import the browser ES module without changing package.json's CommonJS setting.
        script = """
            import { readFileSync } from 'node:fs';
            const source = readFileSync('scripts/scanner.js', 'utf8');
            const { analyzeJobText } = await import(
                'data:text/javascript;base64,' + Buffer.from(source).toString('base64')
            );
            const { samples, rules } = JSON.parse(readFileSync(0, 'utf8'));
            console.log(JSON.stringify(samples.map(text => analyzeJobText(text, rules, []))));
        """
        browser = subprocess.run(
            ["node", "--input-type=module", "-e", script], cwd=ROOT,
            input=json.dumps({"samples": samples, "rules": rules}),
            text=True, capture_output=True, check=True, timeout=30,
        )
        for sample, expected in zip(samples, json.loads(browser.stdout)):
            with self.subTest(text=sample):
                self.assertEqual(analyze_job_text(sample), expected)


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *args, input=None, cwd=ROOT):
        return subprocess.run(
            [sys.executable, str(ROOT / "jobshield.py"), *args],
            input=input, cwd=cwd, text=True, capture_output=True, timeout=30,
        )

    def test_json_output(self):
        result = self.run_cli("--text", VALID_JOB + " Registration fee.", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), analyze_job_text(VALID_JOB + " Registration fee."))

    def test_readable_output(self):
        result = self.run_cli("--text", VALID_JOB)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Trust score: 100/100", result.stdout)
        self.assertIn("verify the employer independently", result.stdout)

    def test_standard_input(self):
        result = self.run_cli("--stdin", "--json", input=VALID_JOB)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["score"], 100)

    def test_utf8_file_and_default_rules_work_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "posting.txt"
            path.write_text(VALID_JOB + " Nairobi – Kenya.", encoding="utf-8-sig")
            result = self.run_cli("--file", str(path), "--json", cwd=directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["score"], 100)

    def test_custom_rules_file(self):
        with tempfile.TemporaryDirectory() as directory:
            rules = Path(directory) / "rules.json"
            rules.write_text(json.dumps([
                {"term": "deposit", "weight": 70, "description": "Upfront fee."}
            ]), encoding="utf-8-sig")
            result = self.run_cli("--text", VALID_JOB + " Deposit.", "--rules", str(rules), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["score"], 30)

    def test_missing_or_empty_input_is_an_error(self):
        for args, input_text in [((), None), (("--text", "   "), None),
                                 (("--stdin",), ""), (("--text", VALID_JOB, "--stdin"), "")]:
            with self.subTest(args=args):
                result = self.run_cli(*args, input=input_text)
                self.assertEqual(result.returncode, 2)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_missing_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing.txt")
            for args in [("--file", missing), ("--text", VALID_JOB, "--rules", missing)]:
                with self.subTest(args=args):
                    result = self.run_cli(*args)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("error:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_invalid_rules_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            rules = Path(directory) / "rules.json"
            for content in ["not json", "null", "{}", "[]"]:
                with self.subTest(content=content):
                    rules.write_text(content, encoding="utf-8")
                    result = self.run_cli("--text", VALID_JOB, "--rules", str(rules))
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("error:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
