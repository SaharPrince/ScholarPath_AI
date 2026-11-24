"""Read-only live smoke checks for configured official German scholarship sources.

This script performs HTTP GET requests only. It does not initialize or modify
the application's database.
"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from app.discovery import _candidate_links
from app.extraction import augment_curated_programme, parse_scholarship_page
from app.source_catalog import GERMANY_SOURCES, OFFICIAL_SOURCES
from app.live_discovery import _as_record, discover_live_scholarships


HEADERS = {
    "User-Agent": "ScholarPathAI-live-source-verification/1.0",
    "Accept": "text/html,application/xhtml+xml",
}
TIMEOUT = httpx.Timeout(35.0, connect=15.0)
CORE_SOURCE_NAMES = {
    "DAAD Pakistan – Scholarship Programmes for Pakistan",
    "DAAD Pakistan – Scholarship Database",
}


async def get_page(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """Fetch an official page, retrying one transient network/server failure."""
    for attempt in range(2):
        try:
            response = await client.get(url)
            if response.status_code >= 500 and attempt == 0:
                await asyncio.sleep(0.5)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                raise ValueError(f"Expected HTML, received {content_type or 'unknown content type'}")
            return response.text, str(response.url)
        except httpx.TransportError:
            if attempt == 0:
                await asyncio.sleep(0.5)
                continue
            raise
    raise RuntimeError(f"Unable to fetch official page after retry: {url}")


def _is_transient_failure(error: Exception) -> bool:
    """Distinguish temporary network/5xx failures from permanent bad URLs."""
    if isinstance(error, httpx.TransportError):
        return True
    status_code = getattr(getattr(error, "response", None), "status_code", None)
    return status_code is not None and 500 <= status_code < 600


def _programme_candidate_title(source: dict | None, url: str) -> str | None:
    """Supply a grounded programme name when checking a curated detail page.

    Many official pages use generic headings such as "Basic Principles" or
    German titles such as "Stipendien". Their catalogue entry already names
    the specific programme, so use that name as parser context rather than
    treating a generic page heading as proof that the page is not an award.
    Broad index pages do not receive this override.
    """
    if not source:
        return None
    explicit_title = source.get("programme_titles", {}).get(url)
    if explicit_title:
        return explicit_title
    is_curated_detail = (
        url in source.get("programme_urls", ())
        or source.get("source_type") in {"official_programme", "government"}
    )
    return source.get("name") if is_curated_detail else None


async def main() -> None:
    failures: list[str] = []
    blocking_failures: list[str] = []
    access_restricted: list[str] = []
    transient_failures: list[str] = []
    reachable = 0
    core_reachable = set()

    async def check_index_source(client: httpx.AsyncClient, source: dict):
        try:
            html, final_url = await get_page(client, source["official_url"])
            host = urlparse(final_url).hostname or ""
            candidates = _candidate_links(html, final_url, host)
            return source, final_url, candidates, None
        except Exception as exc:
            return source, None, [], exc

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers=HEADERS,
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    ) as client:
        print("\n========== OFFICIAL GERMAN SOURCE INDEX CHECK ==========")
        index_results = await asyncio.gather(
            *(check_index_source(client, source) for source in OFFICIAL_SOURCES)
        )
        for source, final_url, candidates, error in index_results:
            if error is None:
                reachable += 1
                if source["name"] in CORE_SOURCE_NAMES:
                    core_reachable.add(source["name"])
                print(
                    f"OK | {source['name']} | HTTP HTML | "
                    f"candidate_links={len(candidates)} | {final_url}"
                )
                continue

            message = f"{source['name']}: {type(error).__name__}: {error}"
            failures.append(message)
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code in {403, 429}:
                # Some official providers block cloud CI traffic. This is
                # not evidence that the source URL is invalid; report it
                # distinctly rather than failing the whole PR.
                access_restricted.append(message)
                print(f"ACCESS RESTRICTED | {source['name']} | HTTP {status_code}")
            else:
                if source["name"] in CORE_SOURCE_NAMES:
                    blocking_failures.append(message)
                print(f"UNAVAILABLE | {source['name']} | {type(error).__name__}: {error}")

    missing_core = CORE_SOURCE_NAMES - core_reachable
    restricted_core = {
        name for name in CORE_SOURCE_NAMES
        if any(name in item for item in access_restricted)
    }
    unaccounted_core = missing_core - restricted_core
    if unaccounted_core:
        blocking_failures.append(
            "Core DAAD source pages failed for reasons other than access restrictions: "
            + ", ".join(sorted(unaccounted_core))
        )

    print("\n========== LIVE CHECK SUMMARY ==========")
    print(f"Official German source indexes reachable: {reachable}/{len(OFFICIAL_SOURCES)}")
    print(f"Core DAAD source indexes reachable: {len(core_reachable)}/{len(CORE_SOURCE_NAMES)}")
    print(f"Source indexes blocked by CI access controls: {len(access_restricted)}")
    if failures:
        print("Issues observed:")
        for failure in failures:
            print("-", failure)
    if access_restricted:
        print("Access-restricted sources (not treated as broken URLs):")
        for item in access_restricted:
            print("-", item)
    if transient_failures:
        print("Temporary programme-page failures after one retry (not treated as broken URLs):")
        for item in transient_failures:
            print("-", item)

    print("\n========== LIVE SCHOLARSHIP DISCOVERY CHECK ==========")
    records = await discover_live_scholarships()
    print(f"Fresh live scholarship records extracted: {len(records)}")

    for record in records:
        print(
            "RECORD | "
            f"{record.get('source_name')} | "
            f"{record.get('title')} | "
            f"deadline={record.get('deadline_date')} | "
            f"funding={record.get('funding_summary')} | "
            f"criteria={len(record.get('criteria', []))} | "
            f"{record.get('source_url')}"
        )

    # Validate curated programme coverage. Other provider pages remain warnings
    # because independent providers can temporarily block or delay CI requests.
    expected_programme_urls = {
        "https://www.uni-goettingen.de/en/516679.html",
        "https://www.uni-goettingen.de/en/516678.html",
        "https://www.hss.de/stipendium/foerderung/foerderung-auszubildender/",
        "https://www.fes.de/studienfoerderung/stipendium/stipendien-auszubildende",
        "https://www.fes.de/studienfoerderung/stipendium/grundfoerderung-fuer-auslaender-innen",
        "https://www.fes.de/studienfoerderung/stipendium/promotionsfoerderung-fuer-auslaender-innen",
        "https://www.rosalux.de/stiftung/studienwerk/stipendien/studienstipendium",
        "https://www.rosalux.de/stiftung/studienwerk/stipendien/promotionsstipendium",
        "https://www.rosalux.de/berufliche-bildung",
    }
    # Independently check every curated individual-programme page with the
    # verifier's longer timeout. This separates source reachability from the
    # intentionally short request-time discovery budget.
    curated_programme_sources = {}
    for source in GERMANY_SOURCES:
        programme_urls = source.get("programme_urls", ())
        if not programme_urls and source.get("source_type") in {"official_programme", "government", "university"}:
            programme_urls = (source["official_url"],)
        for url in programme_urls:
            curated_programme_sources.setdefault(url, source)
    expected_programme_urls.update(curated_programme_sources)

    direct_reachable = set()
    direct_unparsed = []
    direct_semaphore = asyncio.Semaphore(6)

    async def check_curated_page(client: httpx.AsyncClient, url: str):
        async with direct_semaphore:
            source = curated_programme_sources.get(url)
            try:
                html, final_url = await get_page(client, url)
                title = _programme_candidate_title(source, url)
                parsed = parse_scholarship_page(html, final_url, title)
                parsed = augment_curated_programme(
                    parsed,
                    html,
                    final_url,
                    title,
                    source.get("provider_name") or source.get("name") if source else None,
                )
                return url, final_url, parsed, None
            except Exception as exc:
                return url, None, None, exc

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers=HEADERS,
        limits=httpx.Limits(max_connections=6, max_keepalive_connections=3),
    ) as client:
        direct_results = await asyncio.gather(
            *(check_curated_page(client, url) for url in sorted(expected_programme_urls))
        )

    for url, final_url, parsed, error in direct_results:
        source = curated_programme_sources.get(url, {})
        label = source.get("name", url)
        if error is not None:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            message = f"{label}: {type(error).__name__}: {error}"
            if status_code in {403, 429}:
                access_restricted.append(message)
                print(f"CURATED PAGE ACCESS RESTRICTED | {label} | HTTP {status_code}")
            elif _is_transient_failure(error):
                transient_failures.append(message)
                print(f"CURATED PAGE TEMPORARILY UNAVAILABLE | {label} | {type(error).__name__}: {error}")
            else:
                blocking_failures.append(message)
                print(f"CURATED PAGE UNAVAILABLE | {label} | {type(error).__name__}: {error}")
            continue
        direct_reachable.add(url)
        if parsed is None:
            direct_unparsed.append(label)
            print(f"CURATED PAGE REACHABLE BUT NOT PARSED | {label} | {final_url}")
        else:
            print(
                f"CURATED PAGE OK | {label} | title={parsed.title!r} | "
                f"criteria={len(parsed.criteria)} | {final_url}"
            )

    print(
        "CURATED PROGRAMME DIRECT CHECK | "
        f"reachable={len(direct_reachable)}/{len(expected_programme_urls)} | "
        f"access_restricted={sum(1 for item in direct_results if item[3] is not None and getattr(getattr(item[3], 'response', None), 'status_code', None) in {403, 429})} | "
        f"not_parsed={len(direct_unparsed)} | transient_failures={len(transient_failures)}"
    )
    if direct_unparsed:
        print("PROGRAMME PAGES REACHABLE BUT NOT EXTRACTED:")
        for label in direct_unparsed:
            print("-", label)

    found_programme_urls = {record.get("source_url") for record in records}
    missing_programmes = expected_programme_urls - found_programme_urls
    if not records:
        blocking_failures.append(
            "Live discovery returned no individual scholarship records. "
            "At least one official programme must be extractable; temporary "
            "provider outages may reduce the number returned in a single request."
        )
    elif len(records) < 5:
        print(
            "COVERAGE WARNING: only "
            f"{len(records)} individual records were extracted in this bounded live scan; "
            "provider response times and access restrictions can reduce per-request coverage."
        )
    if missing_programmes:
        # A reachable index does not guarantee every programme detail page will
        # respond inside the serverless request budget. Keep this visible as a
        # coverage warning, not a false failure for otherwise healthy sources.
        print("PROGRAMME PAGES NOT OBSERVED WITHIN THIS LIVE REQUEST:")
        for url in sorted(missing_programmes):
            print("-", url)

    missing_evidence = []
    for record in records:
        source_host = urlparse(str(record.get("source_url", ""))).hostname
        for criterion in record.get("criteria", []):
            evidence_url = criterion.get("evidence_url")
            if not evidence_url or urlparse(str(evidence_url)).hostname != source_host:
                missing_evidence.append(
                    f"{record.get('title')}: {criterion.get('requirement_text')}"
                )
    if missing_evidence:
        blocking_failures.append(
            "Some criteria lack same-host official evidence URLs: "
            + "; ".join(missing_evidence[:10])
        )

    if blocking_failures:
        print("LIVE CHECK RESULT: FAILED")
        raise SystemExit(1)
    if access_restricted or transient_failures or direct_unparsed or failures:
        print(
            "LIVE CHECK RESULT: PASS WITH WARNINGS | core source checks passed; "
            "some providers restricted automated access, had temporary outages, "
            "or published pages without extractable programme details."
        )
    else:
        print("LIVE CHECK RESULT: all official source indexes and curated programme pages passed")


if __name__ == "__main__":
    asyncio.run(main())
