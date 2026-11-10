"""Request-time scholarship discovery from official German provider pages.

No opportunity, candidate, extraction, or eligibility data is written to a database.
Only the curated source registry is persistent (as application code).
"""
import asyncio
import hashlib
from urllib.parse import urlparse

import httpx

from app.discovery import _candidate_links, _daad_database_page_urls, _normalized_host
from app.extraction import (
    USER_AGENT,
    _fetch_page,
    _is_mandatory_criterion,
    _parse_deadline_date,
    parse_scholarship_page,
)
from app.source_catalog import GERMANY_SOURCES


MAX_CANDIDATES_PER_SOURCE = 2
MAX_LIVE_RESULTS = 100
REQUEST_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
REQUEST_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)


def _opportunity_id(url: str) -> int:
    """Stable, non-persistent identifier suitable for browser detail links."""
    return int(hashlib.sha256(url.encode("utf-8")).hexdigest()[:12], 16)


def _as_record(parsed, source: dict, url: str) -> dict:
    fields = parsed.fields
    criteria = [
        {
            "id": f"{_opportunity_id(url)}-{index}",
            "criterion_type": kind,
            "criterion_label": label,
            "requirement_text": requirement,
            "is_mandatory": _is_mandatory_criterion(kind, requirement),
            "evidence_url": parsed.criteria_sources.get((kind, label, requirement), url),
        }
        for index, (kind, label, requirement) in enumerate(parsed.criteria)
    ]
    evidence = [
        {
            "field_name": name,
            "evidence_text": value,
            "evidence_url": parsed.evidence_sources.get((name, value), url),
        }
        for name, value in parsed.evidence
    ]
    return {
        "id": _opportunity_id(url),
        "title": parsed.title,
        "provider_name": parsed.provider_name,
        "country": "Germany",
        "study_destination": fields.get("study_destination") or "Germany",
        "funding_summary": fields.get("funding_summary"),
        "application_url": fields.get("application_url"),
        "deadline_text": fields.get("deadline_text"),
        "deadline_date": _parse_deadline_date(fields.get("deadline_text")),
        "status": "unverified",
        "application_status": parsed.application_status,
        "applicant_category": parsed.applicant_category,
        "source_name": source["name"],
        "source_url": url,
        "criteria": criteria,
        "evidence": evidence,
        "last_checked_at": None,
    }


async def discover_live_scholarships() -> list[dict]:
    """Fetch current official source pages and extract specific opportunities."""
    semaphore = asyncio.Semaphore(20)
    results: dict[str, dict] = {}

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        limits=REQUEST_LIMITS,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        follow_redirects=False,
    ) as client:

        async def fetch(url: str):
            async with semaphore:
                return await _fetch_page(client, url)

        async def inspect_page(source: dict, url: str, candidate_title: str | None = None):
            html, error = await fetch(url)
            if not html:
                return None, []
            parsed = parse_scholarship_page(html, url, candidate_title)
            host = _normalized_host(url)
            links = _candidate_links(html, url, host) if host else []
            return ( _as_record(parsed, source, url) if parsed else None ), links

        async def inspect_source(source: dict):
            source_url = source["official_url"]
            index_urls = _daad_database_page_urls(source_url)
            # DAAD Pakistan publishes a paginated scholarship database. Other
            # providers are checked from their official landing/index page.
            index_urls = index_urls[:17]
            index_results = await asyncio.gather(
                *(inspect_page(source, url, source["name"]) for url in index_urls),
                return_exceptions=True,
            )
            candidate_urls: dict[str, str] = {}
            for item in index_results:
                if isinstance(item, Exception):
                    continue
                record, links = item
                if record:
                    results[record["source_url"]] = record
                for url, title in links:
                    candidate_urls.setdefault(url, title)
            detail_items = list(candidate_urls.items())[:MAX_CANDIDATES_PER_SOURCE]
            if detail_items:
                details = await asyncio.gather(
                    *(inspect_page(source, url, title) for url, title in detail_items),
                    return_exceptions=True,
                )
                for item in details:
                    if isinstance(item, Exception):
                        continue
                    record, _ = item
                    if record:
                        results[record["source_url"]] = record

        await asyncio.wait_for(
            asyncio.gather(
                *(inspect_source(dict(source)) for source in GERMANY_SOURCES),
                return_exceptions=True,
            ),
            timeout=9.0,
        )

    ordered = sorted(
        results.values(),
        key=lambda item: (
            item["application_status"] == "closed",
            item["deadline_date"] is None,
            item["deadline_date"] or "9999-12-31",
            item["title"].casefold(),
        ),
    )
    return ordered[:MAX_LIVE_RESULTS]
