"""Read local text or saved HTML without downloading pages or executing scripts."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re

from .models import JobPosting, MAX_TEXT_LENGTH, ValidationError


MAX_DOCUMENT_BYTES = 5_000_000
BLOCK_TAGS = frozenset({"p", "div", "section", "article", "main", "header", "footer",
                       "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "br", "tr"})
IGNORED_TAGS = frozenset({"script", "style", "noscript", "template", "svg"})
VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input",
                      "link", "meta", "param", "source", "track", "wbr"})


class PostingHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.schema_blocks: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.in_title = False
        self.schema_parts: list[str] | None = None

    @property
    def muted(self) -> bool:
        return any(hidden for _, hidden in self.stack)

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        attrs = dict(attributes)
        hidden = tag in IGNORED_TAGS or "hidden" in attrs or attrs.get("aria-hidden") == "true"
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.schema_parts = []
        if tag == "title":
            self.in_title = True
        if tag in BLOCK_TAGS and not self.muted:
            self.parts.append("\n")
        if tag not in VOID_TAGS:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attributes)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.schema_parts is not None:
            self.schema_blocks.append("".join(self.schema_parts))
            self.schema_parts = None
        if tag == "title":
            self.in_title = False
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if tag in BLOCK_TAGS and not self.muted:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.schema_parts is not None:
            self.schema_parts.append(data)
        if self.in_title:
            self.title_parts.append(data)
        elif not self.muted:
            self.parts.append(data)

    def visible_text(self) -> str:
        lines = [re.sub(r"[\t \r\f\v]+", " ", line).strip() for line in "".join(self.parts).split("\n")]
        return "\n".join(line for line in lines if line)


def html_text(source: str) -> str:
    parser = PostingHTMLParser()
    parser.feed(source)
    parser.close()
    return parser.visible_text()


def _job_schemas(value: object, depth: int = 0) -> list[dict]:
    if depth > 20:
        return []
    if isinstance(value, list):
        return [item for child in value for item in _job_schemas(child, depth + 1)]
    if not isinstance(value, dict):
        return []
    kind = value.get("@type", [])
    kinds = [kind] if isinstance(kind, str) else kind if isinstance(kind, list) else []
    found = [value] if "JobPosting" in kinds else []
    found.extend(_job_schemas(value.get("@graph"), depth + 1))
    return found


def posting_from_html(source: str) -> JobPosting:
    parser = PostingHTMLParser()
    parser.feed(source)
    parser.close()
    schemas: list[dict] = []
    for block in parser.schema_blocks:
        try:
            schemas.extend(_job_schemas(json.loads(block)))
        except (ValueError, RecursionError):
            continue  # Invalid site metadata must not prevent scanning visible text.
    if len(schemas) > 1:
        raise ValidationError("HTML contains multiple JobPosting records; provide a page for one job.")
    data = {"text": parser.visible_text(), "title": "".join(parser.title_parts).strip()[:300]}
    if schemas:
        schema = schemas[0]
        if isinstance(schema.get("title"), str):
            data["title"] = schema["title"][:300]
        description = schema.get("description")
        if isinstance(description, str) and description.strip():
            data["text"] = html_text(description)
        organization = schema.get("hiringOrganization")
        if isinstance(organization, dict):
            if isinstance(organization.get("name"), str):
                data["company_name"] = organization["name"]
            website = organization.get("sameAs", organization.get("url"))
            if isinstance(website, str):
                data["company_website"] = website
        if isinstance(schema.get("url"), str):
            data["url"] = schema["url"]
    return JobPosting.from_mapping(data)


def read_local_text(path: str | Path, max_bytes: int = MAX_DOCUMENT_BYTES) -> str:
    with Path(path).open("rb") as source:
        content = source.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValidationError(f"Input file exceeds the {max_bytes:,}-byte limit.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValidationError("Input file must use UTF-8 encoding.") from error


def read_posting(path: str | Path, format: str = "auto") -> JobPosting:
    path = Path(path)
    if format == "auto":
        format = "html" if path.suffix.lower() in {".html", ".htm"} else (
            "json" if path.suffix.lower() == ".json" else "text"
        )
    source = read_local_text(path)
    if format == "html":
        return posting_from_html(source)
    if format == "json":
        try:
            return JobPosting.from_mapping(json.loads(source))
        except json.JSONDecodeError as error:
            raise ValidationError(f"Posting JSON is invalid at line {error.lineno}: {error.msg}.") from error
    if format != "text":
        raise ValidationError("Posting format must be auto, text, html, or json.")
    if len(source) > MAX_TEXT_LENGTH:
        raise ValidationError(f"Job text must be at most {MAX_TEXT_LENGTH:,} characters.")
    return JobPosting.from_mapping({"text": source})
