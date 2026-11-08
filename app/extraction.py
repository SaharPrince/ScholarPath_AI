"""Conservative extraction of individual scholarship opportunities.

A page is only promoted when it looks like a specific opportunity page and
contains at least one scholarship-specific fact. Extracted records remain
unverified. Every populated fact is accompanied by its source evidence.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.database import get_connection


MAX_RESPONSE_BYTES = 2_000_000
USER_AGENT = "ScholarPathAI/0.4 (+official scholarship detail extractor)"
FIELD_LABELS = {
    "provider_name": ("scholarship provider", "offered by", "administered by", "sponsor"),
    "deadline_text": ("application deadline", "application closes", "deadline", "apply by", "closing date"),
    "funding_summary": ("funding", "scholarship value", "financial support", "tuition fee", "stipend"),
    "eligibility": ("eligibility", "who can apply", "eligible applicants"),
    "ineligibility": ("ineligibility", "who cannot apply", "who is not eligible", "not eligible"),
    "study_level": ("degree level", "study level", "level of study", "programme level", "program level"),
    "nationality": ("nationality", "citizenship", "eligible countries", "country of residence"),
    "academic_requirements": ("academic requirements", "minimum marks", "minimum gpa", "grade requirement"),
    "age_limit": ("age limit", "age requirement", "maximum age"),
    "required_documents": ("required documents", "documents required", "supporting documents"),
    "language_requirements": ("language requirements", "language proficiency", "english language requirement"),
    "work_experience": ("work experience", "professional experience", "years of experience"),
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
OPEN_PATTERN = re.compile(r"(?i)\b(applications? (?:(?:are )?(?:now )?)open|now accepting applications|currently accepting applications|apply now)\b")
UPCOMING_PATTERN = re.compile(r"(?i)\b(applications? (?:will|are expected to) open|opens? for applications)\b")
DISCONTINUED_PATTERN = re.compile(r"(?i)\b(discontinued|programme has ended|program has ended|no longer offered)\b")
SHORTLISTED_PATTERN = re.compile(r"(?i)\b(shortlisted candidates|candidates? who (?:have been |were )?shortlisted|only for candidates? shortlisted|shortlist announced|interview shortlist)\b")


@dataclass
class ExtractedPage:
    title: str
    description: str | None
    provider_name: str | None
    fields: dict[str, str] = field(default_factory=dict)
    criteria: list[tuple[str, str, str]] = field(default_factory=list)
    evidence: list[tuple[str, str]] = field(default_factory=list)
    application_status: str = "unknown"
    applicant_category: str = "unknown"


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _is_mandatory_criterion(criterion_type: str, requirement_text: str) -> bool:
    """Mark mandatory only when the source wording or section label makes it explicit."""
    if criterion_type in {"ineligibility", "required_documents"}:
        return True
    text = requirement_text.casefold()
    if re.search(r"\b(preferred|preferable|encouraged|recommended|desirable|an advantage|priority will be given)\b", text):
        return False
    return bool(re.search(
        r"\b(must|required|mandatory|minimum|at least|no more than|maximum|"
        r"only|cannot|not eligible|ineligible|shall|must not)\b",
        text,
    ))

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


def _remove_site_chrome(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove shared navigation and layout regions before reading programme facts."""
    for node in soup(["script", "style", "noscript", "svg", "nav", "footer", "aside"]):
        node.decompose()

    for node in soup.find_all(True):
        role = str(node.get("role", "")).lower()
        aria_label = str(node.get("aria-label", "")).lower()
        classes_value = node.get("class", [])
        classes = " ".join(classes_value).lower() if isinstance(classes_value, list) else str(classes_value).lower()
        node_id = str(node.get("id", "")).lower()
        marker = " ".join((role, aria_label, classes, node_id))
        if role in {"navigation", "contentinfo"} or any(
            term in marker for term in ("breadcrumb", "sidebar", "site-nav", "navbar", "main-menu", "footer-menu")
        ):
            node.decompose()

    return soup.find("main") or soup.find("article") or soup.body or soup


def _find_labeled_text(content_root: BeautifulSoup, labels: tuple[str, ...], field_name: str) -> str | None:
    """Extract facts only from programme content, not navigation or generic headings."""
    for node in content_root.find_all(["p", "li", "td", "th", "dt", "dd"]):
        text = _clean(node.get_text(" ", strip=True))
        for label in labels:
            # Labels must begin the field text. A label appearing midway through
            # a navigation sentence is not a reliable field/value pair.
            match = re.match(rf"^\s*{re.escape(label)}\s*[:–—-]\s*(.+)$", text, re.I)
            value = _clean(match.group(1)) if match else ""
            if not value and text.lower().rstrip(":") == label:
                sibling = node.find_next(["p", "li", "td", "dd"])
                value = _clean(sibling.get_text(" ", strip=True)) if sibling else ""
            if not value or len(value) > 1200:
                continue
            if field_name == "eligibility":
                # Reject short title-like labels such as "University Partnerships".
                meaningful_terms = (
                    "applicant", "citizen", "national", "resident", "degree", "enrolled",
                    "graduate", "undergraduate", "bachelor", "master", "phd", "doctor",
                    "age", "years", "experience", "must", "minimum", "completed",
                )
                if len(value.split()) < 3 and not any(term in value.lower() for term in meaningful_terms):
                    continue
            if field_name == "deadline_text" and not (DATE_PATTERN.search(value) or ROLLING_PATTERN.search(value)):
                continue
            return value
    return None
def _find_heading_section(content_root: BeautifulSoup, heading_names: tuple[str, ...]) -> str | None:
    """Collect visible paragraph/list content beneath a matching section heading."""
    wanted = {name.casefold() for name in heading_names}
    for heading in content_root.find_all(["h2", "h3", "h4", "h5"]):
        heading_text = _clean(heading.get_text(" ", strip=True)).rstrip(":").casefold()
        if heading_text not in wanted:
            continue
        chunks: list[str] = []
        for node in heading.find_all_next(["h1", "h2", "h3", "h4", "h5", "p", "li"]):
            if node.name in {"h1", "h2", "h3", "h4", "h5"}:
                break
            value = _clean(node.get_text(" ", strip=True))
            if value and value not in chunks:
                chunks.append(value)
        if chunks:
            return " ".join(chunks)[:4000]
    return None


def _find_provider_statement(content_root: BeautifulSoup) -> str | None:
    """Extract a provider only when the page explicitly names who operates the award."""
    pattern = re.compile(
        r"\b(?:managed|administered|offered|provided)\s+by\s+(.+?)"
        r"(?:\s+(?:under|in accordance with|according to)\b|[.;]|$)",
        re.I,
    )
    for paragraph in content_root.find_all("p"):
        value = _clean(paragraph.get_text(" ", strip=True))
        match = pattern.search(value)
        if match:
            provider = re.sub(r"^the\s+", "", _clean(match.group(1)), flags=re.I).strip(" ,:;")
            if 3 <= len(provider) <= 240:
                return provider
    return None


def _find_study_destination(content_root: BeautifulSoup) -> str | None:
    """Extract a destination only when a page explicitly ties study to a named country."""
    countries = (
        "United States", "United Kingdom", "United Arab Emirates", "South Korea",
        "New Zealand", "Saudi Arabia", "South Africa", "United States of America",
        "Germany", "France", "Canada", "Australia", "Japan", "China", "Türkiye",
        "Turkey", "Sweden", "Norway", "Finland", "Netherlands", "Italy", "Spain",
        "Switzerland", "Ireland", "Pakistan",
    )
    country_pattern = "|".join(re.escape(country) for country in sorted(countries, key=len, reverse=True))
    pattern = re.compile(
        rf"\b(?:study|studying|graduate study|degree programme|degree program)"
        rf"[^.?!]{{0,100}}?\b(?:in|at universities all over)\s+(?:the\s+)?({country_pattern})\b",
        re.I,
    )
    for paragraph in content_root.find_all("p"):
        value = _clean(paragraph.get_text(" ", strip=True))
        match = pattern.search(value)
        if match:
            # Return canonical country spelling from the maintained allow-list.
            matched = match.group(1).casefold()
            return next(country for country in countries if country.casefold() == matched)
    return None


def _find_application_url(content_root: BeautifulSoup, page_url: str) -> str | None:
    """Find an application destination only when the official page links to it explicitly."""
    strong_label = re.compile(
        r"(?i)\b(?:apply\s+now|apply\s+online|online\s+application|"
        r"application\s+portal|start\s+(?:a\s+)?new\s+application|"
        r"submit\s+(?:an?\s+)?application|application\s+form|application\s+system)\b"
    )
    contextual_action = re.compile(
        r"(?i)\b(?:apply\s+online|submit\s+(?:the\s+)?application\s+online|"
        r"online\s+application|application\s+portal|start\s+(?:a\s+)?new\s+application)\b"
    )
    application_headings = {
        "how to apply", "how do i apply", "application process",
        "application submission", "apply online", "application portal",
    }
    generic_cta = {"here", "click here", "apply", "application"}
    source = urlparse(page_url)
    candidates: dict[str, int] = {}

    for anchor in content_root.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True))
        parent_text = _clean(anchor.parent.get_text(" ", strip=True)) if anchor.parent else label
        previous_heading = anchor.find_previous(["h1", "h2", "h3", "h4", "h5"])
        heading_text = (
            _clean(previous_heading.get_text(" ", strip=True)).rstrip(":").casefold()
            if previous_heading else ""
        )
        in_application_section = heading_text in application_headings

        if strong_label.search(label):
            score = 3
        elif in_application_section and label.casefold() in generic_cta:
            score = 2
        elif contextual_action.search(parent_text) and label.casefold() in generic_cta:
            score = 1
        else:
            continue

        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith("#"):
            continue
        target = urljoin(page_url, href)
        parsed = urlparse(target)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or (parsed.scheme, parsed.netloc, parsed.path, parsed.query)
               == (source.scheme, source.netloc, source.path, source.query)
            or parsed.path.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"))
        ):
            continue
        candidates[target] = max(score, candidates.get(target, 0))

    if not candidates:
        return None
    highest_score = max(candidates.values())
    best = [url for url, score in candidates.items() if score == highest_score]
    return best[0] if len(best) == 1 else None


def _find_funding_statement(content_root: BeautifulSoup) -> str | None:
    """Capture explicit funding prose when the source has no labelled funding field."""
    indicators = (
        "scholarship funds", "funds graduate study", "grant funds",
        "the grant funds", "the scholarship covers", "the grant covers",
        "financial support includes", "provides a stipend",
    )
    for paragraph in content_root.find_all("p"):
        value = _clean(paragraph.get_text(" ", strip=True))
        lowered = value.lower()
        if len(value) >= 45 and any(term in lowered for term in indicators):
            return value[:1200]
    return None


def _extract_description_criteria(description: str) -> list[tuple[str, str, str]]:
    """Extract only explicit applicant or host-eligibility statements from programme prose."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z“])", description)
    extracted: list[tuple[str, str, str]] = []
    applicant_actor = re.compile(
        r"(?i)\b(applicants?|candidates?|students?|participants?|scholars?|fellows?|"
        r"professionals?|teachers?|officials?)\b"
    )
    host_actor = re.compile(
        r"(?i)\b(non[- ]?U\.?S\.?|international|higher education|post[- ]?secondary|"
        r"academic|educational)?\s*(institutions?|universit(?:y|ies)|libraries|museums|hospitals|"
        r"ministries)\b"
    )
    explicit_requirement = re.compile(
        r"(?i)\b(must|must be|must have|required to|are required|is required|"
        r"only candidates|eligible to|eligible applicants|eligible host)\b"
    )
    for raw in sentences:
        sentence = _clean(raw)
        if not sentence or len(sentence) > 1000 or not explicit_requirement.search(sentence):
            continue
        lowered = sentence.casefold()
        if host_actor.search(sentence) and re.search(r"(?i)\b(eligible to host|may include|are eligible|eligible institutions)\b", sentence):
            extracted.append(("institution_eligibility", "Eligible host institutions", sentence))
        elif applicant_actor.search(sentence) and re.search(r"(?i)\b(applicants?|candidates?|students?|participants?|scholars?|fellows?|professionals?|teachers?|officials?)\s+(?:must|required|are required|should)", sentence):
            extracted.append(("eligibility", "Eligibility from programme description", sentence))
    return extracted


def _classify_application_status(body_text: str, deadline_date: str | None) -> str:
    """Classify this application cycle only; never infer openness from a future date."""
    if DISCONTINUED_PATTERN.search(body_text):
        return "discontinued"
    if SHORTLISTED_PATTERN.search(body_text):
        return "shortlisted_only"
    if ROLLING_PATTERN.search(body_text):
        return "open"
    if deadline_date:
        try:
            if datetime.strptime(deadline_date, "%Y-%m-%d").date() < datetime.now(timezone.utc).date():
                return "closed"
        except ValueError:
            pass
    if OPEN_PATTERN.search(body_text):
        return "open"
    if UPCOMING_PATTERN.search(body_text):
        return "upcoming"
    return "unknown"


def _classify_applicant_category(body_text: str) -> str:
    text = body_text.lower()
    if re.search(r"\b(universit(?:y|ies)|institutions?|organisations?|organizations?) (?:may|can) apply\b", text):
        return "institution"
    if re.search(r"\b(faculty members?|professors?|academic staff)\b", text):
        return "faculty"
    # Degree-level eligibility is stronger evidence than incidental mentions
    # of work experience or professional references elsewhere on the page.
    if re.search(
        r"\b(undergraduate students?|graduate students?|currently enrolled students?|students currently enrolled|"
        r"master'?s applicants?|phd applicants?|degree applicants?|graduate study|"
        r"master'?s\b|phd\b|"
        r"master'?s (?:degree|programme|program)|phd (?:degree|programme|program)|"
        r"apply(?:ing)? for (?:a )?(?:master'?s|phd)|seeking (?:a )?(?:master'?s|phd) degree)\b",
        text,
    ):
        return "student"
    if re.search(r"\b(recent graduates?|alumni|postgraduate applicants?)\b", text):
        return "graduate"
    if re.search(r"\b(mid[- ]career professionals?|young professionals?|senior professionals?|senior scholars?|working professionals?|employed professionals?|professionals with|teachers?|administrators?|government officials?)\b", text):
        return "professional"
    return "unknown"


def parse_scholarship_page(html: str, page_url: str, candidate_title: str | None = None) -> ExtractedPage | None:
    soup = BeautifulSoup(html, "html.parser")
    content_root = _remove_site_chrome(soup)

    h1 = content_root.find("h1")
    title_node = h1 or soup.find("title")
    page_title = _clean(title_node.get_text(" ", strip=True)) if title_node else ""
    candidate_title = _clean(candidate_title or "")
    title = candidate_title if candidate_title and _is_generic_title(page_title) else (page_title or candidate_title)
    if not title or _is_generic_title(title):
        return None

    body_text = _clean(content_root.get_text(" ", strip=True))
    fields: dict[str, str] = {}
    evidence: list[tuple[str, str]] = []
    for field_name, labels in FIELD_LABELS.items():
        value = _find_labeled_text(content_root, labels, field_name)
        if value:
            fields[field_name] = value[:1200]
            evidence.append((field_name, value[:1200]))

    if not _is_opportunity(candidate_title or title, page_title or title, page_url, body_text):
        return None

    # Official programme pages often use section headings and bullet lists
    # instead of inline "Eligibility: ..." labels.
    section_specs = {
        "eligibility": ("Eligibility Criteria", "Eligibility", "Who can apply", "Eligible applicants"),
        "ineligibility": ("Ineligibility", "Who cannot apply", "Who is not eligible"),
        "study_level": ("Degree Level", "Study Level", "Level of Study", "Eligible Degree Levels"),
        "nationality": ("Nationality Requirements", "Citizenship Requirements", "Eligible Nationalities", "Eligible Countries"),
        "academic_requirements": ("Academic Requirements", "Academic Eligibility", "Minimum Academic Requirements", "Minimum Grades", "Minimum GPA"),
        "age_limit": ("Age Limit", "Age Requirements", "Age Eligibility"),
        "required_documents": ("Required Documents", "Documents Required", "Supporting Documents"),
        "language_requirements": ("Language Requirements", "Language Proficiency", "English Language Requirements"),
        "work_experience": ("Work Experience", "Professional Experience", "Relevant Experience"),
    }
    for field_name, headings in section_specs.items():
        section = _find_heading_section(content_root, headings)
        if not section:
            continue
        existing = fields.get(field_name)
        if existing and existing in section:
            merged = section
        elif existing and section in existing:
            merged = existing
        elif existing:
            merged = f"{existing} {section}"
        else:
            merged = section
        if merged != existing:
            fields[field_name] = merged[:4000]
            evidence.append((field_name, fields[field_name]))

    # Provider and destination can be extracted from explicit programme prose.
    if "provider_name" not in fields:
        provider_statement = _find_provider_statement(content_root)
        if provider_statement:
            fields["provider_name"] = provider_statement
            evidence.append(("provider_name", provider_statement))
    if "study_destination" not in fields:
        destination = _find_study_destination(content_root)
        if destination:
            fields["study_destination"] = destination
            evidence.append(("study_destination", destination))

    # Application links must be explicit links on the official opportunity page.
    application_url = _find_application_url(content_root, page_url)
    if application_url:
        fields["application_url"] = application_url
        evidence.append(("application_url", application_url))

    # Funding is often described in a normal paragraph rather than a labelled row.
    if "funding_summary" not in fields:
        funding = _find_funding_statement(content_root)
        if funding:
            fields["funding_summary"] = funding
            evidence.append(("funding_summary", funding))

    # Avoid site-wide meta descriptions and boilerplate organization copy.
    description = None
    for paragraph in content_root.find_all("p"):
        candidate = _clean(paragraph.get_text(" ", strip=True))
        lowered = candidate.lower()
        if len(candidate) < 50:
            continue
        if "provides opportunities and scholarships" in lowered or "welcome to" in lowered:
            continue
        if any(term in lowered for term in ("scholarship", "fellowship", "grant", "programme", "program")):
            description = candidate[:1200]
            break

    # A deadline by itself is not enough to establish a meaningful opportunity.
    if not any(name != "deadline_text" for name in fields) and not description:
        return None
    if not any(name != "deadline_text" for name in fields) and len(description or "") < 100:
        return None

    # Do not mistake the website operator (og:site_name) for the scholarship
    # provider. Populate this only from an explicit provider label on the page.
    provider = fields.get("provider_name")

    criteria: list[tuple[str, str, str]] = []
    for field_name in (
        "eligibility", "ineligibility", "study_level", "nationality",
        "academic_requirements", "age_limit", "required_documents",
        "language_requirements", "work_experience",
    ):
        if field_name in fields:
            # Keep distinct statements separate so one optional sentence cannot
            # downgrade a mandatory requirement elsewhere in the same section.
            statements = re.split(r"(?<=[.!?])\s+(?=[A-Z“])", fields[field_name])
            for statement in statements:
                statement = _clean(statement)
                if statement:
                    criteria.append((field_name, field_name.replace("_", " ").title(), statement))

    if description:
        evidence.append(("description", description))
        # Descriptive copy is used only when it contains explicit eligibility
        # language and a clearly identified applicant or host actor.
        criteria.extend(_extract_description_criteria(description))
    deadline_date = _parse_deadline_date(fields.get("deadline_text"))
    application_status = _classify_application_status(body_text, deadline_date)
    # Use programme identity and extracted eligibility, not unrelated page-wide text.
    applicant_category = _classify_applicant_category(
        " ".join((title, page_title, fields.get("eligibility", ""), description or ""))
    )
    return ExtractedPage(title[:300], description, provider, fields, criteria, evidence,
                         application_status, applicant_category)


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
                           (source_id, title, provider_name, study_destination, funding_summary, application_url, deadline_text, deadline_date,
                            status, source_record_url, application_status, applicant_category)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unverified', ?, ?, ?)
                           ON CONFLICT(source_id, source_record_url) DO UPDATE SET
                               title = excluded.title,
                               provider_name = excluded.provider_name,
                               country = NULL,
                               study_destination = excluded.study_destination,
                               application_url = excluded.application_url,
                               funding_summary = excluded.funding_summary,
                               deadline_text = excluded.deadline_text,
                               deadline_date = excluded.deadline_date,
                               status = 'unverified',
                               application_status = excluded.application_status,
                               applicant_category = excluded.applicant_category,
                               last_checked_at = CURRENT_TIMESTAMP,
                               updated_at = CURRENT_TIMESTAMP
                           RETURNING id""",
                        (candidate["source_id"], parsed.title, parsed.provider_name,
                         parsed.fields.get("study_destination"), parsed.fields.get("funding_summary"),
                         parsed.fields.get("application_url"), parsed.fields.get("deadline_text"),
                         _parse_deadline_date(parsed.fields.get("deadline_text")),
                         candidate["candidate_url"], parsed.application_status, parsed.applicant_category),
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
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (scholarship_id, criterion_type, label, requirement,
                             int(_is_mandatory_criterion(criterion_type, requirement)),
                             candidate["candidate_url"]),
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
                        # Retain previously captured facts and evidence for audit history.
                        # The rejected trust status keeps this row out of the normal feed.
                        connection.execute(
                            """UPDATE scholarships SET status = 'rejected',
                               last_checked_at = CURRENT_TIMESTAMP,
                               updated_at = CURRENT_TIMESTAMP
                               WHERE id = ?""",
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
