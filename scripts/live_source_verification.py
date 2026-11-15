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
from app.live_discovery import discover_live_scholarships


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

    print("\n========== LIVE SCHOLARSHIP DISCOVERY CHECK ==========")
    records = await discover_live_scholarships()
    print(f"Fresh live scholarship records extracted: {len(records)}")
    for record in records:
        print(
            "RECORD | "
            f"{record.get('source_name')} | "
            f"{record.get('title')} | "
            f"deadline={record.get('deadline_date')} | "
            f"criteria={len(record.get('criteria', []))} | "
            f"{record.get('source_url')}"
        )

    # The Santander page is a critical live-extraction check: a successful
    # source-index request must also produce a fully evidenced individual record.
    santander_url = "https://www.uni-goettingen.de/en/santander%2Bstipendien/707360.html"
    santander_application_url = (
        "https://app.santanderopenacademy.com/en/program/"
        "sorgenfrei-stipendium-deutschland-2026-10-x-10-000-eur-fuer-dein-studium"
    )
    santander_record = next(
        (record for record in records if record.get("source_url") == santander_url),
        None,
    )
    if santander_record is None:
        blocking_failures.append(
            "The current Göttingen Santander programme page was reachable but "
            "live discovery did not emit an individual scholarship record."
        )
    else:
        if santander_record.get("deadline_date") != "2026-11-30":
            blocking_failures.append(
                "Göttingen Santander deadline extraction expected 2026-11-30; "
                f"received {santander_record.get('deadline_date')!r}."
            )
        if santander_record.get("application_url") != santander_application_url:
            blocking_failures.append(
                "Göttingen Santander application URL was not preserved from the official page."
            )
        if santander_record.get("provider_name") != "Openbank Deutschland AG":
            blocking_failures.append(
                "Göttingen Santander provider attribution did not match the curated official source."
            )
        criterion_text = " ".join(
            str(item.get("requirement_text") or "").casefold()
            for item in santander_record.get("criteria", [])
        )
        if "regular students" not in criterion_text or "exchange students are not eligible" not in criterion_text:
            blocking_failures.append(
                "Göttingen Santander regular-student eligibility and exchange-student exclusion "
                "were not both preserved."
            )
        if not any(
            item.get("field_name") == "deadline_text"
            and item.get("evidence_url") == santander_url
            for item in santander_record.get("evidence", [])
        ):
            blocking_failures.append(
                "Göttingen Santander deadline is missing its official-page evidence link."
            )

    # Validate curated programme coverage. Other provider pages remain warnings
    # because independent providers can temporarily block or delay CI requests.
    expected_programme_urls = {
        santander_url,
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
    if access_restricted:
        print(
            "LIVE CHECK RESULT: no unexpected source failures; "
            "some official pages blocked automated CI access and remain configured for live discovery."
        )
    elif failures:
        print("LIVE CHECK RESULT: core DAAD sources passed; some secondary indexes were unavailable")
    else:
        print("LIVE CHECK RESULT: all official source indexes were reachable")


if __name__ == "__main__":
    asyncio.run(main())
