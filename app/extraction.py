"""Conservative extraction of scholarship facts from discovered official pages.

Extracted records remain unverified. Every populated field is accompanied by
a snippet and the URL of the page from which it was captured.
"""
from dataclasses import dataclass, field
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.database import get_connection


MAX_RESPONSE_BYTES = 2_000_000
USER_AGENT = "ScholarPathAI/0.2 (+official scholarship detail extractor)"
FIELD_LABELS = {
    "deadline_text": ("application deadline", "deadline", "apply by", "closing date"),
    "funding_summary": ("funding", "scholarship value", "financial support", "tuition fee", "stipend"),
    "eligibility": ("eligibility", "who can apply", "requirements", "eligible applicants"),
    "study_level": ("degree level", "study level", "level of study", "programme level"),
    "nationality": ("nationality", "citizenship", "eligible countries", "country of residence"),
    "academic_requirements": ("academic requirements", "minimum marks", "minimum gpa", "grade requirement"),
    "age_limit": ("age limit", "age requirement"),
}


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


def _find_labeled_text(soup: BeautifulSoup, labels: tuple[str, ...]) -> str | None:
    """Find a concise nearby value for a visible label; never infer missing facts."""
    for node in soup.find_all(["p", "li", "td", "th", "dt", "dd", "h2", "h3", "h4"]):
        text = _clean(node.get_text(" ", strip=True))
        lowered = text.lower()
        for label in labels:
            match = re.search(rf"(?<!\\w){re.escape(label)}\\s*[:–—-]\\s*(.+)", text, re.I)
            if match:
                value = _clean(match.group(1))
                if value and len(value) <= 1200:
                    return value
            if lowered.rstrip(":") == label:
                sibling = node.find_next(["p", "li", "td", "dd"])
                if sibling:
                    value = _clean(sibling.get_text(" ", strip=True))
                    if value and value.lower() not in labels and len(value) <= 1200:
                        return value
    return None


def parse_scholarship_page(html: str, page_url: str) -> ExtractedPage | None:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()

    title_node = soup.find("h1") or soup.find("title")
    title = _clean(title_node.get_text(" ", strip=True)) if title_node else ""
    if not title:
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

    fields: dict[str, str] = {}
    evidence: list[tuple[str, str]] = []
    for field_name, labels in FIELD_LABELS.items():
        value = _find_labeled_text(soup, labels)
        if value:
            fields[field_name] = value[:1200]
            evidence.append((field_name, value[:1200]))

    criteria: list[tuple[str, str, str]] = []
    for field_name in ("eligibility", "study_level", "nationality", "academic_requirements", "age_limit"):
        if field_name in fields:
            criteria.append((field_name, field_name.replace("_", " ").title(), fields[field_name]))

    if description:
        evidence.append(("description", description))
    if not fields and not description:
        return None
    return ExtractedPage(title, description, provider, fields, criteria, evidence)


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


async def extract_candidate_details() -> list[dict]:
    """Visit unprocessed candidates and store evidence-backed, unverified records."""
    with get_connection() as connection:
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
            parsed = parse_scholarship_page(html, candidate["candidate_url"]) if html else None
            status = "failed" if error else ("insufficient_evidence" if parsed is None else "extracted")
            message = error or (None if parsed else "Page did not contain enough extractable scholarship information.")

            with get_connection() as connection:
                if parsed:
                    cursor = connection.execute(
                        """INSERT INTO scholarships
                           (source_id, title, provider_name, funding_summary, deadline_text,
                            status, source_record_url)
                           VALUES (?, ?, ?, ?, ?, 'unverified', ?)
                           ON CONFLICT(source_id, source_record_url) DO UPDATE SET
                               title = excluded.title,
                               provider_name = COALESCE(excluded.provider_name, scholarships.provider_name),
                               funding_summary = COALESCE(excluded.funding_summary, scholarships.funding_summary),
                               deadline_text = COALESCE(excluded.deadline_text, scholarships.deadline_text),
                               last_checked_at = CURRENT_TIMESTAMP,
                               updated_at = CURRENT_TIMESTAMP
                           RETURNING id""",
                        (candidate["source_id"], parsed.title[:300], parsed.provider_name,
                         parsed.fields.get("funding_summary"), parsed.fields.get("deadline_text"),
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
                               VALUES (?, ?, ?, ?, 1, ?)""",
                            (scholarship_id, criterion_type, label, requirement, candidate["candidate_url"]),
                        )
                    connection.execute(
                        "UPDATE discovery_candidates SET status = 'promoted' WHERE id = ?",
                        (candidate["id"],),
                    )
                connection.execute(
                    """INSERT INTO extraction_attempts (candidate_id, status, message)
                       VALUES (?, ?, ?)""",
                    (candidate["id"], status, message),
                )
            results.append({"candidate_id": candidate["id"], "title": candidate["candidate_title"],
                            "status": status, "message": message})
    return results
