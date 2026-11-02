"""Token-authenticated loopback API for local JobShield clients."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .models import (
    ConflictError, NotFoundError, ValidationError, boolean_field,
    integer_field, object_fields, text_field,
)
from .service import JobShieldService


LOGGER = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 1_000_000
IDENTIFIER_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def validate_origin(origin: str) -> str:
    parts = urlsplit(origin)
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        raise ValidationError("An allowed origin must contain only a scheme and host, with an optional port.")
    if parts.scheme == "chrome-extension" and re.fullmatch(r"[a-p]{32}", parts.netloc):
        return origin
    if parts.scheme in {"http", "https"} and parts.hostname in {"localhost", "127.0.0.1"}:
        try:
            parts.port
        except ValueError as error:
            raise ValidationError("Allowed origin has an invalid port.") from error
        return origin
    raise ValidationError("Allowed origins must be explicit localhost URLs or Chrome extension origins.")


class LocalAPIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, service: JobShieldService, token: str, *, port: int = 8765, origins: tuple[str, ...] = ()):
        if not isinstance(token, str) or len(token) < 32 or not token.isascii() or any(char.isspace() for char in token):
            raise ValidationError("API token must contain at least 32 ASCII characters without whitespace.")
        integer_field(port, "port", 0, 65535)
        self.service = service
        self.token = token
        self.origins = frozenset(validate_origin(origin) for origin in origins)
        super().__init__(("127.0.0.1", port), APIHandler)


class APIHandler(BaseHTTPRequestHandler):
    server_version = "JobShield/" + __version__
    sys_version = ""
    timeout = 10

    def log_message(self, format: str, *args: object) -> None:
        # Avoid logging request bodies, tokens, and job URLs.
        LOGGER.debug("Local API request completed.")

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def do_OPTIONS(self) -> None:
        self._handle("OPTIONS")

    def _send(self, status: int, payload: object | None) -> None:
        content = json.dumps(payload, allow_nan=False).encode("utf-8") if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin", "")
        self.send_header("Vary", "Origin")
        if origin in self.server.origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        if content:
            self.wfile.write(content)

    def _check_client(self, *, authenticate: bool) -> None:
        port = self.server.server_address[1]
        if self.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            raise APIError(403, "invalid_host", "Host must refer to this local API.")
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self.server.origins:
            raise APIError(403, "origin_denied", "This browser origin is not allowed.")
        if authenticate:
            expected = "Bearer " + self.server.token
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
                raise APIError(401, "unauthorized", "A valid bearer token is required.")

    def _json_body(self) -> object:
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "unsupported_encoding", "Chunked request bodies are not supported.")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise APIError(411, "length_required", "Supply one Content-Length header.")
        try:
            size = int(lengths[0])
        except ValueError as error:
            raise APIError(400, "invalid_length", "Content-Length must be an integer.") from error
        if size < 1 or size > MAX_REQUEST_BYTES:
            raise APIError(413, "body_size", f"Request body must contain 1 to {MAX_REQUEST_BYTES} bytes.")
        if self.headers.get_content_type() != "application/json":
            raise APIError(415, "content_type", "Content-Type must be application/json.")
        data = self.rfile.read(size)
        if len(data) != size:
            raise APIError(400, "incomplete_body", "Request body ended before Content-Length.")
        try:
            return json.loads(data.decode("utf-8"), parse_constant=self._reject_constant,
                              object_pairs_hook=self._unique_object)
        except (UnicodeError, ValueError, RecursionError) as error:
            raise APIError(400, "invalid_json", "Body must be valid UTF-8 JSON with unique object keys.") from error

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise ValueError(f"Invalid JSON number: {value}.")

    @staticmethod
    def _unique_object(pairs: list[tuple]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate object key.")
            result[key] = value
        return result

    @staticmethod
    def _query(raw: str, allowed: set[str]) -> dict[str, str]:
        try:
            data = parse_qs(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=10)
        except ValueError as error:
            raise ValidationError("Query parameters are invalid.") from error
        if set(data) - allowed:
            raise ValidationError("Query includes unsupported parameters.")
        if any(len(values) != 1 for values in data.values()):
            raise ValidationError("Query parameters cannot be repeated.")
        return {key: values[0] for key, values in data.items()}

    @classmethod
    def _pagination(cls, raw: str) -> dict:
        query = cls._query(raw, {"status", "q", "limit", "offset"})
        try:
            return {
                "status": query.get("status", ""), "query": query.get("q", ""),
                "limit": int(query.get("limit", "50")), "offset": int(query.get("offset", "0")),
            }
        except ValueError as error:
            raise ValidationError("limit and offset must be integers.") from error

    def _dispatch(self, method: str, path: str, query: str) -> tuple[int, object | None]:
        service = self.server.service
        if path == "/health" and method == "GET":
            self._query(query, set())
            return 200, {"status": "ok", "version": __version__}
        if path == "/v1/scans":
            if method == "GET":
                return 200, service.repository.list_scans(**self._pagination(query))
            if method == "POST":
                self._query(query, set())
                data = object_fields(self._json_body(), {"posting", "save"})
                save = boolean_field(data.get("save", False), "save")
                return (201 if save else 200), service.assess(data.get("posting"), save=save, source="local-api")
        if path == "/v1/batch" and method == "POST":
            self._query(query, set())
            data = object_fields(self._json_body(), {"postings", "save"})
            return 200, service.analyze_batch(data.get("postings"), save=data.get("save", False))
        if path == "/v1/reports":
            if method == "GET":
                return 200, service.repository.list_reports(**self._pagination(query))
            if method == "POST":
                self._query(query, set())
                return 201, service.submit_report(self._json_body())
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] in (["v1", "scans"], ["v1", "reports"]):
            self._query(query, set())
            identifier = parts[2]
            if not IDENTIFIER_PATTERN.fullmatch(identifier):
                raise NotFoundError("Resource not found.")
            repository = service.repository
            if parts[1] == "scans":
                if method == "GET":
                    return 200, repository.get_scan(identifier)
                if method == "DELETE":
                    repository.delete_scan(identifier)
                    return 204, None
            elif method == "GET":
                return 200, repository.get_report(identifier)
            elif method == "PATCH":
                data = object_fields(self._json_body(), {"status", "note", "version"})
                return 200, repository.review_report(
                    identifier, data.get("status"), data.get("note", ""), data.get("version"),
                )
            raise APIError(405, "method_not_allowed", "This resource does not support that method.")
        if path == "/v1/companies" and method == "GET":
            parameters = self._query(query, {"q"})
            query_text = text_field(parameters.get("q", ""), "q", limit=300)
            return 200, {"items": service.directory.search(query_text)}
        if path == "/v1/rules" and method == "GET":
            self._query(query, set())
            return 200, {"items": service.keywords}
        if path == "/v1/stats" and method == "GET":
            parameters = self._query(query, {"days"})
            try:
                days = int(parameters.get("days", "30"))
            except ValueError as error:
                raise ValidationError("days must be an integer.") from error
            return 200, service.repository.statistics(days)
        if path in {"/health", "/v1/scans", "/v1/batch", "/v1/reports", "/v1/companies", "/v1/rules", "/v1/stats"}:
            raise APIError(405, "method_not_allowed", "This endpoint does not support that method.")
        raise NotFoundError("Endpoint not found.")

    def _handle(self, method: str) -> None:
        try:
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                raise APIError(400, "invalid_target", "Use a relative API path.")
            health = method == "GET" and parsed.path == "/health"
            self._check_client(authenticate=not health and method != "OPTIONS")
            if method == "OPTIONS":
                if self.headers.get("Access-Control-Request-Method") not in {"GET", "POST", "PATCH", "DELETE"}:
                    raise APIError(405, "method_not_allowed", "Requested CORS method is not supported.")
                self._send(204, None)
                return
            status, payload = self._dispatch(method, parsed.path, parsed.query)
            self._send(status, payload)
        except APIError as error:
            self._send(error.status, {"error": {"code": error.code, "message": error.message}})
        except NotFoundError as error:
            self._send(404, {"error": {"code": "not_found", "message": str(error)}})
        except ConflictError as error:
            self._send(409, {"error": {"code": "conflict", "message": str(error)}})
        except (ValidationError, ValueError) as error:
            self._send(400, {"error": {"code": "invalid_input", "message": str(error)}})
        except sqlite3.Error:
            LOGGER.exception("Local database operation failed.")
            self._send(503, {"error": {"code": "database_unavailable", "message": "The local database is unavailable."}})
        except (BrokenPipeError, ConnectionResetError):
            return
        except TimeoutError:
            self._send(408, {"error": {"code": "request_timeout", "message": "Request body was not received in time."}})
