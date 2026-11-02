"""Offline company-directory lookups with exact hostname boundary checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from urllib.parse import urlsplit

from .models import ValidationError, normalize_domain, text_field


DEFAULT_COMPANIES_PATH = Path(__file__).resolve().parents[1] / "data" / "verifiedcompanies.json"
PERSONAL_EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "hotmail.com",
    "outlook.com", "live.com", "aol.com", "icloud.com", "proton.me", "protonmail.com",
})


def domain_matches(host: str, domain: str) -> bool:
    """A subdomain matches; a hostname merely containing the domain does not."""
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


@dataclass(frozen=True)
class Company:
    name: str
    domain: str
    verified: bool

    def to_dict(self) -> dict:
        return asdict(self)


class CompanyDirectory:
    def __init__(self, companies: list[Company]):
        self._companies = tuple(companies)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_COMPANIES_PATH) -> CompanyDirectory:
        with Path(path).open(encoding="utf-8-sig") as source:
            data = json.load(source)
        if not isinstance(data, list):
            raise ValidationError("Company directory must be a JSON array.")
        companies = []
        domains: set[str] = set()
        for index, row in enumerate(data, 1):
            if not isinstance(row, dict):
                raise ValidationError(f"Company {index} must be an object.")
            name = text_field(row.get("name", ""), "Company name", required=True)
            domain = normalize_domain(text_field(row.get("domain", ""), "Company domain", required=True))
            if type(row.get("verified")) is not bool:
                raise ValidationError(f"Company {index} needs a boolean verified field.")
            if domain in domains:
                raise ValidationError(f"Duplicate company domain: {domain}.")
            domains.add(domain)
            companies.append(Company(name, domain, row["verified"]))
        return cls(companies)

    def search(self, query: str = "", limit: int = 50) -> list[dict]:
        query = query.strip().casefold()
        found = [company.to_dict() for company in self._companies
                 if query in company.name.casefold() or query in company.domain]
        return found[:limit]

    def by_name(self, name: str) -> Company | None:
        normalized = " ".join(name.casefold().split())
        return next((company for company in self._companies
                     if " ".join(company.name.casefold().split()) == normalized), None)

    def by_domain(self, domain: str) -> Company | None:
        matches = [company for company in self._companies if domain_matches(domain, company.domain)]
        return max(matches, key=lambda company: len(company.domain), default=None)

    def check_identity(self, name: str = "", website: str = "", email: str = "") -> dict:
        """Return evidence from the bundled directory, without certifying a posting."""
        website_host = urlsplit(website).hostname or ""
        email_host = email.rsplit("@", 1)[1] if "@" in email else ""
        named_company = self.by_name(name) if name else None
        website_company = self.by_domain(website_host) if website_host else None
        email_company = self.by_domain(email_host) if email_host else None
        mismatches = []
        if named_company:
            if website_host and not domain_matches(website_host, named_company.domain):
                mismatches.append("Company website does not match the named company's listed domain.")
            if email_host and not domain_matches(email_host, named_company.domain):
                mismatches.append("Recruiter email does not match the named company's listed domain.")
        if website_company and email_host and not domain_matches(email_host, website_company.domain):
            message = "Recruiter email does not match the website's listed company domain."
            if not named_company:
                mismatches.append(message)
        return {
            "named_company": named_company.to_dict() if named_company else None,
            "website_company": website_company.to_dict() if website_company else None,
            "email_company": email_company.to_dict() if email_company else None,
            "personal_email": email_host in PERSONAL_EMAIL_DOMAINS,
            "mismatches": mismatches,
            "notice": "Directory matches are reference information, not proof that a recruiter or posting is legitimate.",
        }
