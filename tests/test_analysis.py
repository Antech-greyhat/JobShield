import json
from pathlib import Path
import tempfile
import unittest

from jobshield.analysis import assess_posting
from jobshield.companies import CompanyDirectory
from jobshield.models import JobPosting, ValidationError, email_address, web_url
from jobshield.scanner import load_keywords


JOB = "Job description: Developer. Responsibilities: Write software. Salary: KES 100,000."


class StructuredAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.directory = CompanyDirectory.load()
        self.rules = load_keywords()

    def assess(self, **fields):
        return assess_posting(JobPosting.from_mapping({"text": JOB, **fields}), self.rules, self.directory)

    def test_text_only_assessment_matches_base_scan(self):
        result = self.assess()
        self.assertEqual(result["score"], result["text_analysis"]["score"])
        self.assertEqual(result["additional_risks"], [])

    def test_named_company_with_spoofed_domain_is_flagged(self):
        result = self.assess(company_name="Safaricom", company_website="https://safaricom.co.ke.evil.example/jobs")
        self.assertEqual(result["score"], 70)
        self.assertIn("company_identity_mismatch", [risk["code"] for risk in result["additional_risks"]])
        self.assertIsNone(result["company_identity"]["website_company"])

    def test_subdomain_matches_without_awarding_extra_score(self):
        result = self.assess(
            company_name="SAFARICOM", company_website="https://careers.safaricom.co.ke/jobs",
            recruiter_email="hiring@safaricom.co.ke",
        )
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["company_identity"]["mismatches"], [])
        self.assertEqual(len(result["positive_signals"]), 3)

    def test_name_alone_does_not_verify_recruiter(self):
        result = self.assess(company_name="Safaricom")
        self.assertEqual(result["positive_signals"], [])
        self.assertEqual(result["score"], 90)

    def test_upfront_fee_is_not_double_charged(self):
        result = self.assess(text=JOB + " Registration fee required.", application_fee=True,
                             company_website="https://example.com")
        self.assertEqual(result["score"], 60)
        self.assertNotIn("upfront_fee", [risk["code"] for risk in result["additional_risks"]])

    def test_structured_fee_and_messaging_interview_reduce_score(self):
        result = self.assess(application_fee=True, interview_method="WhatsApp",
                             recruiter_email="hiring@gmail.com", company_website="https://example.com")
        self.assertEqual((result["score"], result["status"]), (10, "danger"))
        self.assertEqual({risk["code"] for risk in result["additional_risks"]},
                         {"upfront_fee", "messaging_interview", "personal_email"})

    def test_non_job_remains_unknown_even_with_company_metadata(self):
        result = self.assess(text="Welcome to our website.", company_name="Safaricom")
        self.assertEqual((result["score"], result["status"]), (0, "unknown"))

    def test_urgency_and_unlisted_fee_phrases_are_detected(self):
        result = self.assess(text=JOB + " Processing fee required. Limited slots.")
        self.assertEqual(result["score"], 45)
        self.assertEqual(len(result["additional_risks"]), 2)


class InputValidationTests(unittest.TestCase):
    def test_posting_rejects_typos_and_wrong_types(self):
        invalid = [None, [], {"text": JOB, "recruiterEmail": "a@example.com"},
                   {"text": JOB, "application_fee": "false"}, {"text": JOB, "interview_method": "unknown"},
                   {"text": " "}, {"text": 5}, {"text": JOB, "title": "x" * 301}]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                JobPosting.from_mapping(data)

    def test_urls_reject_credentials_and_non_web_schemes(self):
        for url in ["javascript:alert(1)", "https://safaricom.co.ke@evil.example/", "file:///tmp/posting",
                    "https://example.com:70000", "https://exa mple.com"]:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                web_url(url, "url")
        self.assertEqual(web_url("https://EXAMPLE.com/job#section", "url"), "https://example.com/job")
        self.assertEqual(web_url(" https://example.com\n", "url"), "https://example.com")

    def test_emails_normalize_domain_and_reject_malformed_addresses(self):
        self.assertEqual(email_address("Jobs@EXAMPLE.COM"), "Jobs@example.com")
        for value in ["a@@example.com", "a@bad_domain.com", "a..b@example.com", "@example.com", "a b@example.com"]:
            with self.subTest(email=value), self.assertRaises(ValidationError):
                email_address(value)

    def test_directory_rejects_duplicate_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "companies.json"
            path.write_text(json.dumps([
                {"name": "A", "domain": "example.com", "verified": True},
                {"name": "B", "domain": "EXAMPLE.COM", "verified": True},
            ]), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "Duplicate"):
                CompanyDirectory.load(path)
