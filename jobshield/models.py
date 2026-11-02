"""Validation shared by the command line, batch importer, and HTTP API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import re
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


MAX_TEXT_LENGTH = 200_000
SCAN_STATUSES = ("unknown", "safe", "warning", "danger")
REPORT_STATUSES = ("pending", "approved", "dismissed")
INTERVIEW_METHODS = ("", "phone", "video", "in_person", "telegram", "whatsapp")


class ValidationError(ValueError):
    """An input field cannot be accepted."""


class NotFoundError(LookupError):
    """A requested saved scan or report does not exist."""


class ConflictError(ValueError):
    """A report changed since it was read, or its transition is invalid."""


def text_field(value: object, name: str, *, required: bool = False, limit: int = 500) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be a string.")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{name} is required.")
    if len(value) > limit:
        raise ValidationError(f"{name} must be at most {limit} characters.")
    if "\x00" in value:
        raise ValidationError(f"{name} cannot contain a null character.")
    return value


def boolean_field(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{name} must be true or false.")
    return value


def integer_field(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{name} must be an integer from {minimum} to {maximum}.")
    return value


def object_fields(value: object, allowed: set[str], name: str = "Request") -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{name} must be a JSON object.")
    unknown = set(value) - allowed
    if unknown:
        raise ValidationError(f"{name} has unsupported fields: {', '.join(sorted(map(str, unknown)))}.")
    return value


def normalize_domain(value: str) -> str:
    """Normalize a host without allowing deceptive suffix or credential matches."""
    host = value.rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ValidationError("Domain is not a valid internationalized hostname.") from error
    if len(host) > 253 or "." not in host:
        raise ValidationError("Domain must be a complete hostname.")
    labels = host.split(".")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
        raise ValidationError("Domain contains an invalid hostname label.")
    return host


def web_url(value: object, name: str, *, required: bool = False) -> str:
    url = text_field(value, name, required=required, limit=2048)
    if not url:
        return ""
    if any(character.isspace() or ord(character) < 32 for character in url):
        raise ValidationError(f"{name} cannot contain whitespace or control characters.")
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("Only HTTP and HTTPS URLs are accepted.")
        if parts.username is not None or parts.password is not None:
            raise ValueError("Credentials are not allowed in URLs.")
        host = normalize_domain(parts.hostname)
        port = parts.port
    except ValueError as error:
        raise ValidationError(f"Invalid {name}: {error}") from error
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


def email_address(value: object) -> str:
    email = text_field(value, "recruiter_email", limit=254)
    if not email:
        return ""
    if email.count("@") != 1 or any(character.isspace() for character in email):
        raise ValidationError("recruiter_email must be a single email address.")
    local, domain = email.rsplit("@", 1)
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local):
        raise ValidationError("recruiter_email has an invalid local part.")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValidationError("recruiter_email has invalid dot placement.")
    return f"{local}@{normalize_domain(domain)}"


@dataclass(frozen=True)
class JobPosting:
    text: str
    title: str = ""
    company_name: str = ""
    company_website: str = ""
    recruiter_email: str = ""
    application_fee: bool = False
    interview_method: str = ""
    url: str = ""

    @classmethod
    def from_mapping(cls, value: object) -> JobPosting:
        data = object_fields(value, {field.name for field in fields(cls)}, "Posting")
        method = text_field(data.get("interview_method", ""), "interview_method").lower()
        if method not in INTERVIEW_METHODS:
            raise ValidationError(f"interview_method must be one of: {', '.join(INTERVIEW_METHODS[1:])}.")
        return cls(
            text=text_field(data.get("text", ""), "text", required=True, limit=MAX_TEXT_LENGTH),
            title=text_field(data.get("title", ""), "title", limit=300),
            company_name=text_field(data.get("company_name", ""), "company_name", limit=300),
            company_website=web_url(data.get("company_website", ""), "company_website"),
            recruiter_email=email_address(data.get("recruiter_email", "")),
            application_fee=boolean_field(data.get("application_fee", False), "application_fee"),
            interview_method=method,
            url=web_url(data.get("url", ""), "url"),
        )

    @property
    def has_details(self) -> bool:
        return bool(self.company_name or self.company_website or self.recruiter_email
                    or self.application_fee or self.interview_method)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportSubmission:
    company_name: str
    job_url: str
    reason: str

    @classmethod
    def from_mapping(cls, value: object) -> ReportSubmission:
        data = object_fields(value, {"company_name", "job_url", "reason"}, "Report")
        return cls(
            company_name=text_field(data.get("company_name", ""), "company_name", required=True, limit=300),
            job_url=web_url(data.get("job_url", ""), "job_url", required=True),
            reason=text_field(data.get("reason", ""), "reason", required=True, limit=10_000),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
