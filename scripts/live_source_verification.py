"""Read-only live smoke checks for configured official scholarship sources.

This script performs HTTP GET requests only. It does not initialize or modify
the application's SQLite database.
"""
import asyncio
from urllib.parse import urljoin, urlparse

import httpx

from app.discovery import _candidate_links
from app.extraction import (
    HEC_COMMONWEALTH_2027_URL,
    HEC_KNOWLEDGE_CORRIDOR_BASE,
    HEC_KNOWLEDGE_CORRIDOR_PAGES,
    _parse_hec_commonwealth_announcement,
    _parse_hec_knowledge_corridor,
)
from app.source_catalog import OFFICIAL_SOURCES


HEADERS = {
    "User-Agent": "ScholarPathAI-live-source-verification/1.0",
    "Accept": "text/html,application/xhtml+xml",
}
TIMEOUT = httpx.Timeout(35.0, connect=15.0)


async def get_page(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    response = await client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise ValueError(f"Expected HTML, received {content_type or 'unknown content type'}")
    return response.text, str(response.url)


async def main() -> None:
    failures: list[str] = []
    timeout = TIMEOUT

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=HEADERS,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    ) as client:
        print("\n========== OFFICIAL SOURCE INDEX CHECK ==========")
        reachable = 0
        for source in OFFICIAL_SOURCES:
            url = source["official_url"]
            try:
                html, final_url = await get_page(client, url)
                host = urlparse(url).hostname or ""
                candidates = _candidate_links(html, final_url, host)
                reachable += 1
                print(
                    f"OK | {source['name']} | HTTP HTML | "
                    f"candidate_links={len(candidates)} | {final_url}"
                )
            except Exception as exc:
                failures.append(f"{source['name']}: {type(exc).__name__}: {exc}")
                print(f"UNAVAILABLE | {source['name']} | {type(exc).__name__}: {exc}")

        print("\n========== HEC KNOWLEDGE CORRIDOR PARSER ==========")
        corridor_pages: dict[str, tuple[str, str]] = {}
        for name, path in HEC_KNOWLEDGE_CORRIDOR_PAGES.items():
            url = urljoin(HEC_KNOWLEDGE_CORRIDOR_BASE, path)
            try:
                html, final_url = await get_page(client, url)
                corridor_pages[name] = (html, final_url)
                print(f"FETCHED | {name} | {final_url}")
            except Exception as exc:
                failures.append(f"HEC corridor {name}: {type(exc).__name__}: {exc}")
                print(f"UNAVAILABLE | {name} | {type(exc).__name__}: {exc}")

        corridor = _parse_hec_knowledge_corridor(corridor_pages)
        if corridor is None:
            print("PARSER RESULT | Knowledge Corridor: no complete programme extraction")
        else:
            print("PARSER RESULT | Knowledge Corridor:", corridor.title)
            print("Fields:", sorted(corridor.fields))
            print("Criteria:", len(corridor.criteria))
            print("Evidence:", len(corridor.evidence))
            missing_criteria = [item for item in corridor.criteria if item not in corridor.criteria_sources]
            missing_evidence = [item for item in corridor.evidence if item not in corridor.evidence_sources]
            print("Criteria missing provenance:", len(missing_criteria))
            print("Evidence missing provenance:", len(missing_evidence))
            if missing_criteria or missing_evidence:
                failures.append("Knowledge Corridor extraction contains facts without source URLs")

        print("\n========== HEC COMMONWEALTH PARSER ==========")
        try:
            html, final_url = await get_page(client, HEC_COMMONWEALTH_2027_URL)
            commonwealth = _parse_hec_commonwealth_announcement(html, final_url)
            if commonwealth is None:
                print("PARSER RESULT | Commonwealth: no matching 2027-28 announcement extracted")
            else:
                print("PARSER RESULT |", commonwealth.title)
                print("Provider:", commonwealth.provider_name)
                print("Deadline:", commonwealth.fields.get("deadline_text", "not extracted"))
                print("Criteria:", len(commonwealth.criteria))
                print("Evidence:", len(commonwealth.evidence))
                missing_criteria = [item for item in commonwealth.criteria if item not in commonwealth.criteria_sources]
                missing_evidence = [item for item in commonwealth.evidence if item not in commonwealth.evidence_sources]
                print("Criteria missing provenance:", len(missing_criteria))
                print("Evidence missing provenance:", len(missing_evidence))
                if missing_criteria or missing_evidence:
                    failures.append("Commonwealth extraction contains facts without source URLs")
        except Exception as exc:
            failures.append(f"HEC Commonwealth: {type(exc).__name__}: {exc}")
            print("UNAVAILABLE | Commonwealth |", type(exc).__name__, str(exc))

    print("\n========== LIVE CHECK SUMMARY ==========")
    print(f"Official source indexes reachable: {reachable}/{len(OFFICIAL_SOURCES)}")
    if failures:
        print("Issues observed:")
        for failure in failures:
            print("-", failure)
        # The live check is diagnostic because external government websites
        # may rate-limit or block hosted CI. Unit tests remain the required gate.
        print("LIVE CHECK RESULT: completed with external-source issues")
    else:
        print("LIVE CHECK RESULT: all requests and parser provenance checks passed")


if __name__ == "__main__":
    asyncio.run(main())
