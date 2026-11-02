"""Local recruitment-fraud analysis, storage, and reporting tools."""

from .scanner import DEFAULT_RULES_PATH, analyze_job_text, load_keywords

__version__ = "1.1.0"
__all__ = ["DEFAULT_RULES_PATH", "analyze_job_text", "load_keywords"]
