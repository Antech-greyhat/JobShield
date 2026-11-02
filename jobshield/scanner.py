"""Offline job-posting analysis using the browser extension's shared scam rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypedDict


DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "scamkeywords.json"
JOB_INDICATORS = (
    "job description",
    "responsibilities",
    "qualifications",
    "requirements",
    "apply now",
    "hiring",
    "salary",
    "experience",
    "employment type",
)


class ScamKeyword(TypedDict):
    term: str
    weight: int
    description: str


class Flag(TypedDict):
    type: Literal["info", "warning"]
    message: str
    description: str


class Analysis(TypedDict):
    score: int
    flags: list[Flag]
    status: Literal["unknown", "safe", "warning", "danger"]


def _validate_keywords(data: object) -> list[ScamKeyword]:
    """Reject malformed rules instead of silently changing the risk score."""
    if not isinstance(data, list) or not data:
        raise ValueError("Scam rules must be a non-empty JSON array.")

    keywords: list[ScamKeyword] = []
    seen: set[str] = set()
    for index, rule in enumerate(data, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"Scam rule {index} must be an object.")
        term = rule.get("term")
        weight = rule.get("weight")
        description = rule.get("description")
        if not isinstance(term, str) or not term.strip():
            raise ValueError(f"Scam rule {index} needs a non-empty term.")
        if type(weight) is not int or not 1 <= weight <= 100:
            raise ValueError(f"Scam rule {index} needs an integer weight from 1 to 100.")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Scam rule {index} needs a non-empty description.")
        if term.lower() in seen:
            raise ValueError(f"Duplicate scam term: {term!r}.")
        seen.add(term.lower())
        keywords.append(ScamKeyword(term=term, weight=weight, description=description))
    return keywords


def load_keywords(path: str | Path = DEFAULT_RULES_PATH) -> list[ScamKeyword]:
    """Load UTF-8 rules, including files with a byte-order mark from text editors."""
    with Path(path).open(encoding="utf-8-sig") as rules_file:
        return _validate_keywords(json.load(rules_file))


def analyze_job_text(
    text: str, scam_keywords: list[ScamKeyword] | None = None
) -> Analysis:
    """Match scripts/scanner.js scoring, flag order, and status thresholds.

    A score describes matched heuristics; it does not verify an employer.
    Custom rules use the same schema as data/scamkeywords.json.
    """
    if not isinstance(text, str):
        raise TypeError("Job text must be a string.")
    keywords = load_keywords() if scam_keywords is None else _validate_keywords(scam_keywords)
    if not text:
        return Analysis(score=0, flags=[], status="unknown")

    text_lower = text.lower()
    if sum(indicator in text_lower for indicator in JOB_INDICATORS) < 2:
        return Analysis(
            score=0,
            flags=[Flag(
                type="info",
                message="Not a Job Posting",
                description=(
                    "This page does not contain enough standard job keywords "
                    "(e.g., responsibilities, requirements) to be analyzed."
                ),
            )],
            status="unknown",
        )

    score = 100
    flags: list[Flag] = []
    for keyword in keywords:
        if keyword["term"].lower() in text_lower:
            score -= keyword["weight"]
            flags.append(Flag(
                type="warning",
                message=f'Found suspicious phrase: "{keyword["term"]}"',
                description=keyword["description"],
            ))

    if "salary" not in text_lower and "pay" not in text_lower:
        score -= 10
        flags.append(Flag(
            type="info",
            message="No salary information provided",
            description="Legitimate jobs usually mention salary or compensation.",
        ))

    status: Literal["safe", "warning", "danger"] = "safe"
    if score < 40:
        status = "danger"
    elif score < 70:
        status = "warning"
    return Analysis(score=max(0, score), flags=flags, status=status)


