"""Request-time scholarship discovery from official German provider pages.

No opportunity, candidate, extraction, or eligibility data is written to a database.
Only the curated source registry is persistent (as application code).
"""
import asyncio
import hashlib
import logging
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
logger = logging.getLogger(__name__)



_GENERIC_SOURCE_TITLE_MARKERS = (
    "welcome",
    "scholarship department",
    "scholarships & funding",
    "scholarships and funding",
    "funding opportunities from other organisations",
    "scholarships by target group",
    "scholarship providers",
    "scholarship database",
    "daad scholarships - an overview",
    "scholarships – an overview",
    "scholarships - an overview",
    "overview of scholarships",
    "overview of funding opportunities",
    "most important domestic scholarship programmes",
    "domestic scholarship programmes",
    "scholarship programmes by target group",
    "scholarship programmes for pakistan",
    "scholarships and other funding for international students",
    "study funding",
    "funding opportunities",
    "applying for a scholarship",
    "how to apply",
    "application process",
    "application procedure",
)


def _is_generic_source_title(record: dict) -> bool:
    """Identify broad provider/index titles, regardless of how the page was discovered."""
    title = " ".join(str(record.get("title") or "").casefold().split())
    if not title or title in {"scholarship", "scholarships", "funding", "welcome", "stipendium", "stipendien", "studienwerk", "studienförderung"}:
        return True
    return any(marker in title for marker in _GENERIC_SOURCE_TITLE_MARKERS)


def _has_actionable_eligibility(record: dict) -> bool:
    """Only promote pages that publish at least one real applicant condition."""
    return any(
        isinstance(item, dict)
        and str(item.get("requirement_text") or "").strip()
        and item.get("criterion_type") not in {"selection_process", "target_audience"}
        for item in record.get("criteria", [])
    )


def _promote_actionable_records(results: dict[str, dict], records_with_html) -> None:
    """Add records after both their main and linked eligibility pages are processed."""
    for record, _page_html in records_with_html:
        if _has_actionable_eligibility(record):
            results[record["source_url"]] = record


def _is_promotable_source_page(record: dict, source: dict) -> bool:
    """Prevent broad indexes and provider directories from becoming scholarships."""
    # Indexes and databases are discovery entry points, never individual
    # opportunities. Government and university sources may also publish a
    # specific named scholarship on their own programme pages, so assess the
    # extracted page title instead of rejecting those source types wholesale.
    if (
        source.get("source_type") in {"official_index", "official_database"}
        and record.get("source_url") == source.get("official_url")
    ):
        return False
    return not _is_generic_source_title(record)


def _opportunity_id(url: str) -> int:
    """Stable, non-persistent identifier suitable for browser detail links."""
    return int(hashlib.sha256(url.encode("utf-8")).hexdigest()[:12], 16)



def _should_merge_source_eligibility(record: dict, source_url: str) -> bool:
    """Apply source-level eligibility pages only to the source's own programme."""
    return record.get("source_url") == source_url


def _source_candidate_title(source: dict, url: str) -> str:
    """Use a specific, source-authored title for a curated programme URL."""
    title = source.get("programme_titles", {}).get(url)
    return str(title or source["name"])


def _source_page_urls(source: dict) -> list[str]:
    """Return root/index pages plus explicitly curated same-host programmes."""
    source_url = source["official_url"]
    source_host = _normalized_host(source_url)
    base_urls = _daad_database_page_urls(source_url)
    if "scholarship-database" in source_url:
        base_urls = base_urls[:MAX_DAAD_INDEX_PAGES]
    programme_urls = [
        url for url in source.get("programme_urls", ())
        if source_host and _normalized_host(url) == source_host
    ]
    return list(dict.fromkeys([*programme_urls, *base_urls]))


def _eligibility_links(html: str, page_url: str, limit: int = 3) -> list[str]:
    """Find same-site official pages likely to contain programme requirements."""
    soup = BeautifulSoup(html, "html.parser")
    base = urlparse(page_url)
    keywords = (
        "eligibility", "eligible", "requirements", "who can apply",
        "application criteria", "selection criteria", "qualifications",
        "language requirements", "admission requirements",
        "voraussetzungen", "bewerbungsvoraussetzungen", "wen suchen wir",
        "wen-suchen-wir", "wer kann sich bewerben", "scholarship for studies",
    )
    found: list[str] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        label = " ".join(link.get_text(" ", strip=True).casefold().split())
        href = link.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        target = urljoin(page_url, href)
        searchable_link = f"{label} {href}".casefold()
        if not any(word in searchable_link for word in keywords):
            continue
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
        "provider_name": (source.get("provider_name") or source["name"]) if source.get("source_type") in {"official_programme", "government", "university"} else (parsed.provider_name or source.get("provider_name") or source["name"]),
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
                logger.warning(
                    "Official source page unavailable: source=%s url=%s error=%s",
                    source["name"],
                    url,
                    error or "no response body",
                )
                return None, [], None
            successful_pages += 1
            parsed = parse_scholarship_page(html, url, candidate_title)
            host = _normalized_host(url)
            links = _candidate_links(html, url, host) if host else []
            return (_as_record(parsed, source, url) if parsed else None), links, html

        async def inspect_source(source: dict):
            source_url = source["official_url"]
            index_urls = _source_page_urls(source)
            eligibility_urls = list(source.get("eligibility_urls", ()))

            async def fetch_eligibility_pages():
                return await asyncio.gather(
                    *(fetch(url) for url in eligibility_urls),
                    return_exceptions=True,
                )

            async def enrich_records(records_with_html):
                # Batch secondary requirements fetches. Awaiting them inside the
                # index-page completion loop let one slow provider delay every
                # other completed programme in a serverless request.
                requests = []
                for record, page_html in records_with_html:
                    if page_html and not record["criteria"]:
                        requests.extend(
                            (record, url)
                            for url in _eligibility_links(page_html, record["source_url"])
                        )
                if not requests:
                    return
                pages = await asyncio.gather(
                    *(fetch(url) for _record, url in requests),
                    return_exceptions=True,
                )
                for (record, requirements_url), page_result in zip(requests, pages):
                    if isinstance(page_result, Exception):
                        logger.warning(
                            "Linked eligibility fetch failed: source=%s url=%s error=%s",
                            record["source_name"],
                            requirements_url,
                            page_result,
                        )
                        continue
                    requirements_html, error = page_result
                    if requirements_html:
                        extracted = extract_criteria_from_html(requirements_html, requirements_url)
                        _merge_linked_criteria(record, extracted, requirements_url)
                    else:
                        logger.warning(
                            "Linked eligibility page unavailable: source=%s url=%s error=%s",
                            record["source_name"],
                            requirements_url,
                            error or "no response body",
                        )

            eligibility_task = asyncio.create_task(fetch_eligibility_pages())
            index_tasks = [
                asyncio.create_task(
                    inspect_page(source, url, _source_candidate_title(source, url))
                )
                for url in index_urls
            ]
            candidate_urls: dict[str, str] = {}
            root_records: list[tuple[dict, str | None]] = []
            programme_records: list[tuple[dict, str | None]] = []
            detail_task: asyncio.Task | None = None

            async def inspect_details(detail_items: list[tuple[str, str]]) -> None:
                if not detail_items:
                    return
                details = await asyncio.gather(
                    *(inspect_page(source, url, title) for url, title in detail_items),
                    return_exceptions=True,
                )
                detail_records = []
                for item in details:
                    if isinstance(item, Exception):
                        logger.warning(
                            "Official programme detail fetch failed: source=%s error=%s",
                            source["name"],
                            item,
                        )
                        continue
                    record, _links, detail_html = item
                    if record and not _is_generic_source_title(record):
                        detail_records.append((record, detail_html))
                        if _has_actionable_eligibility(record):
                            results[record["source_url"]] = record
                await enrich_records(detail_records)
                for record, _detail_html in detail_records:
                    if _has_actionable_eligibility(record):
                        results[record["source_url"]] = record

            try:
                # Consume index pages as soon as each one completes. A slow root
                # page must not hide faster curated programme pages when the
                # overall serverless discovery budget expires.
                for completed in asyncio.as_completed(index_tasks):
                    try:
                        item = await completed
                    except Exception:
                        logger.exception("Official index page task failed: source=%s", source["name"])
                        continue
                    record, links, page_html = item
                    if record and _is_promotable_source_page(record, source):
                        if _should_merge_source_eligibility(record, source_url):
                            # Source-level eligibility belongs only to the root
                            # programme. Enrich it after the parallel fetch ends,
                            # without blocking direct programme records.
                            root_records.append((record, page_html))
                        else:
                            programme_records.append((record, page_html))
                            if _has_actionable_eligibility(record):
                                results[record["source_url"]] = record
                    for url, title in links:
                        candidate_urls.setdefault(url, title)

                # Candidate detail pages and curated eligibility pages are
                # independent requests. Start both phases together rather than
                # waiting for one network round trip before starting the next.
                detail_limit = 1 if source.get("programme_urls") else MAX_CANDIDATES_PER_SOURCE
                detail_items = list(candidate_urls.items())[:detail_limit]
                if detail_items:
                    detail_task = asyncio.create_task(inspect_details(detail_items))

                eligibility_results, _ = await asyncio.gather(
                    eligibility_task,
                    enrich_records(programme_records),
                )
                _promote_actionable_records(results, programme_records)
                eligibility_pages: dict[str, str] = {}
                for url, page_result in zip(eligibility_urls, eligibility_results):
                    if isinstance(page_result, Exception):
                        logger.warning(
                            "Curated eligibility page fetch failed: source=%s url=%s error=%s",
                            source["name"],
                            url,
                            page_result,
                        )
                        continue
                    requirements_html, error = page_result
                    if requirements_html:
                        eligibility_pages[url] = requirements_html
                    else:
                        logger.warning(
                            "Curated eligibility page unavailable: source=%s url=%s error=%s",
                            source["name"],
                            url,
                            error or "no response body",
                        )

                root_followups = []
                for record, page_html in root_records:
                    for requirements_url, requirements_html in eligibility_pages.items():
                        extracted = extract_criteria_from_html(requirements_html, requirements_url)
                        _merge_linked_criteria(record, extracted, requirements_url)
                    if page_html and not record["criteria"]:
                        root_followups.append((record, page_html))
                    if _has_actionable_eligibility(record):
                        results[record["source_url"]] = record
                await enrich_records(root_followups)
                for record, _page_html in root_followups:
                    if _has_actionable_eligibility(record):
                        results[record["source_url"]] = record

                if detail_task is not None:
                    await detail_task
            finally:
                for task in index_tasks:
                    if not task.done():
                        task.cancel()
                if not eligibility_task.done():
                    eligibility_task.cancel()
                if detail_task is not None and not detail_task.done():
                    detail_task.cancel()
                pending_tasks = [
                    task for task in (eligibility_task, detail_task)
                    if task is not None and not task.done()
                ]
                if pending_tasks:
                    await asyncio.gather(*pending_tasks, return_exceptions=True)


        async def run_source_group(sources: list[dict], timeout: float) -> None:
            if not sources or timeout <= 0:
                return
            tasks = [
                asyncio.create_task(inspect_source(dict(source)))
                for source in sources
            ]
            done, pending = await asyncio.wait(
                tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                try:
                    task.result()
                except Exception:
                    logger.exception("Official source scan failed")

        # Prioritize curated individual programme pages and the main
        # scholarship foundations. Their named awards are more actionable than
        # broad indexes, while the remaining providers still receive a bounded
        # portion of the same live request budget.
        priority_names = {
            "Heinrich Böll Foundation – Scholarships",
            "Konrad Adenauer Foundation – International Scholarships",
        }
        priority_sources = [
            source for source in GERMANY_SOURCES
            if source.get("programme_urls") or source["name"] in priority_names
        ]
        secondary_sources = [
            source for source in GERMANY_SOURCES
            if source not in priority_sources
        ]
        loop = asyncio.get_running_loop()
        # Scan both groups inside the same bounded request window. Running
        # the secondary group only after the priority budget expired left it
        # almost no time on slow providers and made results depend on ordering.
        await asyncio.gather(
            run_source_group(priority_sources, DISCOVERY_BUDGET_SECONDS),
            run_source_group(secondary_sources, DISCOVERY_BUDGET_SECONDS),
        )
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
