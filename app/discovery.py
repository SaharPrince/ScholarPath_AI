from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.database import get_connection


DISCOVERY_TERMS = (
    "scholarship",
    "financial aid",
    "fellowship",
    "grant",
    "funding",
    "studentship",
)
MAX_RESPONSE_BYTES = 2_000_000
MAX_LINKS_PER_SOURCE = 200
USER_AGENT = "ScholarPathAI/0.1 (+official scholarship source indexer)"


@dataclass
class SourceResult:
    source_id: int
    source_name: str
    status: str
    candidates_found: int = 0
    message: str | None = None


def _normalized_host(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        return None
    return parsed.hostname.lower().rstrip(".")


def _link_label(anchor) -> str:
    """Read visible and accessible labels, including image-only links."""
    labels = [
        anchor.get_text(" ", strip=True),
        anchor.get("aria-label", ""),
        anchor.get("title", ""),
    ]
    for image in anchor.find_all("img"):
        labels.extend((image.get("alt", ""), image.get("title", "")))

    for label in labels:
        cleaned = " ".join(str(label).split())
        if cleaned:
            return cleaned
    return ""


def _candidate_links(html: str, page_url: str, allowed_host: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True, limit=MAX_LINKS_PER_SOURCE):
        href = str(anchor.get("href", "")).strip()
        title = _link_label(anchor)
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute_url = urljoin(page_url, href)
        parsed = urlparse(absolute_url)
        host = _normalized_host(absolute_url)
        if host != allowed_host or parsed.fragment:
            continue
        path_lower = parsed.path.lower()
        title_lower = title.casefold()

        # Ignore site navigation, authentication, archives, contact pages and
        # downloadable reference documents. These are not individual opportunity
        # pages and otherwise inflate the review queue.
        excluded_path_markers = (
            "/_layouts/15/authenticate.aspx",
            "/contactus.aspx",
            "/inactive-scholarships",
            "/archive",
            "/documents/",
        )
        excluded_extensions = (
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        )
        if any(marker in path_lower for marker in excluded_path_markers):
            continue
        if path_lower.endswith(excluded_extensions):
            continue
        if title_lower in {"sign in", "log in", "login", "contact us"}:
            continue

        # HEC's shared root index is linked from several category pages.
        # Keep named programme subpages such as /IDPS/Pages/default.aspx,
        # but do not rediscover the generic /scholarshipsgrants/Pages/default.aspx.
        if path_lower.rstrip("/") == "/english/scholarshipsgrants/pages/default.aspx":
            continue

        searchable = f"{title} {parsed.path}".lower()
        if not any(term in searchable for term in DISCOVERY_TERMS):
            continue
        clean_url = parsed._replace(query="", fragment="").geturl()
        if clean_url == page_url:
            continue
        fallback = parsed.path.rsplit("/", 1)[-1] or "Scholarship information"
        found.setdefault(clean_url, title or fallback)
    return list(found.items())


async def _fetch_source(client: httpx.AsyncClient, source: dict) -> SourceResult:
    source_url = source["official_url"]
    allowed_host = _normalized_host(source_url)
    if not allowed_host:
        return SourceResult(source["id"], source["name"], "skipped", message="Source URL must use HTTPS on the standard port.")

    try:
        async with client.stream("GET", source_url) as response:
            if response.status_code != 200:
                return SourceResult(source["id"], source["name"], "failed", message=f"HTTP {response.status_code}")
            final_host = _normalized_host(str(response.url))
            if final_host != allowed_host:
                return SourceResult(source["id"], source["name"], "skipped", message="Cross-domain redirect was not followed.")
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                return SourceResult(source["id"], source["name"], "skipped", message="Source did not return HTML.")
            length = response.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
                return SourceResult(source["id"], source["name"], "skipped", message="Source page exceeds the size limit.")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    return SourceResult(source["id"], source["name"], "skipped", message="Source page exceeded the size limit while downloading.")
                chunks.append(chunk)
            html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            links = _candidate_links(html, source_url, allowed_host)
    except httpx.TimeoutException:
        return SourceResult(source["id"], source["name"], "failed", message="Source request timed out.")
    except httpx.HTTPError as exc:
        return SourceResult(source["id"], source["name"], "failed", message=f"HTTP request failed: {type(exc).__name__}")

    with get_connection() as connection:
        before = connection.total_changes
        for url, title in links:
            connection.execute(
                """INSERT INTO discovery_candidates
                   (source_id, title, candidate_url, status)
                   VALUES (?, ?, ?, 'candidate')
                   ON CONFLICT(source_id, candidate_url) DO UPDATE SET
                       title = excluded.title,
                       last_seen_at = CURRENT_TIMESTAMP""",
                (source["id"], title[:300], url),
            )
        inserted = connection.total_changes - before

        # Retire previously queued false positives without deleting their audit
        # records. This also protects existing local databases on the next run.
        connection.execute(
            """UPDATE discovery_candidates
               SET status = 'reviewed'
               WHERE status = 'candidate'
                 AND (
                     lower(candidate_url) LIKE '%/_layouts/15/authenticate.aspx%'
                     OR lower(candidate_url) LIKE '%/contactus.aspx%'
                     OR lower(candidate_url) LIKE '%/inactive-scholarships%'
                     OR lower(candidate_url) LIKE '%/archive%'
                     OR lower(candidate_url) LIKE '%/documents/%'
                     OR lower(candidate_url) =
                        'https://www.hec.gov.pk/english/scholarshipsgrants/pages/default.aspx'
                 )"""
        )
    return SourceResult(source["id"], source["name"], "completed", candidates_found=inserted)


async def discover_from_active_sources() -> list[SourceResult]:
    """Index scholarship-related links on configured official source pages.

    This produces review candidates only. It does not create scholarship records
    or verify authenticity, eligibility, deadlines, or whether applications are open.
    """
    with get_connection() as connection:
        sources = [dict(row) for row in connection.execute(
            "SELECT id, name, official_url FROM sources WHERE is_active = 1 ORDER BY id"
        ).fetchall()]

    timeout = httpx.Timeout(12.0, connect=5.0)
    limits = httpx.Limits(max_connections=3, max_keepalive_connections=2)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    results: list[SourceResult] = []
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        headers=headers,
        follow_redirects=False,
    ) as client:
        for source in sources:
            results.append(await _fetch_source(client, source))
    return results
