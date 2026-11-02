from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from jobshield.models import ValidationError
from jobshield.server import LocalAPIServer, MAX_REQUEST_BYTES
from jobshield.service import JobShieldService


JOB = "Job description: Developer. Responsibilities: Build tools. Salary: KES 100,000."
TOKEN = "test-token-with-at-least-thirty-two-characters"
ORIGIN = "http://localhost:5173"


class APITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "api.sqlite3"
        self.service = JobShieldService(self.path)
        self.server = LocalAPIServer(self.service, TOKEN, port=0, origins=(ORIGIN,))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.directory.cleanup()

    def request(self, method, path, payload=None, *, token=TOKEN, headers=None, raw=None):
        values = {"Authorization": "Bearer " + token} if token else {}
        if payload is not None:
            raw = json.dumps(payload).encode("utf-8")
            values["Content-Type"] = "application/json"
        values.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=raw, headers=values)
            response = connection.getresponse()
            content = response.read()
            return response.status, json.loads(content) if content else None, dict(response.getheaders())
        finally:
            connection.close()

    def test_health_is_public_and_does_not_create_database(self):
        for path in ("/health", "/health?"):
            with self.subTest(path=path):
                status, body, headers = self.request("GET", path, token=None)
                self.assertEqual(status, 200, body)
                self.assertEqual(body["status"], "ok")
                self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertFalse(self.path.exists())

    def test_data_endpoints_require_token(self):
        for token in [None, "wrong-token"]:
            with self.subTest(token=token):
                status, body, _ = self.request("GET", "/v1/scans", token=token)
                self.assertEqual((status, body["error"]["code"]), (401, "unauthorized"))
        self.assertFalse(self.path.exists())

    def test_unapproved_origins_and_rebinding_hosts_are_rejected(self):
        for headers in [{"Origin": "https://evil.example"}, {"Host": "evil.example"}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request("GET", "/health", headers=headers)[0], 403)

    def test_explicit_origin_preflight(self):
        status, body, headers = self.request("OPTIONS", "/v1/scans", token=None, headers={
            "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true",
        })
        self.assertEqual((status, body), (204, None))
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")

    def test_unsaved_assessment_then_saved_history_and_delete(self):
        payload = {"posting": {"text": JOB}}
        status, body, _ = self.request("POST", "/v1/scans", payload)
        self.assertEqual((status, body["analysis"]["score"]), (200, 100))
        self.assertFalse(self.path.exists())
        status, saved, _ = self.request("POST", "/v1/scans", {**payload, "save": True})
        self.assertEqual(status, 201)
        identifier = saved["id"]
        self.assertEqual(self.request("GET", "/v1/scans/" + identifier)[1], saved)
        self.assertEqual(self.request("GET", "/v1/scans")[1]["total"], 1)
        self.assertEqual(self.request("DELETE", "/v1/scans/" + identifier)[0], 204)
        self.assertEqual(self.request("GET", "/v1/scans/" + identifier)[0], 404)

    def test_report_submission_review_and_version_conflict(self):
        status, report, _ = self.request("POST", "/v1/reports", {
            "company_name": "Example", "job_url": "https://example.com/job", "reason": "Registration fee.",
        })
        self.assertEqual((status, report["status"]), (201, "pending"))
        path = "/v1/reports/" + report["id"]
        patch = {"status": "approved", "note": "Confirmed fee request.", "version": 1}
        status, reviewed, _ = self.request("PATCH", path, patch)
        self.assertEqual((status, reviewed["version"], len(reviewed["events"])), (200, 2, 2))
        self.assertEqual(self.request("PATCH", path, patch)[0], 409)
        self.assertEqual(self.request("GET", path)[1]["version"], 2)
        self.assertEqual(self.request("GET", "/v1/reports?status=approved")[1]["total"], 1)

    def test_batch_keeps_valid_records_and_reports_bad_rows(self):
        status, result, _ = self.request("POST", "/v1/batch", {"postings": [{"text": JOB}, {}]})
        self.assertEqual(status, 200)
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual(result["errors"][0]["row"], 2)

    def test_parallel_saves_are_preserved(self):
        def save(index):
            return self.request("POST", "/v1/scans", {"posting": {"text": JOB, "title": str(index)}, "save": True})[0]

        with ThreadPoolExecutor(max_workers=4) as executor:
            statuses = list(executor.map(save, range(8)))
        self.assertEqual(statuses, [201] * 8)
        self.assertEqual(self.request("GET", "/v1/stats")[1]["scan_count"], 8)

    def test_bad_json_duplicate_keys_and_nonfinite_numbers_are_rejected(self):
        for body in [b"broken", b'{"posting": {}, "posting": {}}', b'{"posting": NaN}', b"\xff"]:
            with self.subTest(body=body):
                status, result, _ = self.request("POST", "/v1/scans", raw=body,
                                                headers={"Content-Type": "application/json"})
                self.assertEqual((status, result["error"]["code"]), (400, "invalid_json"))

    def test_oversized_and_wrong_content_type_requests_are_rejected(self):
        status, _, _ = self.request("POST", "/v1/scans", raw=b"{}", headers={
            "Content-Type": "application/json", "Content-Length": str(MAX_REQUEST_BYTES + 1),
        })
        self.assertEqual(status, 413)
        self.assertEqual(self.request("POST", "/v1/scans", raw=b"{}", headers={"Content-Type": "text/plain"})[0], 415)

    def test_invalid_parameters_and_wrong_field_types_return_400(self):
        for path in ["/v1/scans?limit=no", "/v1/scans?limit=0", "/v1/scans?status=invalid",
                     "/v1/scans?limit=1&limit=2", "/v1/scans?unexpected=yes", "/v1/stats?days=0",
                     "/health?flag", "/v1/scans?limit", "/v1/scans?limit=1&"]:
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 400)
        for payload in [[], {}, {"posting": {"text": JOB}, "save": "false"}, {"posting": {"text": 5}}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("POST", "/v1/scans", payload)[0], 400)

    def test_company_and_rules_endpoints_return_bundled_data(self):
        status, companies, _ = self.request("GET", "/v1/companies?q=safaricom")
        self.assertEqual((status, companies["items"][0]["domain"]), (200, "safaricom.co.ke"))
        self.assertEqual(len(self.request("GET", "/v1/rules")[1]["items"]), 6)

    def test_unknown_endpoint_and_wrong_method_have_json_errors(self):
        self.assertEqual(self.request("GET", "/v1/missing")[0], 404)
        self.assertEqual(self.request("DELETE", "/v1/rules")[0], 405)
        _, saved, _ = self.request("POST", "/v1/scans", {"posting": {"text": JOB}, "save": True})
        self.assertEqual(self.request("PATCH", "/v1/scans/" + saved["id"], {})[0], 405)

    def test_invalid_server_configuration_is_rejected_before_binding(self):
        for options in [{"token": "short"}, {"token": TOKEN, "origins": ("*",)},
                        {"token": TOKEN, "origins": ("https://evil.example",)}]:
            with self.subTest(options=options), self.assertRaises(ValidationError):
                LocalAPIServer(self.service, port=0, **options)
