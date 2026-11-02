"""Application operations used consistently by the CLI, batch importer, and API."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from .analysis import assess_posting
from .companies import CompanyDirectory, DEFAULT_COMPANIES_PATH
from .models import JobPosting, ReportSubmission, ValidationError, boolean_field
from .scanner import DEFAULT_RULES_PATH, analyze_job_text, load_keywords
from .storage import DEFAULT_DATABASE, Repository


class JobShieldService:
    def __init__(
        self, database: str | Path = DEFAULT_DATABASE, *,
        rules_path: str | Path = DEFAULT_RULES_PATH,
        companies_path: str | Path = DEFAULT_COMPANIES_PATH,
    ):
        self.keywords = load_keywords(rules_path)
        self.directory = CompanyDirectory.load(companies_path)
        self.database = Path(database)
        self._repository: Repository | None = None
        self._repository_lock = Lock()

    @property
    def repository(self) -> Repository:
        # Do not create a database for scans that the user has not chosen to save.
        with self._repository_lock:
            if self._repository is None:
                self._repository = Repository(self.database)
            return self._repository

    def scan_text(self, text: str, *, save: bool = False, source: str = "") -> dict:
        boolean_field(save, "save")
        posting = JobPosting.from_mapping({"text": text})
        result = analyze_job_text(posting.text, self.keywords)
        if save:
            return self.repository.save_scan(posting, result, source)
        return result

    def assess(self, data: dict | JobPosting, *, save: bool = False, source: str = "") -> dict:
        boolean_field(save, "save")
        posting = JobPosting.from_mapping(data.to_dict() if isinstance(data, JobPosting) else data)
        result = assess_posting(posting, self.keywords, self.directory)
        if save:
            return self.repository.save_scan(posting, result, source)
        return {"posting": posting.to_dict(), "analysis": result}

    def analyze_batch(self, postings: object, *, save: bool = False) -> dict:
        boolean_field(save, "save")
        if not isinstance(postings, list) or not 1 <= len(postings) <= 500:
            raise ValidationError("postings must be an array with 1 to 500 entries.")
        items, errors = [], []
        for index, data in enumerate(postings, 1):
            try:
                items.append({"row": index, **self.assess(data, save=save, source=f"batch:{index}")})
            except ValidationError as error:
                errors.append({"row": index, "error": str(error)})
        statuses = {status: 0 for status in ("unknown", "safe", "warning", "danger")}
        for item in items:
            statuses[item["analysis"]["status"]] += 1
        return {
            "items": items, "errors": errors,
            "summary": {"total": len(postings), "succeeded": len(items), "failed": len(errors), "statuses": statuses},
        }

    def submit_report(self, data: dict) -> dict:
        return self.repository.create_report(ReportSubmission.from_mapping(data))
