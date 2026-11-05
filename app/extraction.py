"""Conservative extraction of individual scholarship opportunities.

A page is only promoted when it looks like a specific opportunity page and
contains at least one scholarship-specific fact. Extracted records remain
unverified. Every populated fact is accompanied by its source evidence.
"""
from dataclasses import dataclass, field
from datetime import datetime
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.database import get_connection


MAX_RESPONSE_BYTES = 2_000_000
USER_AGENT = "ScholarPathAI/0.3 (+official scholarship detail extractor)"
FIELD_LABELS = {
    "deadline_text": ("application deadline", "application closes", "deadline", "apply by", "closing date"),
    "funding_summary": ("funding", "scholarship value", "financial support", "tuition fee", "stipend"),
    "eligibility": ("eligibility", "who can apply", "eligible applicants"),
    "study_level": ("degree level", "study level", "level of study", "programme level", "program level"),
    "nationality": ("nationality", "citizenship", "eligible countries", "country of residence"),
    "academic_requirements": ("academic requirements", "minimum marks", "minimum gpa", "grade requirement"),
    "age_limit": ("age limit", "age requirement"),
}
GENERIC_PAGE_TERMS = (
    "scholarship database", "funding partners", "application guide",
    "step by step guide", "scholarship applicants", "find funding",
    "scholarship programmes for", "scholarship programs for",
    "all scholarships", "scholarship index",
    "promoting mutual understanding through exchanges",
)
OPPORTUNITY_TERMS = ("scholarship", "fellowship", "grant", "studentship", "award", "programme", "program", "ugrad", "fulbright", "humphrey", "flta", "epos")
DATE_PATTERN = re.compile(
    r"(?i)\b(?:\d{1,2}[./ -](?:\d{1,2}|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[./, -]*\d{2,4}|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{4})\b"
)
ROLLING_PATTERN = re.compile(r"(?i)\b(rolling basis|no fixed deadline|applications? accepted throughout the year|open year[- ]round)\b")


@dataclass
class ExtractedPage:
    title: str
    description: str | None
    provider_name: str | None
    fields: dict[str, str] = field(default_factory=dict)
    criteria: list[tuple[str, str, str]] = field(default_factory=list)
    evidence: list[tuple[str, str]] = field(default_factory=list)


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _parse_deadline_date(value: str | None) -> str | None:
    """Normalize an explicitly extracted English deadline date to ISO format."""
    if not value:
        return None
    match = DATE_PATTERN.search(value)
    if not match:
        return None
    candidate = match.group(0).strip()
    for date_format in (
        "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y",
        "%d %B %Y", "%d %b %Y", "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(candidate, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _is_generic_title(value: str) -> bool:
    lowered = _clean(value).lower()
    return not lowered or any(term in lowered for term in GENERIC_PAGE_TERMS)


def _is_opportunity(candidate_title: str, page_title: str, page_url: str, body_text: str) -> bool:
    candidate = _clean(candidate_title)
    title = _clean(page_title)
    path = urlparse(page_url).path.lower()
    if _is_generic_title(candidate) or _is_generic_title(title):
        # A specific candidate link title can override generic site-wide H1/title metadata.
        if not candidate or _is_generic_title(candidate):
            return False
    searchable = f"{candidate} {title} {path}".lower()
    has_opportunity_identity = any(term in searchable for term in OPPORTUNITY_TERMS) or "/scholarships/" in path
    has_specific_fact = any(term in body_text.lower() for term in (
        "eligibility", "who can apply", "application deadline", "apply by",
        "funding", "stipend", "tuition", "minimum gpa", "academic requirement",
        "application period", "applications open",
    ))
    return has_opportunity_identity and has_specific_fact


def _find_labeled_text(soup: BeautifulSoup, labels: tuple[str, ...], field_name: str) -> str | None:
    """Read only explicit label/value pairs; deadlines additionally need a date or rolling rule."""
    for node in soup.find_all(["p", "li", "td", "th", "dt", "dd"]):
        text = _clean(node.get_text(" ", strip=True))
        for label in labels:
            match = re.search(rf"(?<!\w){re.escape(label)}\s*[:–—-]\s*(.+)", text, re.I)
            value = _clean(match.group(1)) if match else ""
            if not value and _clean(text).lower().rstrip(":") == label:
                sibling = node.find_next(["p", "li", "td", "dd"])
                value = _clean(sibling.get_text(" ", strip=True)) if sibling else ""
            if not value or len(value) > 1200:
                continue
            if field_name == "deadline_text" and not (DATE_PATTERN.search(value) or ROLLING_PATTERN.search(value)):
                continue
            return value
    return None


def parse_scholarship_page(html: str, page_url: str, candidate_title: str | None = None) -> ExtractedPage | None:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()

    h1 = soup.find("h1")
    title_node = h1 or soup.find("title")
    page_title = _clean(title_node.get_text(" ", strip=True)) if title_node else ""
    candidate_title = _clean(candidate_title or "")
    title = candidate_title if candidate_title and _is_generic_title(page_title) else (page_title or candidate_title)
    if not title or _is_generic_title(title):
        return None

    body_text = _clean(soup.get_text(" ", strip=True))
    fields: dict[str, str] = {}
    evidence: list[tuple[str, str]] = []
    for field_name, labels in FIELD_LABELS.items():
        value = _find_labeled_text(soup, labels, field_name)
        if value:
            fields[field_name] = value[:1200]
            evidence.append((field_name, value[:1200]))

    if not _is_opportunity(candidate_title or title, page_title or title, page_url, body_text):
        return None
    if not fields:
        return None

    description = None
    description_node = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if description_node:
        description = _clean(str(description_node.get("content", ""))) or None
    if not description:
        first_paragraph = soup.find("p")
        if first_paragraph:
            candidate = _clean(first_paragraph.get_text(" ", strip=True))
            if candidate and len(candidate) >= 35:
                description = candidate[:1200]

    provider = None
    site_node = soup.find("meta", attrs={"property": "og:site_name"})
    if site_node:
        provider = _clean(str(site_node.get("content", ""))) or None

    criteria: list[tuple[str, str, str]] = []
    for field_name in ("eligibility", "study_level", "nationality", "academic_requirements", "age_limit"):
        if field_name in fields:
            criteria.append((field_name, field_name.replace("_", " ").title(), fields[field_name]))

    if description:
        evidence.append(("description", description))
    return ExtractedPage(title[:300], description, provider, fields, criteria, evidence)


async def _fetch_page(client: httpx.AsyncClient, url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None, "Candidate URL is not a safe HTTPS URL."
    try:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                return None, f"HTTP {response.status_code}"
            if urlparse(str(response.url)).hostname != parsed.hostname:
                return None, "Cross-domain redirect was not followed."
            if "text/html" not in response.headers.get("content-type", "").lower():
                return None, "Candidate did not return HTML."
            length = response.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
                return None, "Page exceeds the response size limit."
            chunks = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    return None, "Page exceeded the response size limit."
                chunks.append(chunk)
            return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace"), None
    except httpx.TimeoutException:
        return None, "Request timed out."
    except httpx.HTTPError as exc:
        return None, f"HTTP request failed: {type(exc).__name__}"


async def extract_candidate_details(reprocess: bool = False) -> list[dict]:
    """Visit candidates; optionally reprocess old attempts and replace prior extracted rows."""
    with get_connection() as connection:
        if reprocess:
            # Preserve historical rows and evidence. Re-run candidates and update
            # matching records in place; rejected pages remain auditable.
            connection.execute("DELETE FROM extraction_attempts")
            connection.execute("UPDATE discovery_candidates SET status = 'candidate'")
        candidates = [dict(row) for row in connection.execute(
            """SELECT c.id, c.source_id, c.title AS candidate_title, c.candidate_url
               FROM discovery_candidates c
               WHERE c.status = 'candidate'
                 AND NOT EXISTS (
                     SELECT 1 FROM extraction_attempts a
                     WHERE a.candidate_id = c.id
                 )
               ORDER BY c.id"""
        ).fetchall()]

    timeout = httpx.Timeout(15.0, connect=6.0)
    limits = httpx.Limits(max_connections=3, max_keepalive_connections=2)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    results = []
    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers,
                                 follow_redirects=False) as client:
        for candidate in candidates:
            html, error = await _fetch_page(client, candidate["candidate_url"])
            parsed = parse_scholarship_page(html, candidate["candidate_url"], candidate["candidate_title"]) if html else None
            status = "failed" if error else ("insufficient_evidence" if parsed is None else "extracted")
            message = error or (None if parsed else "Page was not classified as a specific opportunity or lacked explicit scholarship facts.")

            with get_connection() as connection:
                if parsed:
                    cursor = connection.execute(
                        """INSERT INTO scholarships
                           (source_id, title, provider_name, funding_summary, deadline_text, deadline_date,
                            status, source_record_url)
                           VALUES (?, ?, ?, ?, ?, ?, 'unverified', ?)
                           ON CONFLICT(source_id, source_record_url) DO UPDATE SET
                               title = excluded.title,
                               provider_name = excluded.provider_name,
                               funding_summary = excluded.funding_summary,
                               deadline_text = excluded.deadline_text,
                               deadline_date = excluded.deadline_date,
                               status = 'unverified',
                               last_checked_at = CURRENT_TIMESTAMP,
                               updated_at = CURRENT_TIMESTAMP
                           RETURNING id""",
                        (candidate["source_id"], parsed.title, parsed.provider_name,
                         parsed.fields.get("funding_summary"), parsed.fields.get("deadline_text"),
                         _parse_deadline_date(parsed.fields.get("deadline_text")),
                         candidate["candidate_url"]),
                    ).fetchone()
                    scholarship_id = cursor["id"]
                    connection.execute("DELETE FROM scholarship_evidence WHERE scholarship_id = ?", (scholarship_id,))
                    connection.execute("DELETE FROM eligibility_criteria WHERE scholarship_id = ?", (scholarship_id,))
                    for field_name, snippet in parsed.evidence:
                        connection.execute(
                            """INSERT INTO scholarship_evidence
                               (scholarship_id, field_name, evidence_text, evidence_url)
                               VALUES (?, ?, ?, ?)""",
                            (scholarship_id, field_name, snippet, candidate["candidate_url"]),
                        )
                    for criterion_type, label, requirement in parsed.criteria:
                        connection.execute(
                            """INSERT INTO eligibility_criteria
                               (scholarship_id, criterion_type, criterion_label,
                                requirement_text, is_mandatory, evidence_url)
                               VALUES (?, ?, ?, ?, 0, ?)""",
                            (scholarship_id, criterion_type, label, requirement, candidate["candidate_url"]),
                        )
                    connection.execute("UPDATE discovery_candidates SET status = 'promoted' WHERE id = ?", (candidate["id"],))
                elif not error:
                    # A successfully fetched page that lacks opportunity evidence
                    # is rejected. A network/HTTP failure must not erase prior facts.
                    rejected_row = connection.execute(
                        """SELECT id FROM scholarships
                           WHERE source_id = ? AND source_record_url = ?""",
                        (candidate["source_id"], candidate["candidate_url"]),
                    ).fetchone()
                    if rejected_row:
                        scholarship_id = rejected_row["id"]
                        connection.execute(
                            """UPDATE scholarships SET status = 'rejected',
                               provider_name = NULL, country = NULL, study_destination = NULL,
                               funding_summary = NULL, application_url = NULL,
                               deadline_text = NULL, deadline_date = NULL,
                               last_checked_at = CURRENT_TIMESTAMP,
                               updated_at = CURRENT_TIMESTAMP
                               WHERE id = ?""",
                            (scholarship_id,),
                        )
                        connection.execute(
                            "DELETE FROM scholarship_evidence WHERE scholarship_id = ?",
                            (scholarship_id,),
                        )
                        connection.execute(
                            "DELETE FROM eligibility_criteria WHERE scholarship_id = ?",
                            (scholarship_id,),
                        )
                    connection.execute("UPDATE discovery_candidates SET status = 'reviewed' WHERE id = ?", (candidate["id"],))
                connection.execute(
                    """INSERT INTO extraction_attempts (candidate_id, status, message)
                       VALUES (?, ?, ?)""",
                    (candidate["id"], status, message),
                )
            results.append({"candidate_id": candidate["id"], "title": candidate["candidate_title"],
                            "status": status, "message": message})
    return results
