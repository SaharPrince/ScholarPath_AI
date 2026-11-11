"""Request-time scholarship discovery from official German provider pages.

No opportunity, candidate, extraction, or eligibility data is written to a database.
Only the curated source registry is persistent (as application code).
"""
import asyncio
import hashlib
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import httpx

from app.discovery import _candidate_links, _daad_database_page_urls, _normalized_host
from app.extraction import (
    USER_AGENT,
    _fetch_page,
    extract_criteria_from_html,
    _is_mandatory_criterion,
    _parse_deadline_date,
    parse_scholarship_page,
)
from app.source_catalog import GERMANY_SOURCES


MAX_CANDIDATES_PER_SOURCE = 3
MAX_LIVE_RESULTS = 100
# Keep each source request short enough to return partial results within
# common serverless execution limits. Slow sources must not block all others.
REQUEST_TIMEOUT = httpx.Timeout(3.5, connect=1.5)
DISCOVERY_BUDGET_SECONDS = 8.0
MAX_DAAD_INDEX_PAGES = 4
REQUEST_LIMITS = httpx.Limits(max_connections=40, max_keepalive_connections=20)



_GENERIC_SOURCE_TITLE_MARKERS = (
    "welcome",
    "studienwerk",
    "scholarship department",
    "stipendium",
    "stipendien",
    "studienförderung",
    "funding opportunities from other organisations",
    "scholarships by target group",
    "scholarship providers",
    "scholarship database",
    "scholarship programmes for pakistan",
    "scholarships and other funding for international students",
    "study funding",
    "funding opportunities",
)


def _is_promotable_source_page(record: dict, source: dict) -> bool:
    """Prevent broad indexes and provider directories from becoming scholarships."""
    if source.get("source_type") in {
        "official_index", "official_database", "government", "university"
    }:
        return False
    title = " ".join(str(record.get("title") or "").casefold().split())
    if not title or title in {"scholarship", "scholarships", "funding", "welcome"}:
        return False
    if any(marker in title for marker in _GENERIC_SOURCE_TITLE_MARKERS):
        return False
    return True


def _opportunity_id(url: str) -> int:
    """Stable, non-persistent identifier suitable for browser detail links."""
    return int(hashlib.sha256(url.encode("utf-8")).hexdigest()[:12], 16)



def _eligibility_links(html: str, page_url: str, limit: int = 3) -> list[str]:
    """Find same-site official pages likely to contain programme requirements."""
    soup = BeautifulSoup(html, "html.parser")
    base = urlparse(page_url)
    keywords = (
        "eligibility", "eligible", "requirements", "who can apply",
        "application criteria", "selection criteria", "qualifications",
        "language requirements", "admission requirements",
        "voraussetzungen", "bewerbungsvoraussetzungen", "wen suchen wir",
        "wer kann sich bewerben", "scholarship for studies",
    )
    found: list[str] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        label = " ".join(link.get_text(" ", strip=True).casefold().split())
        href = link.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        if not any(word in label for word in keywords):
            continue
        target = urljoin(page_url, href)
        parsed = urlparse(target)
        if parsed.scheme != "https" or parsed.hostname != base.hostname:
            continue
        normalized = parsed._replace(fragment="").geturl()
        if normalized == page_url or normalized in seen:
            continue
        found.append(normalized)
        seen.add(normalized)
        if len(found) >= limit:
            break
    return found


def _merge_linked_criteria(record: dict, criteria: list[tuple[str, str, str]], evidence_url: str) -> None:
    """Attach criteria scraped from a related official page, with its own evidence URL."""
    existing = {item["requirement_text"].casefold() for item in record["criteria"]}
    for kind, label, requirement in criteria:
        key = requirement.casefold()
        if key in existing:
            continue
        index = len(record["criteria"])
        record["criteria"].append({
            "id": f'{record["id"]}-{index}',
            "criterion_type": kind,
            "criterion_label": label,
            "requirement_text": requirement,
            "is_mandatory": _is_mandatory_criterion(kind, requirement),
            "evidence_url": evidence_url,
        })
        existing.add(key)
    if criteria:
        record["evidence"].append({
            "field_name": "additional_eligibility",
            "evidence_text": f"Additional eligibility details scraped from {evidence_url}",
            "evidence_url": evidence_url,
        })


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
    semaphore = asyncio.Semaphore(40)
    results: dict[str, dict] = {}
    successful_pages = 0

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
            nonlocal successful_pages
            html, error = await fetch(url)
            if not html:
                return None, [], None
            successful_pages += 1
            parsed = parse_scholarship_page(html, url, candidate_title)
            host = _normalized_host(url)
            links = _candidate_links(html, url, host) if host else []
            return (_as_record(parsed, source, url) if parsed else None), links, html

        async def inspect_source(source: dict):
            source_url = source["official_url"]
            index_urls = _daad_database_page_urls(source_url)
            # Check only the first few DAAD result pages per student request.
            # Crawling all 17 pages on every request caused avoidable timeouts;
            # subsequent searches will fetch fresh data again.
            index_urls = index_urls[:MAX_DAAD_INDEX_PAGES]
            index_results = await asyncio.gather(
                *(inspect_page(source, url, source["name"]) for url in index_urls),
                return_exceptions=True,
            )
            candidate_urls: dict[str, str] = {}
            for item in index_results:
                if isinstance(item, Exception):
                    continue
                record, links, _html = item
                if record and _is_promotable_source_page(record, source):
                    # Programme landing pages frequently link to a separate
                    # eligibility page. Enrich root-page records too, not only
                    # discovered detail links, or providers such as HSS lose
                    # their actual applicant conditions.
                    if _html and not record["criteria"]:
                        requirements_urls = _eligibility_links(_html, record["source_url"])
                        pages = await asyncio.gather(
                            *(fetch(requirements_url) for requirements_url in requirements_urls),
                            return_exceptions=True,
                        )
                        for requirements_url, page_result in zip(requirements_urls, pages):
                            if isinstance(page_result, Exception):
                                continue
                            requirements_html, _error = page_result
                            if requirements_html:
                                extracted = extract_criteria_from_html(requirements_html)
                                _merge_linked_criteria(record, extracted, requirements_url)
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
                    record, _links, detail_html = item
                    if record:
                        # Follow a few clearly labelled same-domain requirements
                        # pages when the programme page contains no eligibility.
                        if detail_html and not record["criteria"]:
                            requirements_urls = _eligibility_links(detail_html, record["source_url"])
                            pages = await asyncio.gather(
                                *(fetch(requirements_url) for requirements_url in requirements_urls),
                                return_exceptions=True,
                            )
                            for requirements_url, page_result in zip(requirements_urls, pages):
                                if isinstance(page_result, Exception):
                                    continue
                                requirements_html, _error = page_result
                                if requirements_html:
                                    extracted = extract_criteria_from_html(requirements_html)
                                    _merge_linked_criteria(record, extracted, requirements_url)
                        results[record["source_url"]] = record

        # Return opportunities from sources that respond within the request
        # budget. One slow provider must never discard results from every other
        # official provider.
        tasks = [
            asyncio.create_task(inspect_source(dict(source)))
            for source in GERMANY_SOURCES
        ]
        done, pending = await asyncio.wait(
            tasks,
            timeout=DISCOVERY_BUDGET_SECONDS,
            return_when=asyncio.ALL_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        # Consume exceptions from completed source tasks; source failures are
        # isolated and do not prevent partial live results from being returned.
        for task in done:
            try:
                task.result()
            except Exception:
                continue
        if successful_pages == 0:
            raise RuntimeError("No official scholarship source pages responded")

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
