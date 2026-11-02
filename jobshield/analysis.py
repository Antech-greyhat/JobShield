"""Structured recruitment checks layered on the extension-compatible text scan."""

from __future__ import annotations

import re

from .companies import CompanyDirectory
from .models import JobPosting
from .scanner import ScamKeyword, analyze_job_text


URGENCY_PATTERN = re.compile(r"\b(?:urgent(?:ly)?|limited slots|apply immediately|guaranteed job)\b", re.I)
FEE_PATTERN = re.compile(r"\b(?:application|registration|processing|training) fee\b|payment required", re.I)


def assess_posting(posting: JobPosting, keywords: list[ScamKeyword], directory: CompanyDirectory) -> dict:
    base = analyze_job_text(posting.text, keywords)
    identity = directory.check_identity(posting.company_name, posting.company_website, posting.recruiter_email)
    risks: list[dict] = []
    positives: list[str] = []

    def add_risk(code: str, message: str, weight: int, level: str = "medium") -> None:
        risks.append({"code": code, "message": message, "weight": weight, "level": level})

    # The text scanner already charges for these phrases. A boolean fee field or
    # broader manual phrase must not charge for that same evidence a second time.
    fee_already_scored = any(
        rule["term"].lower() in posting.text.lower()
        and ("fee" in rule["term"].lower() or "pay for" in rule["term"].lower())
        for rule in keywords
    )
    if (posting.application_fee or FEE_PATTERN.search(posting.text)) and not fee_already_scored:
        add_risk("upfront_fee", "An application, registration, or training payment is requested.", 40, "high")
    if URGENCY_PATTERN.search(posting.text + " " + posting.title):
        add_risk("urgency", "The listing uses pressure or guaranteed-employment language.", 15)
    if identity["personal_email"]:
        add_risk("personal_email", "The recruiter uses a personal email provider.", 20)
    if identity["mismatches"]:
        add_risk("company_identity_mismatch", " ".join(identity["mismatches"]), 30, "high")
    if posting.has_details and not posting.company_website:
        add_risk("missing_website", "No company website was supplied for independent checking.", 10)
    if posting.interview_method in {"telegram", "whatsapp"}:
        add_risk("messaging_interview", "The interview is arranged through a messaging app.", 30, "high")

    if identity["website_company"] and identity["website_company"]["verified"]:
        positives.append("Website hostname matches a company domain in the bundled directory.")
    if identity["email_company"] and identity["email_company"]["verified"]:
        positives.append("Email hostname matches a company domain in the bundled directory.")
    if posting.company_website:
        positives.append("A company website is available for independent checking.")

    score = max(0, base["score"] - sum(risk["weight"] for risk in risks))
    status = "unknown" if base["status"] == "unknown" else (
        "danger" if score < 40 else "warning" if score < 70 else "safe"
    )
    flags = list(base["flags"])
    flags.extend({"type": "warning", "message": risk["message"], "description": risk["code"]}
                 for risk in risks)
    return {
        "score": score,
        "status": status,
        "flags": flags,
        "text_analysis": base,
        "additional_risks": risks,
        "positive_signals": positives,
        "company_identity": identity,
        "notice": "Heuristic analysis only; verify the employer independently.",
    }
