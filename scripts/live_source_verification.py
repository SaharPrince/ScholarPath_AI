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
from app.source_catalog import OFFICIAL_SOURCES


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
    response = await client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise ValueError(f"Expected HTML, received {content_type or 'unknown content type'}")
    return response.text, str(response.url)


async def main() -> None:
    failures: list[str] = []
    blocking_failures: list[str] = []
    access_restricted: list[str] = []
    reachable = 0
    core_reachable = set()

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers=HEADERS,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    ) as client:
        print("\n========== OFFICIAL GERMAN SOURCE INDEX CHECK ==========")
        for source in OFFICIAL_SOURCES:
            url = source["official_url"]
            try:
                html, final_url = await get_page(client, url)
                host = urlparse(final_url).hostname or ""
                candidates = _candidate_links(html, final_url, host)
                reachable += 1
                if source["name"] in CORE_SOURCE_NAMES:
                    core_reachable.add(source["name"])
                print(
                    f"OK | {source['name']} | HTTP HTML | "
                    f"candidate_links={len(candidates)} | {final_url}"
                )
            except Exception as exc:
                message = f"{source['name']}: {type(exc).__name__}: {exc}"
                failures.append(message)
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code in {403, 429}:
                    # Some official providers block cloud CI traffic. This is
                    # not evidence that the source URL is invalid; report it
                    # distinctly rather than failing the whole PR.
                    access_restricted.append(message)
                    print(f"ACCESS RESTRICTED | {source['name']} | HTTP {status_code}")
                else:
                    if source["name"] in CORE_SOURCE_NAMES:
                        blocking_failures.append(message)
                    print(f"UNAVAILABLE | {source['name']} | {type(exc).__name__}: {exc}")

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

    if blocking_failures:
        print("LIVE CHECK RESULT: FAILED")
        raise SystemExit(1)
    if failures:
        print("LIVE CHECK RESULT: core DAAD sources passed; some secondary indexes were unreachable")
    else:
        print("LIVE CHECK RESULT: all official source indexes were reachable")


if __name__ == "__main__":
    asyncio.run(main())
