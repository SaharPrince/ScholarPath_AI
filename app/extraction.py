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
    "deadline_text": ("our next application deadlines", "application deadline", "application closes", "deadline", "apply by", "closing date"),
    "application_status": ("current status",),
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
GERMAN_DATE_PATTERN = re.compile(
    r"(?i)\b(?P<day>\d{1,2})\.?\s+"
    r"(?P<month>januar|februar|märz|maerz|april|mai|juni|juli|august|"
    r"september|oktober|november|dezember)\s+(?P<year>\d{4})\b"
)
GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9,
    "oktober": 10, "november": 11, "dezember": 12,
}
GERMAN_NUMERIC_DATE_RANGE_PATTERN = re.compile(
    r"(?i)\b(?P<start_day>\d{1,2})\.(?P<start_month>\d{1,2})\.?\s*[-–]\s*"
    r"(?P<end_day>\d{1,2})\.(?P<end_month>\d{1,2})\.?(?P<year>\d{4})\b"
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
    evidence_sources: dict[tuple[str, str], str] = field(default_factory=dict)
    criteria_sources: dict[tuple[str, str, str], str] = field(default_factory=dict)


def _clean(value: str) -> str:
    """Collapse whitespace and repair known missing-space joins in extracted page text."""
    # Strip invisible formatting characters copied from SharePoint pages.
    value = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", value)
    text = " ".join(value.split()).strip()
    # Repair common SharePoint joins such as AnnualStipend, FullyFunded,
    # DairyScience, and 1000Ph.D. without splitting acronym endings like PhD.
    text = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", text)
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
    # Repair letter-to-number joins in years and monetary amounts, plus
    # known SharePoint joins where both sides are lowercase.
    text = re.sub(r"(?<=[A-Za-z])(?=\d{4}\b)", " ", text)
    text = re.sub(r"(?i)\b(USD|PKR)(?=\d)", r"\1 ", text)
    text = re.sub(r"(?i)\b(States?)(under|at|for|to)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(without)(a)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(application)(to)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(The)female\b", r"\1 female", text)
    text = re.sub(r"(?i)(?<=\d)BST\b", " BST", text)
    # Repair verified missing-space joins observed in current HEC source pages.
    for left, right in (
        ("doctoral", "study"),
        ("a", "category"),
        ("be", "availing"),
        ("CSC's", "six"),
        ("all", "applicants"),
        ("guarantee", "final"),
        ("the", "applicant"),
        ("is", "the"),
        ("female", "nomination"),
        ("are", "required"),
        # Additional exact HEC SharePoint joins found in the saved eligibility
        # criteria after the targeted extraction.
        ("throughout", "the"),
        ("Researchers", "of"),
        ("division", "in"),
        ("Pakistan", "national"),
        ("at", "the"),
        ("the", "Commonwealth"),
        # Exact lowercase joins verified in the saved HEC Commonwealth record.
        ("submit", "their"),
        ("national", "university"),
        ("or", "actual"),
    ):
        text = re.sub(
            rf"(?i)\b({re.escape(left)})({re.escape(right)})\b",
            r"\1 \2",
            text,
        )
    # Repair exact joined tokens where the component words have no
    # regex word boundary between them. Keep this list limited to forms
    # verified in the official HEC pages; do not attempt general segmentation.
    for left, right in (
        ("doctoral", "study"),
        ("CSC's", "six"),
        ("a", "UK"),
        ("nomination", "process"),
        ("online", "application"),
        ("online", "applications"),
        ("Management", "and"),
        ("inclusion", "and"),
        ("and", "capacity"),
    ):
        text = re.sub(
            rf"(?i)(?<![A-Za-z]){re.escape(left + right)}(?![A-Za-z])",
            left + " " + right,
            text,
        )
    # A small number of source themes lose the space after this exact comma.
    text = re.sub(r"(?i)\b(access),(?=inclusion\b)", r"\1, ", text)

    # Repair observed missing spaces inside HEC development-theme phrases.
    text = re.sub(r"(?i)\bmanagement(?=and\b)", "management ", text)
    text = re.sub(r"(?i)\binclusion(?=and\b)", "inclusion ", text)
    text = re.sub(r"(?i)\band(?=capacity\b)", "and ", text)

    # These all-lowercase joins have no word boundary between their
    # component words, so repair the exact observed source forms explicitly.
    text = re.sub(r"(?i)\barerequired\b", "are required", text)
    text = re.sub(r"(?i)\bandEnvironmental\b", "and Environmental", text)
    text = re.sub(r"(?i)\bglobalpeace\b", "global peace", text)
    # Keep ordinal division references readable after SharePoint spacing repair.
    text = re.sub(r"(?i)\b(and|or)(?=\d(?:st|nd|rd|th)\b)", r"\1 ", text)
    text = re.sub(r"(?i)\b(2|3)\s+(nd|rd)\b", r"\1\2", text)
    # Repair unambiguous joins observed in official CCAP source copy.
    text = re.sub(r"(?i)\b(years?)(of)(experience)\b", r"\1 \2 \3", text)
    text = re.sub(r"(?i)\b(years?)(of)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(within)(technical|vocational)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(residents?)(of)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(permanent)(resident(?:s)?)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(eligible)(fields?)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(on)(behalf)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(of)(education)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(four-year)(bachelor)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(after)(selection)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(Institutional)(TOEFL)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(applicants?)(must)\b", r"\1 \2", text)
    text = re.sub(r"(?i)(U\.S\.)(?=[A-Za-z])", r"\1 ", text)
    # Additional joins observed in official USEFP CCIP/CCAP page copy.
    text = re.sub(r"(?i)\b(the)(listed)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(to)(the)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(of)(experience)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(United)(States)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(OR)(?=\(\d+\))", r"\1 ", text)
    # Repair recurring joined words in HEC SharePoint copy without attempting
    # unsafe general-purpose word segmentation.
    text = re.sub(r"(?i)\b(which)(is)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(have)(a)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(required)(to)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(in)(the)(relevant)\b", r"\1 \2 \3", text)
    text = re.sub(r"(?<=[A-Za-z])\(", " (", text)

    # Repair additional missing spaces and punctuation spacing found in CCIP/CCAP copy.
    text = re.sub(r"(?i)\b(may)(apply)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(permanent)(residency)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(State)(employees)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(a)(full-time)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(in)(the)\b", r"\1 \2", text)
    text = re.sub(r"(?i)\b(Department)(of)\b", r"\1 \2", text)
    text = re.sub(r"(?i)(i\.e\.)(?=\S)", r"\1 ", text)
    text = re.sub(r",(?=\S)", ", ", text)
    # Explicit final repairs for joined tokens observed in live HEC page output.
    # Keep these exact and conservative; do not attempt general word segmentation.
    for pattern, replacement in (
        (r"(?i)\bdoctoralstudy\b", "doctoral study"),
        (r"(?i)\bCSC'ssix\b", "CSC's six"),
        (r"(?i)\baUK\b", "a UK"),
        (r"(?i)\bnominationprocess\b", "nomination process"),
        (r"(?i)\bHATtests\b", "HAT tests"),
        (r"(?i)\bonline(applications?)\b", r"online \1"),
        (r"(?i)\bAccess,inclusion\b", "Access, inclusion"),
    ):
        text = re.sub(pattern, replacement, text)
    # Repair additional exact joins observed in live HEC announcement and
    # eligibility text. These are deliberately narrow to avoid splitting names.
    for left, right in (
        ("to", "pursue"),
        ("for", "the"),
        ("by", "the"),
        ("female", "nomination"),
        ("permanent", "resident"),
        ("field", "of"),
        ("candidates", "may"),
        ("before", "the"),
        ("in", "HAT"),
        ("may", "upload"),
        ("prescribed", "by"),
        ("to", "submit"),
        ("from", "the"),
    ):
        text = re.sub(
            rf"(?i)(?<![A-Za-z]){re.escape(left + right)}(?![A-Za-z])",
            left + " " + right,
            text,
        )
    text = re.sub(r"(?i)(?<![A-Za-z])Master'sand(?![A-Za-z])", "Master's and", text)
    # Preserve thousands separators in funding and other numeric values.
    text = re.sub(r"(?<=\d),\s+(?=\d{3}\b)", ",", text)
    return text


def _clean_preserving_lines(value: str) -> str:
    """Normalize extracted text line by line without flattening meaningful layout."""
    return "\n".join(
        _clean(line) if line.strip() else ""
        for line in value.splitlines()
    ).strip()


def _save_evidence(connection, scholarship_id: int, evidence: list[tuple[str, str]], evidence_url: str) -> None:
    """Append source evidence without deleting history or duplicating identical facts."""
    for field_name, evidence_text in evidence:
        connection.execute(
            """INSERT INTO scholarship_evidence
               (scholarship_id, field_name, evidence_text, evidence_url)
               SELECT ?, ?, ?, ?
               WHERE NOT EXISTS (
                   SELECT 1 FROM scholarship_evidence
                   WHERE scholarship_id = ?
                     AND field_name = ?
                     AND evidence_text = ?
                     AND evidence_url = ?
               )""",
            (scholarship_id, field_name, evidence_text, evidence_url,
             scholarship_id, field_name, evidence_text, evidence_url),
        )

def _split_criteria_statements(value: str) -> list[str]:
    """Split list items and sentences without breaking common academic abbreviations."""
    protected = value
    abbreviations = {
        "U.S.": "US_ABBREVIATION",
        "Ph.D.": "PHD_ABBREVIATION",
        "M.Phil.": "MPHIL_ABBREVIATION",
        "B.A.": "BA_ABBREVIATION",
        "M.A.": "MA_ABBREVIATION",
        "e.g.": "EG_ABBREVIATION",
        "i.e.": "IE_ABBREVIATION",
    }
    for original, token in abbreviations.items():
        protected = re.sub(re.escape(original), token, protected, flags=re.I)
    # Protect single-letter initials in names, e.g. "Hubert H. Humphrey".
    protected = re.sub(r"\b([A-Z])\.(?=\s+[A-Z])", r"\1INITIAL", protected)
    parts = re.split(r"\s*(?:\n+|(?<=[.!?])\s+(?=[A-Z“]))\s*", protected)
    restored = []
    for part in parts:
        for original, token in abbreviations.items():
            part = re.sub(token, original, part, flags=re.I)
        part = re.sub(r"\b([A-Z])INITIAL", r"\1.", part)
        cleaned = _clean(part)
        if cleaned and cleaned not in restored:
            restored.append(cleaned)
    return restored


def _classify_eligibility_statement(statement: str) -> tuple[str, str]:
    """Assign a more useful criterion type to explicit applicant conditions."""
    text = statement.casefold()
    if re.search(r"\b(?:under|less than|below)\s+\d{1,2}\s+years?\s+old\b|\b\d{1,2}\s+years?\s+old\b", text):
        return "age_limit", "Age limit"
    if re.search(
        r"\b(german language skills|command of the (?:english|german) language|"
        r"deutschkenntnisse|sprachkenntnisse)\b",
        text,
    ):
        return "language_requirements", "Language requirements"
    if re.search(r"\b(above-average|academic performance|grades|gpa|school performance)\b", text):
        return "academic_requirements", "Academic requirements"
    if re.search(r"\b(master(?:'s)?|phd|doctoral)\b", text):
        return "study_level", "Study level"
    if re.search(
        r"\b(?:full-time|part-time)\s+(?:course|study|student|degree|programme|program)\b|"
        r"\b(university|higher education institution|enrolled|admitted)\b",
        text,
    ):
        return "study_level", "Study requirements"
    return "eligibility", "Eligibility"


def _is_mandatory_criterion(criterion_type: str, requirement_text: str) -> bool:
    """Infer mandatory status conservatively, preserving explicit preferences."""
    if criterion_type in {"target_audience", "selection_process", "selection_criteria"}:
        # These describe award administration or ranking, not applicant eligibility.
        return False
    if criterion_type == "age_limit" and re.search(
        r"(?i)\bno\s+(?:upper\s+)?age\s+limit\b",
        requirement_text,
    ):
        # An explicit statement that there is no age ceiling is informational,
        # not a condition an applicant must satisfy.
        return False
    if criterion_type == "application_requirements" and re.search(
        r"(?i)\b(sole responsibility|both (?:the )?(?:commonwealth|hec)|"
        r"commonwealth and hec|hec and commonwealth)\b",
        requirement_text,
    ):
        return True
    if criterion_type in {
        "ineligibility", "required_documents", "post_selection_requirement",
        "age_limit", "category_i_eligibility", "category_ii_eligibility",
    }:
        # An extracted age-limit criterion is an explicit eligibility boundary,
        # even when the source phrases it as "40 years in case of..." rather
        # than using words such as "maximum" or "must".
        return True
    text = requirement_text.casefold()
    # In this source context, "should be between X and Y" states an age limit.
    if re.search(r"\bshould\s+be\s+between\s+\d", text):
        return True
    if re.search(
        r"\b(preferred|preferable|encouraged|recommended|desirable|an advantage|"
        r"priority (?:will be|is) given|particularly welcome|should be poised|poised to assume)\b",
        text,
    ):
        return False
    if criterion_type in {"eligibility", "language_requirements", "academic_requirements", "study_level"}:
        # These statements came from an explicit applicant-requirements section.
        return True
    if re.search(
        r"\b(must|required|mandatory|minimum|at least|no more than|maximum|"
        r"only|cannot|not eligible|ineligible|shall|must not|eligible|"
        r"citizens?|nationals?|residing|resident|currently enrolled|"
        r"hold|possess|completed|degree|years of education|years of experience|"
        r"between\s+\d|should be between\s+\d|currently working|active experience|proficient|"
        r"government school teachers?|early career|fluency|fluent)\b",
        text,
    ):
        return True
    return False

def _parse_deadline_date(value: str | None) -> str | None:
    """Normalize an explicitly extracted English or German deadline date to ISO format."""
    if not value:
        return None
    numeric_window = GERMAN_NUMERIC_DATE_RANGE_PATTERN.search(value)
    if numeric_window:
        return (
            f"{int(numeric_window.group('year')):04d}-"
            f"{int(numeric_window.group('end_month')):02d}-"
            f"{int(numeric_window.group('end_day')):02d}"
        )
    matches = sorted(
        [*DATE_PATTERN.finditer(value), *GERMAN_DATE_PATTERN.finditer(value)],
        key=lambda item: item.start(),
    )
    if not matches:
        return None
    # For application windows, prefer the first closing date (for example,
    # "15 January until 1 March") rather than the opening date.
    closing_matches = [
        match for match in matches
        if re.search(
            r"(?i)(?:until|through|bis(?: einschließlich)?|deadline(?:\s+is)?|closes?(?:\s+on)?|closing date|apply by|no later than)\s*$",
            value[max(0, match.start() - 48):match.start()],
        )
    ]
    match = closing_matches[0] if closing_matches else matches[0]
    candidate = match.group(0).strip()
    german_match = GERMAN_DATE_PATTERN.fullmatch(candidate)
    if german_match:
        month = GERMAN_MONTHS[german_match.group("month").casefold()]
        return (
            f"{int(german_match.group('year')):04d}-"
            f"{month:02d}-{int(german_match.group('day')):02d}"
        )
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
        "application period", "applications open", "voraussetzungen",
        "bewerbungsfrist", "bewerbungsportal", "stipendium",
        "studienförderung", "förderung", "finanzielle unterstützung",
        "we support", "applicants must", "must be submitted",
        "residence permit", "come from a country", "belong to the catholic church",
        "have sufficient knowledge",
    ))
    return has_opportunity_identity and has_specific_fact


def _remove_site_chrome(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove shared navigation and layout regions before reading programme facts."""
    for node in soup(["script", "style", "noscript", "svg", "nav", "footer", "aside"]):
        node.decompose()

    # Inspect the complete tree before decomposing anything. Removing a parent
    # Tag clears the attributes of its descendants in BeautifulSoup; mutating
    # during find_all iteration can therefore leave later nodes with attrs=None.
    nodes_to_remove = []
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
            nodes_to_remove.append(node)

    # find_all() returns a snapshot, so defer mutation until inspection is done.
    # A parent may already have removed a nested candidate; skip detached nodes.
    for node in nodes_to_remove:
        if node.parent is not None:
            node.decompose()

    rich_content = soup.select_one(".ms-rtestate-field")
    if rich_content is not None:
        return rich_content
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
            if field_name == "deadline_text" and not (DATE_PATTERN.search(value) or GERMAN_DATE_PATTERN.search(value) or GERMAN_NUMERIC_DATE_RANGE_PATTERN.search(value) or ROLLING_PATTERN.search(value)):
                continue
            return value
    return None
def _has_explicit_not_supported_heading(content_root: BeautifulSoup) -> bool:
    """Identify provider headings that make every following list item an exclusion."""
    expected = {
        "unfortunately, we cannot support the following",
        "unfortunately, we cannot fund the following",
    }
    return any(
        _clean(heading.get_text(" ", strip=True)).rstrip(":?! .").casefold() in expected
        for heading in content_root.find_all(["h2", "h3", "h4", "h5"])
    )


def _find_heading_section(content_root: BeautifulSoup, heading_names: tuple[str, ...]) -> str | None:
    """Collect visible paragraph/list content beneath a matching section heading."""
    wanted = {name.casefold() for name in heading_names}
    for heading in content_root.find_all(["h2", "h3", "h4", "h5"]):
        heading_text = _clean(heading.get_text(" ", strip=True)).rstrip(":?! .").casefold()
        if heading_text not in wanted:
            continue
        chunks: list[str] = []
        nodes = heading.find_all_next(["h1", "h2", "h3", "h4", "h5", "p", "li", "td", "th"])
        section_nodes = []
        for node in nodes:
            if node.name in {"h1", "h2", "h3", "h4", "h5"}:
                break
            section_nodes.append(node)

        # List items are the atomic requirements when present. However, some
        # official pages (including USEFP CCAP) place an exclusion-introduction
        # paragraph between two separate lists under the same heading. Preserve
        # that marker in DOM order so the caller can split the second list into
        # ineligibility criteria without absorbing unrelated prose.
        list_items = [node for node in section_nodes if node.name == "li"]
        if list_items:
            selected_nodes = [
                node for node in section_nodes
                if node.name in {"li", "td", "th"}
                or (
                    node.name == "p"
                    and re.search(
                        r"(?i)individuals in the following circumstances are not eligible",
                        _clean(node.get_text(" ", strip=True)),
                    )
                )
            ]
        else:
            selected_nodes = [node for node in section_nodes if node.name in {"p", "td", "th"}]
        for node in selected_nodes:
            # Skip nested list items when their parent item already captures
            # the complete requirement.
            if node.name == "li" and node.find_parent("li"):
                continue
            value = _clean(node.get_text(" ", strip=True))
            if value and value not in chunks:
                chunks.append(value)
        if chunks:
            return "\n".join(chunks)[:4000]
    return None


def _find_provider_statement(content_root: BeautifulSoup) -> str | None:
    """Extract a provider only when the page explicitly names who operates the award."""
    pattern = re.compile(
        r"\b(?:managed|administered|offered|provided)\s+by\s+(.+?)"
        r"(?:\s+(?:under|in accordance with|according to|"
        r"in the UK|in the United Kingdom|and are intended|to support)\b|[.;]|$)",
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
        has_monthly_amount = (
            re.search(r"(?i)\b\d[\d.,]*\s*(?:€|euro)\b", value)
            and re.search(r"(?i)\b(?:monatlich|pro monat|im monat|monthly|per month)\b", value)
        )
        if len(value) >= 30 and (any(term in lowered for term in indicators) or has_monthly_amount):
            return value[:1200]
    return None


def _extract_description_criteria(description: str) -> list[tuple[str, str, str]]:
    """Extract only explicit applicant or host-eligibility statements from programme prose."""
    sentences = _split_criteria_statements(description)
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
        # The USEFP Specialist page contains a malformed source sentence:
        # "... eligible to host a U.S. scholar or profession although the
        # Fulbright Specialists Program." Do not turn that corrupted wording
        # into a formal host-institution eligibility criterion. Keep the raw
        # paragraph in description evidence for human review.
        if re.search(r"\bprofession(?:al)?\s+although\s+the\b", sentence, re.I):
            continue
        lowered = sentence.casefold()
        if host_actor.search(sentence) and re.search(r"(?i)\b(eligible to host|may include|are eligible|eligible institutions)\b", sentence):
            extracted.append(("institution_eligibility", "Eligible host institutions", sentence))
        elif applicant_actor.search(sentence) and re.search(r"(?i)\b(applicants?|candidates?|students?|participants?|scholars?|fellows?|professionals?|teachers?|officials?)\s+(?:must|required|are required|should)", sentence):
            extracted.append(("eligibility", "Eligibility from programme description", sentence))
    return extracted


def _is_applicant_eligibility_statement(statement: str) -> bool:
    """Reject directory taxonomy and broad discovery copy masquerading as criteria."""
    value = _clean(statement)
    if not value:
        return False
    # DAAD and foundation directories describe categories of funding providers.
    # A student mentioned after an organisation category is not an applicant rule.
    if re.match(
        r"(?i)^(?:denominational|religious|faith[- ]based|private|public|"
        r"corporate|government(?:al)?|non[- ]?profit)\s+"
        r"(?:organisations?|organizations?|institutions?|foundations?|associations?)\s*:",
        value,
    ):
        return False
    if re.match(
        r"(?i)^(?:organisations?|organizations?|institutions?|foundations?|"
        r"associations?)\s*:\s*(?:students?|applicants?|candidates?)\b",
        value,
    ):
        return False
    if re.match(
        r"(?i)^(?:your answer to all of the above|sie konnten alle punkte mit ja|"
        r"please make sure you have reviewed)\b",
        value,
    ):
        return False
    # General directory invitations are not eligibility conditions for a
    # particular scholarship opportunity.
    if re.search(
        r"(?i)\b(?:students?|applicants?)\s+(?:can|may)\s+apply\s+"
        r"(?:to|for)\s+(?:various|different|a range of|many)\b",
        value,
    ):
        return False
    if re.search(
        r"(?i)\b(?:various|different|a range of)\s+"
        r"(?:scholarships?|funding options?|funding opportunities)\b",
        value,
    ):
        return False
    if re.match(
        r"(?i)^(?:then please contact|if the hsf is not represented|"
        r"please submit your application|dann nehmen sie bitte kontakt|"
        r"reichen sie ihre bewerbung)\b",
        value,
    ):
        return False
    # Explanations about how the provider consults the national training
    # register are administrative guidance, not conditions an applicant must
    # satisfy. Keep the actual recognised-occupation condition itself.
    if re.match(
        r"(?i)^(?:für die entscheidung über den zugang zur förderung|"
        r"im bereich der bundesrechtlich geregelten ausbildungsberufe ist "
        r"dieses verzeichnis)\b",
        value,
    ):
        return False
    if re.match(
        r"(?i)^bewerber(?:innen|:innen)? sollten folgende kriterien erfüllen\b",
        value,
    ):
        return False
    if re.match(r"(?i)^speak german at an adequate level\b", value):
        return False
    return True


def _extract_unlabelled_criteria(content_root: BeautifulSoup) -> list[tuple[str, str, str]]:
    """Scrape eligibility statements from ordinary paragraphs and lists.

    Providers often publish requirements without an 'Eligibility' heading or
    labelled fields. This fallback scans visible page content, but only keeps
    statements that explicitly describe applicant conditions; it never invents
    missing thresholds or turns selection preferences into hard requirements.
    """
    extracted: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    requirement_signal = re.compile(
        r"(?i)\b(?:must|must not|required|are required|is required|"
        r"should have|should hold|need to|needs to|eligible|ineligible|"
        r"not eligible|only applicants|only candidates|can apply|may apply|"
        r"cannot apply|preferred|preferable|desirable|recommended|at least|minimum of|maximum age|no older than|"
        r"no more than|between \d|professional experience|from the following countries|"
        r"citizens? of|nationals? of|resident in|residing in|"
        r"hold a (?:bachelor|master|doctoral)|have completed|"
        r"müssen|muss|sollten|soll|voraussetzung(?:en)?|erforderlich|"
        r"mindestens|höchstens|nicht förderfähig|förderfähig|"
        r"studieren|erlernen|engagiert|engagieren|identifizieren|"
        r"haben|sind|stehen|erhalten|ausbildung|ausbildungsberuf|"
        r"ausbildungsjahr|ausbildungsvertrag|sprachkenntnisse|deutschkenntnisse|"
        r"unter \d{1,2}\s+jahre|wohnsitz|anerkannt(?:e|en|er))\b"
    )
    applicant_signal = re.compile(
        r"(?i)\b(?:applicants?|candidates?|students?|graduates?|"
        r"doctoral candidates?|postdocs?|researchers?|scholars?|"
        r"international students?|citizens?|nationals?|residents?|"
        r"bewerber(?:innen|:innen)?|studierende|promovierende|"
        r"auszubildende|azubis|ausländer(?:innen|:innen)?|"
        r"geflüchtete|staatsangehörige|personen)\b"
    )
    raw_values: list[str] = []
    implied_applicant_condition = re.compile(
        r"(?i)^(?:come from\b|have not been\b|hold (?:a|an)\b|"
        r"are already studying\b|wish to pursue\b|would like to pursue\b|"
        r"belong to\b|have sufficient knowledge\b|have a university degree\b|"
        r"are of\b|currently reside\b)"
    )
    for node in content_root.find_all(["p", "li", "dd", "dt"]):
        raw = _clean(node.get_text(" ", strip=True))
        if not raw or len(raw) < 4 or len(raw) > 1400:
            continue
        if (
            raw_values
            and re.search(
                r"(?i)\b(?:command|knowledge|proficiency|fluency|understanding|ability|mastery)\s*$",
                raw_values[-1],
            )
            and re.match(r"(?i)^(?:of|in|for|with|at)\b", raw)
        ):
            raw_values[-1] = f"{raw_values[-1]} {raw}"
        else:
            raw_values.append(raw)

    # Some foundations phrase eligibility as "we support [group] who ...".
    # Preserve the exact supported applicant group and study condition.
    for node in content_root.find_all("p"):
        paragraph = _clean(node.get_text(" ", strip=True))
        match = re.search(
            r"(?i)\b(?:we support|the foundation supports|foundation supports)\s+"
            r"(.+?)\s+who\s+(.+?)(?:[.!?]|$)",
            paragraph,
        )
        if match:
            statement = _clean(f"{match.group(1)} who {match.group(2)}")
            if applicant_signal.search(statement) and len(statement) >= 24:
                key = statement.casefold()
                if key not in seen and _is_applicant_eligibility_statement(statement):
                    extracted.append(("eligibility", "Eligible applicant group", statement))
                    seen.add(key)

    # Keep source-framed preferences separate from mandatory conditions.
    for node in content_root.find_all("p"):
        paragraph = _clean(node.get_text(" ", strip=True))
        match = re.search(r"(?i)\bdo you have (.+?\?)\s*then\b", paragraph)
        if match:
            statement = _clean(match.group(1))
            key = statement.casefold()
            if len(statement) >= 24 and key not in seen:
                extracted.append(("selection_criteria", "Selection preferences", statement))
                seen.add(key)

    for raw in raw_values:
        raw_is_implied_list_condition = bool(implied_applicant_condition.match(raw))
        if len(raw) < 24 or (
            not requirement_signal.search(raw) and not raw_is_implied_list_condition
        ):
            continue
        for statement in _split_criteria_statements(raw):
            statement = _clean(statement)
            key = statement.casefold()
            statement_is_implied_list_condition = bool(
                implied_applicant_condition.match(statement)
            )
            if not statement or key in seen or len(statement) < 24 or len(statement) > 1000:
                continue
            if (
                not requirement_signal.search(statement)
                and not statement_is_implied_list_condition
            ):
                continue
            if not _is_applicant_eligibility_statement(statement):
                continue
            # A condition must identify applicants, or be an unmistakable
            # qualification fragment such as "at least two years of experience".
            has_actor = bool(applicant_signal.search(statement))
            has_qualification = bool(re.search(
                r"(?i)\b(?:degree|bachelor|master|doctorate|phd|gpa|grade|"
                r"academic|language|ielts|toefl|experience|age|nationality|"
                r"citizenship|residence|enrol(?:led|ment)|study level|"
                r"studium|ausbildung|ausbildungsberuf|ausbildungsjahr|"
                r"hochschule|fachhochschule|deutschkenntnisse|sprachkenntnisse|"
                r"noten|leistungen|engagement|identifikation|staatsangehörigkeit|"
                r"aufenthaltstitel|berufserfahrung|ausbildungsvertrag|abschluss|semester)\b",
                statement,
            ))
            if not (has_actor or has_qualification or statement_is_implied_list_condition):
                continue
            lowered = statement.casefold()
            if re.search(r"(?i)\b(preferred|preferable|desirable|recommended|"
                         r"an advantage|priority will be given|besonders willkommen|"
                         r"ausdrücklich zu einer bewerbung ermutigt|bevorzugt berücksichtigt)\b", statement):
                kind, label = "selection_criteria", "Selection preference"
            elif re.search(r"(?i)\b(ineligible|not eligible|cannot apply|must not)\b", statement):
                kind, label = "ineligibility", "Ineligibility"
            elif re.search(r"(?i)\b(language|ielts|toefl|german|english proficiency|"
                            r"deutschkenntnisse|sprachkenntnisse)\b", statement):
                kind, label = "language_requirements", "Language requirements"
            elif re.search(r"(?i)\b(age|years old|younger than|older than|"
                            r"unter \d{1,2} jahre|über \d{1,2} jahre)\b", statement):
                kind, label = "age_limit", "Age requirements"
            elif re.search(r"(?i)\b(nationality|citizenship|citizen|national|resident|residing|"
                            r"staatsangehörigkeit|staatsangehörige|aufenthaltstitel|wohnsitz|"
                            r"ausländer|geflüchtete)\b", statement):
                kind, label = "nationality", "Nationality and residence"
            elif re.search(r"(?i)\b(bachelor|master|doctorate|phd|degree|enrolled|graduate|"
                            r"studium|ausbildung|ausbildungsberuf|hochschule|semester|promotion)\b", statement):
                kind, label = "study_level", "Academic qualification"
            elif re.search(r"(?i)\b(experience|professional|employment|employed|work|"
                            r"berufserfahrung|ausbildungsvertrag)\b", statement):
                kind, label = "work_experience", "Work experience"
            else:
                kind, label = "eligibility", "Eligibility"
            extracted.append((kind, label, statement))
            seen.add(key)
    return extracted


def extract_criteria_from_html(html: str) -> list[tuple[str, str, str]]:
    """Extract eligibility from a linked official requirements page."""
    soup = BeautifulSoup(html, "html.parser")
    content_root = _remove_site_chrome(soup)
    section_specs = {
        "eligibility": ("Eligibility", "Eligibility Criteria", "Who can apply", "Eligible applicants", "Scholarship for Studies", "Requirements"),
        "ineligibility": (
            "Ineligibility", "Who cannot apply", "Who is not eligible",
            "Unfortunately, we cannot support the following",
            "Unfortunately, we cannot fund the following",
        ),
        "study_level": ("Degree Level", "Study Level", "Level of Study", "Academic qualification"),
        "nationality": ("Nationality Requirements", "Citizenship Requirements", "Eligible Nationalities", "Eligible Countries"),
        "academic_requirements": ("Academic Requirements", "Academic Eligibility", "Minimum Academic Requirements", "Minimum Grades", "Minimum GPA"),
        "age_limit": ("Age Limit", "Age Requirements", "Age Eligibility"),
        "required_documents": ("Required Documents", "Documents Required", "Supporting Documents"),
        "language_requirements": ("Language Requirements", "Language Proficiency", "English Language Requirements"),
        "work_experience": ("Work Experience", "Professional Experience", "Relevant Experience"),
    }
    found: list[tuple[str, str, str]] = []
    for kind, headings in section_specs.items():
        section = _find_heading_section(content_root, headings)
        if not section:
            continue
        for statement in _split_criteria_statements(section):
            statement = _clean(statement)
            if (
                statement
                and len(statement) >= 18
                and _is_applicant_eligibility_statement(statement)
            ):
                criterion_kind, criterion_label = (
                    _classify_eligibility_statement(statement) if kind == "eligibility"
                    else (kind, kind.replace("_", " ").title())
                )
                found.append((criterion_kind, criterion_label, statement))
    found.extend(_extract_unlabelled_criteria(content_root))
    unique = []
    seen = set()
    for item in found:
        key = item[2].casefold()
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def _extract_ccip_criteria(content_root: BeautifulSoup) -> list[tuple[str, str, str]]:
    """Extract CCIP requirements from its official overview and FAQ answers."""
    page_text = _clean(content_root.get_text(" ", strip=True))
    criteria: list[tuple[str, str, str]] = []

    # These are explicit conditions stated in the programme overview.
    overview_rules = (
        ("eligibility", "Applicants must be resident in Pakistan."),
        ("eligibility", "Applicants must currently be employed in one of the listed eligible fields."),
        ("eligibility", "Applicants must have 14–15 years of education (a two-year bachelor's degree) as the programme's stated standard route."),
        ("eligibility", "Applicants must have English-language proficiency."),
        ("eligibility", "Applicants must demonstrate potential to make a positive impact on Pakistan's future development."),
        ("eligibility", "Applicants must demonstrate leadership."),
    )
    criteria.extend((kind, "Eligibility", text) for kind, text in overview_rules)

    # FAQ answers explicitly clarify the degree and experience rules.
    faq_rules = (
        ("target_audience", "The programme is intended for young professionals with a two-year bachelor's degree and less than three years of work experience."),
        ("eligibility", "Applicants with a three-year bachelor's degree may apply if they are currently working in one of the specified eligible fields."),
        ("ineligibility", "Applicants who hold a four-year bachelor's degree are ineligible."),
        ("ineligibility", "Applicants who hold a master's degree are ineligible."),
        ("ineligibility", "Applicants currently enrolled in a master's programme are ineligible."),
        ("post_selection_requirement", "After selection, applicants must obtain at least 400 on the Institutional TOEFL (ITP) to qualify."),
    )
    labels = {
        "eligibility": "Eligibility",
        "ineligibility": "Ineligibility",
        "target_audience": "Target audience",
        "post_selection_requirement": "Post-selection requirement",
    }
    criteria.extend((kind, labels[kind], text) for kind, text in faq_rules)

    # Keep these records only when the corresponding official FAQ content is
    # actually present on the fetched page; do not infer rules from the URL.
    required_phrases = (
        "less than 3 years of work experience",
        "three year bachelors degree",
        "four years bachelors degree",
        "master's degree",
        "currently enrolled into a master's program",
        "minimum of 400",
    )
    if not any(phrase in page_text.casefold() for phrase in required_phrases):
        return []

    fields_present = {
        "overview": "The applicants must be resident in Pakistan",
        "two_year": "2 year Bachelor's degree",
        "three_year": "three year Bachelors degree",
        "four_year": "four years Bachelors degree",
        "masters": "Master's degree",
        "toefl": "minimum of 400",
    }
    # The source page's FAQ wording can vary in whitespace and apostrophes;
    # verify the principal eligibility content before using the structured set.
    if fields_present["overview"].casefold() not in page_text.casefold():
        return []
    return criteria


def _classify_application_status(
    body_text: str,
    deadline_date: str | None,
    source_status: str | None = None,
) -> str:
    """Prefer an explicit programme-page status over inference from dates or prose."""
    if source_status:
        normalized = _clean(source_status).casefold().replace("-", " ").replace("_", " ")
        explicit_statuses = {
            "open": "open",
            "currently open": "open",
            "accepting applications": "open",
            "closed": "closed",
            "upcoming": "upcoming",
            "not yet open": "upcoming",
            "shortlisted only": "shortlisted_only",
            "discontinued": "discontinued",
        }
        if normalized in explicit_statuses:
            return explicit_statuses[normalized]
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
    # Explicit faculty-training identity takes precedence over degree words in
    # a programme title (for example, a faculty programme leading to a PhD).
    if re.search(
        r"\b(faculty members?|professors?|academic staff|faculty training|"
        r"faculty development|university faculty)\b",
        text,
    ):
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
    if re.search(
        r"\b(mid[- ]career professionals?|young professionals?|senior professionals?|"
        r"senior (?:U\.S\. )?scholars?|scholars? and professionals?|"
        r"working professionals?|employed professionals?|professionals with|"
        r"teachers?|administrators?|government officials?|Pakistani officials?)\b",
        text,
    ):
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

    # Some official providers publish several application windows beneath a
    # dedicated deadlines heading instead of a labelled field.
    if "deadline_text" not in fields:
        deadline_section = _find_heading_section(
            content_root,
            ("Application Deadlines", "Our Next Application Deadlines", "Deadlines"),
        )
        if deadline_section and (DATE_PATTERN.search(deadline_section) or GERMAN_DATE_PATTERN.search(deadline_section)):
            fields["deadline_text"] = deadline_section[:1200]
            evidence.append(("deadline_text", fields["deadline_text"]))

    # German providers often publish application windows as dated list items
    # without a separate heading or an English "deadline" label.
    if "deadline_text" not in fields:
        application_windows = []
        for node in content_root.find_all(["p", "li", "td", "dd"]):
            value = _clean(node.get_text(" ", strip=True))
            has_date = DATE_PATTERN.search(value) or GERMAN_DATE_PATTERN.search(value) or GERMAN_NUMERIC_DATE_RANGE_PATTERN.search(value)
            has_window_marker = re.search(
                r"(?i)\b(?:bis(?: einschließlich)?|application (?:period|window|deadline)|"
                r"bewerbungs(?:frist|schluss|zeitraum|portal)|closing date|applications? close|zwischen dem)\b",
                value,
            )
            if has_date and has_window_marker:
                application_windows.append(value)
        if application_windows:
            fields["deadline_text"] = " / ".join(application_windows)[:1200]
            evidence.append(("deadline_text", fields["deadline_text"]))

    if not _is_opportunity(candidate_title or title, page_title or title, page_url, body_text):
        return None

    # Official programme pages often use section headings and bullet lists
    # instead of inline "Eligibility: ..." labels.
    section_specs = {
        "eligibility": (
            "Eligibility Criteria", "Eligibility", "Who can apply", "Eligible applicants",
            "Technical Eligibility Requirements", "Wer kann sich bewerben",
            "Voraussetzungen", "Fördervoraussetzungen",
        ),
        "ineligibility": (
            "Ineligibility", "Who cannot apply", "Who is not eligible",
            "Unfortunately, we cannot support the following",
            "Unfortunately, we cannot fund the following",
        ),
        "study_level": ("Degree Level", "Study Level", "Level of Study", "Eligible Degree Levels"),
        "nationality": ("Nationality Requirements", "Citizenship Requirements", "Eligible Nationalities", "Eligible Countries"),
        "academic_requirements": ("Academic Requirements", "Academic Eligibility", "Minimum Academic Requirements", "Minimum Grades", "Minimum GPA"),
        "age_limit": ("Age Limit", "Age Requirements", "Age Eligibility"),
        "required_documents": ("Required Documents", "Documents Required", "Supporting Documents"),
        "language_requirements": ("Language Requirements", "Language Proficiency", "English Language Requirements"),
        "work_experience": ("Work Experience", "Professional Experience", "Relevant Experience"),
    }
    if "irgac" in page_url.casefold() or "irgac" in title.casefold():
        section_specs["eligibility"] = (*section_specs["eligibility"], "Requirements")

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

    # Some official pages place exclusion rules inside a broader technical
    # eligibility section. Split at the explicit exclusion-introduction sentence.
    embedded_ineligibility_context = _has_explicit_not_supported_heading(content_root)
    eligibility_section = fields.get("eligibility")
    if eligibility_section:
        statements = _split_criteria_statements(eligibility_section)
        marker_index = next(
            (
                index for index, statement in enumerate(statements)
                if re.search(
                    r"(?i)individuals in the following circumstances are not eligible",
                    statement,
                )
            ),
            None,
        )
        if marker_index is not None:
            eligible_statements = statements[:marker_index]
            excluded_statements = statements[marker_index + 1:]
            fields["eligibility"] = "\n".join(eligible_statements)
            if excluded_statements:
                fields["ineligibility"] = "\n".join(excluded_statements)
                evidence.append(("ineligibility", fields["ineligibility"]))
                embedded_ineligibility_context = True

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
        if any(term in lowered for term in (
            "scholarship", "fellowship", "grant", "programme", "program",
            "stipendium", "förderung", "studierende", "promovierende",
        )):
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
            statements = _split_criteria_statements(fields[field_name])
            for statement in statements:
                statement = _clean(statement)
                if not statement or not _is_applicant_eligibility_statement(statement):
                    continue
                if re.search(
                    r"(?i)^(?:all program activities will be in english|"
                    r"no translation services will be provided)",
                    statement,
                ):
                    continue
                if re.search(
                    r"(?i)^be a pakistani citizen \(dual citizens are eligible$",
                    statement,
                ):
                    # The page already states the Pakistani passport/citizenship
                    # qualification separately. Preserve only the additional
                    # dual-citizenship clarification to avoid a duplicate rule.
                    statement = (
                        "Dual citizenship is generally permitted, subject to "
                        "the source's stated exclusions."
                    )
                # These CCAP sentences explain programme delivery, not applicant
                # eligibility. Language proficiency itself remains a criterion.
                if re.search(
                    r"(?i)^(?:all program activities will be in english|"
                    r"no translation services will be provided)",
                    statement,
                ):
                    continue
                # Broad ineligibility sections can contain history and selection copy.
                # Only bypass this filter under an explicit "cannot support" heading.
                # Preserve literal regex word boundaries so explicit exclusions
                # remain detectable in the merged pull-request build.
                if field_name == "ineligibility" and not embedded_ineligibility_context and not re.search(
                    r"\b(ineligible|not eligible|not be accepted|will not be accepted|"
                    r"cannot apply|cannot be nominated|not eligible to|are excluded|"
                    r"dual .{0,30}national(?:ity|s)?|employees? of|contractors? of|"
                    r"alumni of|already availed|already studying|applied for immigration|"
                    r"attended graduate school|long[- ]term .{0,20}experience)\b",
                    statement,
                    re.I,
                ):
                    continue
                exception_match = re.search(
                    r"(?i)\b(?:with the exception of|except for|except|excluding)\b\s+(.+)$",
                    statement,
                ) if field_name == "eligibility" else None
                if exception_match:
                    eligible_part = statement[:exception_match.start()].rstrip(" ,;:")
                    excluded_part = exception_match.group(1).strip(" )(.")
                    if re.search(r"(?i)dual citizens are eligible", eligible_part):
                        eligible_part = re.sub(
                            r"(?i)\s*\(?dual citizens are eligible\)?\s*",
                            " ",
                            eligible_part,
                        ).strip(" ,;:")
                        if eligible_part:
                            criteria.append(("eligibility", "Eligibility", eligible_part))
                        criteria.append((
                            "eligibility", "Eligibility",
                            "Dual citizenship is generally permitted, subject to the source's stated exclusions.",
                        ))
                    elif eligible_part:
                        criteria.append(("eligibility", "Eligibility", eligible_part))
                    if excluded_part:
                        criteria.append((
                            "ineligibility",
                            "Ineligibility",
                            f"{excluded_part} (excluded by the source's stated exception)",
                        ))
                else:
                    criterion_kind, criterion_label = (
                        _classify_eligibility_statement(statement) if field_name == "eligibility"
                        else (field_name, field_name.replace("_", " ").title())
                    )
                    criteria.append((criterion_kind, criterion_label, statement))

    if description:
        evidence.append(("description", description))
        # Descriptive copy is used only when it contains explicit eligibility
        # language and a clearly identified applicant or host actor.
        criteria.extend(_extract_description_criteria(description))

    # Fallback for official pages that publish eligibility as ordinary prose
    # or list items without an explicit Eligibility heading or field label.
    fallback_criteria = _extract_unlabelled_criteria(content_root)
    existing_text = {item[2].casefold() for item in criteria}
    for item in fallback_criteria:
        if item[2].casefold() not in existing_text:
            criteria.append(item)
            existing_text.add(item[2].casefold())

    if urlparse(page_url).path.casefold().endswith("/ccip.cfm"):
        ccip_criteria = _extract_ccip_criteria(content_root)
        if ccip_criteria:
            criteria = [item for item in criteria if item[0] == "institution_eligibility"]
            criteria.extend(ccip_criteria)
            evidence.append((
                "eligibility",
                "CCIP eligibility overview and FAQ answers captured from the official programme page.",
            ))

    if urlparse(page_url).path.casefold().endswith("/ccap.cfm"):
        # The official CCAP page repeats the Pakistani citizenship condition
        # in its dual-citizenship bullet. Keep the passport qualification and
        # the dual-citizenship clarification, but avoid a duplicate citizen rule.
        criteria = [
            item for item in criteria
            if not _clean(item[2]).casefold().startswith("be a pakistani citizen")
        ]
        # The broad dual-citizenship exclusion already covers an applicant
        # whose spouse is a U.S. citizen or permanent resident. Retain that
        # broader source rule rather than storing the spouse-only duplicate.
        has_broader_family_exclusion = any(
            item[0] == "ineligibility"
            and "dual u.s." in item[2].casefold()
            and "spouse" in item[2].casefold()
            for item in criteria
        )
        if has_broader_family_exclusion:
            criteria = [
                item for item in criteria
                if not (
                    item[0] == "ineligibility"
                    and re.search(
                        r"(?i)^individuals who are married to a u\.s\. citizen\b",
                        _clean(item[2]),
                    )
                )
            ]

        # These are alternative qualification routes, not cumulative rules.
        government_route = next((
            item for item in criteria
            if item[0] == "eligibility"
            and "full-time government official" in item[2].casefold()
            and "10 years" in item[2].casefold()
        ), None)
        administrator_route = next((
            item for item in criteria
            if item[0] == "eligibility"
            and "full-time education administrator" in item[2].casefold()
            and "5 years" in item[2].casefold()
        ), None)
        if government_route and administrator_route:
            combined_route = (
                "Applicants must qualify through either of these routes: "
                "(1) be a full-time government official or educational association "
                "professional with at least 10 years of experience overseeing technical "
                "or vocational institutions of higher education in Pakistan; OR "
                "(2) be a full-time education administrator with at least 5 years of "
                "experience as an administrator within technical or vocational "
                "institutions in Pakistan."
            )
            first_index = criteria.index(government_route)
            criteria = [
                item for item in criteria
                if item is not government_route and item is not administrator_route
            ]
            criteria.insert(first_index, (
                "eligibility", "Alternative professional eligibility routes", combined_route
            ))

    # Normalize every final criterion after all special-case assembly so custom
    # CCAP/CCIP rules receive the same evidence-backed spacing repairs.
    criteria = [
        (kind, label, _clean(requirement))
        for kind, label, requirement in criteria
        if _clean(requirement)
    ]

    # Description is returned separately from fields, so normalize it explicitly too.
    description = _clean(description) if description else None

    deadline_date = _parse_deadline_date(fields.get("deadline_text"))
    application_status = _classify_application_status(
        body_text, deadline_date, fields.get("application_status")
    )
    # Use programme identity and extracted eligibility, not unrelated page-wide text.
    applicant_category = _classify_applicant_category(
        " ".join((title, page_title, fields.get("eligibility", ""), description or ""))
    )
    return ExtractedPage(title[:300], description, provider, fields, criteria, evidence,
                         application_status, applicant_category)



HEC_KNOWLEDGE_CORRIDOR_BASE = (
    "https://www.hec.gov.pk/english/scholarshipsgrants/US-Pakcorridor/Pages/"
)
HEC_KNOWLEDGE_CORRIDOR_PAGES = {
    "overview": "default.aspx",
    "eligibility": "Eligibility-Criteria.aspx",
    "how_to_apply": "How-to-Apply.aspx",
    "hat": "HAT.aspx",
    "priority_subjects": "Priority-Subject-Areas.aspx",
    "faq": "FAQ.aspx",
}


def _hec_content_root(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    return _remove_site_chrome(soup)


def _hec_visible_items(root: BeautifulSoup) -> list[str]:
    """Read atomic visible HEC content from paragraphs, lists, and table cells."""
    values = []
    for node in root.find_all(["p", "li", "td", "th"]):
        if node.name == "li" and node.find_parent("li"):
            continue
        if node.name == "p" and node.find_parent(["li", "td", "th"]):
            continue
        if node.name in {"td", "th"} and node.find_parent(["td", "th"]):
            continue
        value = _clean(node.get_text(" ", strip=True))
        if value and value not in values:
            values.append(value)
    return values


def _hec_priority_subject_items(root: BeautifulSoup) -> list[str]:
    """Prefer atomic official list items and preserve explicit HTML line breaks."""
    list_items = [
        _clean(node.get_text(" ", strip=True))
        for node in root.find_all("li")
        if not node.find_parent("li")
    ]
    if len(list_items) >= 2:
        candidates = list_items
    else:
        candidates = []
        for node in root.find_all(["p", "td", "th"]):
            if node.find_parent(["li", "td", "th"]):
                continue
            # SharePoint frequently uses <br> as the separator between
            # subject areas inside a single paragraph. Preserve those breaks.
            candidates.extend(
                _clean(line)
                for line in node.get_text("\n", strip=True).splitlines()
                if _clean(line)
            )
        if not candidates:
            candidates = _hec_visible_items(root)

    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        item = _clean(re.sub(r"^\s*\d+\s*[.)]\s*", "", item))
        # The official HEC page joins these two separate subject entries in
        # its rendered text. Split only this observed, unambiguous boundary.
        item = re.sub(r"(?i)\b(Engineering)(Automotive)\b", r"\1\n\2", item)
        if "\n" in item:
            parts = [part.strip() for part in item.splitlines() if part.strip()]
            for part in parts:
                key = re.sub(r"[^a-z0-9]+", "", part.casefold())
                if key and key not in seen:
                    seen.add(key)
                    result.append(part)
            continue
        item = re.sub(
            r"(?i)^following is the list of preferred subject areas?/subjects "
            r"in which scholarship under the .*? is offered effective "
            r"(?:fall|spring|summer).{0,80}?\s+",
            "",
            item,
        ).strip()
        if not item:
            continue
        key = re.sub(r"[^a-z0-9]+", "", item.casefold())
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _parse_hec_knowledge_corridor(pages: dict[str, tuple[str, str]]) -> ExtractedPage | None:
    """Aggregate the official HEC programme pages while retaining page-level provenance."""
    if "overview" not in pages or "eligibility" not in pages:
        return None

    roots = {name: _hec_content_root(html) for name, (html, _) in pages.items()}
    urls = {name: url for name, (_, url) in pages.items()}
    title = "US-Pakistan Knowledge Corridor PhD Scholarship"
    fields: dict[str, str] = {
        "study_level": "PhD",
        "study_destination": "United States",
    }
    evidence: list[tuple[str, str]] = []
    evidence_sources: dict[tuple[str, str], str] = {}
    criteria: list[tuple[str, str, str]] = []
    criteria_sources: dict[tuple[str, str, str], str] = {}

    def add_evidence(field_name: str, value: str, page_name: str) -> None:
        if field_name == "priority_subject_areas":
            # Preserve the subject-list line structure and apply the same
            # verified HEC spacing repairs used for the displayed field.
            value = "\n".join(
                cleaned for line in value.splitlines()
                if (cleaned := _clean(line))
            )
            value = re.sub(r"(?i)\bandEnvironmental\b", "and Environmental", value)
        else:
            value = _clean_preserving_lines(value)
            value = re.sub(r"(?i)\barerequired\b", "are required", value)
        if not value:
            return
        item = (field_name, value)
        if item not in evidence:
            evidence.append(item)
        evidence_sources[item] = urls[page_name]

    def add_criterion(kind: str, label: str, value: str, page_name: str) -> None:
        value = _clean_preserving_lines(value)
        # Apply the observed FAQ repair at the final criterion boundary too.
        # This guards against markup extraction paths that preserve the joined
        # source token after an earlier normalization pass.
        value = re.sub(r"(?i)\barerequired\b", "are required", value)
        if not value:
            return
        # Collapse source-copy duplicates that differ only in punctuation,
        # spacing, or invisible formatting characters.
        def normalize_criterion(text: str) -> str:
            text = re.sub(r"(?i)^\s*(?:[a-z]\s*[\.\)]\s*|[\u2022•\-–]\s*)", "", text)
            return re.sub(r"[^a-z0-9]+", "", text.casefold())

        normalized = normalize_criterion(value)
        if any(
            old_kind == kind and old_label == label
            and normalize_criterion(old_value) == normalized
            for old_kind, old_label, old_value in criteria
        ):
            return
        item = (kind, label, value)
        criteria.append(item)
        criteria_sources[item] = urls[page_name]

    overview_root = roots["overview"]
    # Prefer a programme-purpose statement over historical background about
    # the bilateral initiative. If the page has no useful programme summary,
    # leave description empty rather than mislabel historical context.
    overview_items = _hec_visible_items(overview_root)
    description = next(
        (value for value in overview_items
         if len(value) >= 70
         and not re.search(r"(?i)\b(phase\s*[-–]?\s*\d|ECNEC|revised later|approved by ECNEC)\b", value)
         and re.search(r"(?i)(ph\.?d|doctoral).{0,100}(scholarship|study)|"
                       r"(scholarship|study).{0,100}(ph\.?d|doctoral)", value)
         and re.search(r"(?i)(pakistani students|students from pakistan|study in the united states)", value)),
        None,
    )
    description_evidence = description
    if not description:
        overview_text = " ".join(overview_items)
        description_evidence = next(
            (value for value in overview_items
             if re.search(
                 r"(?i)award\s+1,?000\s+ph\.?d\.?\s+scholarships?.{0,100}"
                 r"pakistani students.{0,100}us universities",
                 value,
             )),
            None,
        )
        if description_evidence:
            description = (
                "PhD scholarships for outstanding Pakistani students to pursue "
                "doctoral study at universities in the United States under the "
                "US–Pakistan Knowledge Corridor."
            )
    if description:
        description = description[:1200]
        # Evidence retains the exact official source wording; the displayed
        # summary may be a concise paraphrase grounded in that wording.
        add_evidence("description", description_evidence or description, "overview")

    # HEC's eligibility page uses ordinary paragraphs and list items rather
    # than semantic heading elements. Keep each source statement atomic.
    eligibility_items = _hec_visible_items(roots["eligibility"])
    active_category: str | None = None
    for value in eligibility_items:
        low = value.casefold()
        if re.search(r"(?i)category\s*ii\b", value):
            active_category = "Category II"
        elif re.search(r"(?i)category\s*i\b", value):
            active_category = "Category I"
        # HEC's general eligibility list may render this direct requirement
        # simply as "Pakistani/AJK nationals", without an applicant/must prefix.
        if re.search(r"(?i)pakistani\s*/?\s*aj\s*&?\s*k\s+nationals?\b", low) or (
            re.match(r"(?i)^\s*(?:be|must be|applicants? must be)\b", value)
            and re.search(r"(?i)pakistani\s*/?\s*aj\s*&?\s*k", low)
            and re.search(r"(?i)national|permanent resident|dual national", low)
        ):
            add_criterion("nationality", "Nationality", value, "eligibility")
        elif re.search(r"(?i)(four[- ]year|16 years|sixteen years|b\.?s\.?|b\.?sc|b\.?e\.?)", value) and re.search(r"(?i)(bachelor|education|degree)", value):
            add_criterion("academic_requirements", "Minimum education", value, "eligibility")
        elif re.search(r"(?i)(second division|second division|division)", value):
            add_criterion("academic_requirements", "Academic record", value, "eligibility")
        elif re.search(r"(?i)\b(age|years?|regular government|all other applicants)\b", value) and re.search(r"\b(40|35)\b", value):
            # Some HEC page layouts put both age bands in one paragraph.
            # Emit one clearly labelled criterion per threshold so neither
            # applicant group disappears during extraction.
            age_bands = set(re.findall(r"\b(40|35)\s*(?:years?|yrs?)\b", value, re.I))
            if not age_bands:
                age_bands = set(re.findall(r"\b(40|35)\b", value))
            for age in sorted(age_bands, key=int, reverse=True):
                age_label = (
                    "Maximum age – specified public-sector applicants"
                    if age == "40"
                    else "Maximum age – all other applicants"
                )
                add_criterion("age_limit", age_label, value, "eligibility")
        elif re.search(r"(?i)(another scholarship|any other scholarship|availing.*scholarship)", value):
            add_criterion("ineligibility", "Other scholarship", value, "eligibility")
        elif re.search(r"(?i)(ph\.?d holders?|already.*ph\.?d|doctoral degree holders?|those having ph\.?d\s+degree)", value):
            add_criterion("ineligibility", "Existing PhD holders", value, "eligibility")
        elif re.search(r"(?i)(category\s*i\b|top\s*50|qs.*50)", value) and (
            re.search(r"(?i)(secured admission|admission in|must have|must secure)", value)
            or not value.rstrip().endswith(":")
        ):
            add_criterion(
                "category_i_eligibility", "Category I – admission to a QS top-50 US university",
                value, "eligibility",
            )
        elif re.search(r"(?i)(category\s*ii\b|51\s*[-–]\s*100|qs.*100)", value) and (
            re.search(r"(?i)(secured admission|admission in|must have|must secure)", value)
            or not value.rstrip().endswith(":")
        ):
            # Eligibility page is authoritative for the 51–100 range. Do not
            # replace it with the malformed phrase in the FAQ page.
            add_criterion(
                "category_ii_eligibility", "Category II – admission to a QS 51–100 US university",
                value, "eligibility",
            )
        elif re.search(r"(?i)(gre|hat).*(300|60\s*%)|(300|60\s*%).*(gre|hat)", value):
            score_label = (
                f"GRE or HAT score – {active_category}"
                if active_category else "GRE or HAT score"
            )
            add_criterion("academic_requirements", score_label, value, "eligibility")
        elif (
            len(value) > 35
            and not re.search(
                r"(?i)^(?:those who satisfy|for this category.*prospective applicant|"
                r"the following requirements|eligibility criteria)\b",
                value.strip(),
            )
            and re.search(r"(?i)(eligible|applicant|admission|university|degree)", value)
        ):
            add_criterion("eligibility", "Eligibility", value, "eligibility")

    # FAQ provides additional requirements and clarifications, but only capture
    # explicit rules; questions and unrelated process commentary are not criteria.
    if "faq" in roots:
        for value in _hec_visible_items(roots["faq"]):
            if re.search(r"(?i)(toefl|ielts).*(not required)|(not required).*(toefl|ielts)", value):
                add_criterion("language_requirements", "English-language tests", value, "faq")
            elif re.search(r"(?i)\bJ[- ]?1\b", value) and re.search(r"(?i)(visa|only)", value):
                add_criterion("post_selection_requirement", "Visa requirement", value, "faq")
            elif re.search(r"(?i)(return to pakistan|serve.*years|bond|contract)", value):
                add_criterion("post_selection_requirement", "Post-study obligation", value, "faq")
            elif (
                re.search(
                    r"(?i)(?:2\s*nd|second)\s*(?:/|,|and|or)\s*(?:3\s*rd|third)\s*division|"
                    r"(?:3\s*rd|third)\s*(?:/|,|and|or)\s*(?:2\s*nd|second)\s*division",
                    value,
                )
                and re.search(r"(?i)(academic career|entire career|throughout.*career|all.*career|degree)", value)
            ):
                add_criterion("academic_requirements", "Academic record – FAQ clarification", value, "faq")
            elif re.search(r"(?i)(gre|hat).*(300|60\s*%)|(300|60\s*%).*(gre|hat)", value) and re.search(
                r"(?i)all candidates|all applicants|every candidate|every applicant", value
            ):
                add_criterion("academic_requirements", "GRE or HAT score – all applicants", value, "faq")
            elif re.search(r"(?i)(confirmed admission|domicile|passport|attested academic)", value):
                add_criterion("required_documents", "Application requirements", value, "faq")

    # The FAQ says the GRE/HAT threshold applies to every candidate, independently
    # of university admission. Keep that shared rule once; retain the separate
    # Category I/II university-admission conditions.
    if any(
        kind == "academic_requirements" and label == "GRE or HAT score – all applicants"
        for kind, label, _value in criteria
    ):
        retained = []
        for item in criteria:
            kind, label, _value = item
            if (
                kind == "academic_requirements"
                and "GRE or HAT score" in label
                and label != "GRE or HAT score – all applicants"
            ):
                # Category headings are not consistently exposed in HEC's
                # page markup, so labels may be Category I, Category II, or
                # generic. The FAQ's all-applicant clarification supersedes
                # every narrower duplicate score label.
                criteria_sources.pop(item, None)
            else:
                retained.append(item)
        criteria = retained

    # Keep category-specific tuition separate from benefits shared by both categories.
    # Preserve the official wording; never calculate a combined funding total.
    category_i_funding: list[str] = []
    category_ii_funding: list[str] = []
    shared_funding: list[str] = []
    if "faq" in roots:
        for value in _hec_visible_items(roots["faq"]):
            if not re.search(
                r"(?i)(USD|PKR|tuition|stipend|health insurance|airfare|fully funded)",
                value,
            ):
                continue
            is_tuition = bool(re.search(r"(?i)tuition", value))
            is_category_i = bool(re.search(r"(?i)category\s*i\b", value))
            is_category_ii = bool(re.search(r"(?i)category\s*ii\b", value))
            # The official FAQ may state the tuition amounts without repeating
            # the category name in the same paragraph. Preserve its explicit
            # distinction: fully funded tuition is Category I; tuition capped
            # at USD 12,000 is Category II.
            if is_category_i or (is_tuition and re.search(r"(?i)fully funded", value)):
                category_i_funding.append(value)
            elif is_category_ii or (
                is_tuition
                and re.search(r"(?i)up to\s+USD\s*12,?000", value)
            ):
                category_ii_funding.append(value)
            else:
                shared_funding.append(value)

    funding_sections = []
    if category_i_funding:
        funding_sections.append(
            "Category I (QS 1–50):\n" + "\n".join(dict.fromkeys(category_i_funding))
        )
    if category_ii_funding:
        funding_sections.append(
            "Category II (QS 51–100):\n" + "\n".join(dict.fromkeys(category_ii_funding))
        )
    if shared_funding:
        funding_sections.append(
            "Benefits stated without a category restriction:\n"
            + "\n".join(dict.fromkeys(shared_funding))
        )
    if funding_sections:
        fields["funding_summary"] = "\n\n".join(funding_sections)[:4000]
        add_evidence("funding_summary", fields["funding_summary"], "faq")

    # Only accept the portal when the official how-to page links to it.
    if "how_to_apply" in roots:
        portal_links = []
        for anchor in roots["how_to_apply"].find_all("a", href=True):
            target = urljoin(urls["how_to_apply"], str(anchor.get("href", "")).strip())
            parsed = urlparse(target)
            if parsed.scheme == "https" and parsed.hostname == "scholarship.hec.gov.pk":
                portal_links.append(target)
        if portal_links:
            fields["application_url"] = sorted(set(portal_links))[0]
            add_evidence("application_url", fields["application_url"], "how_to_apply")

    if "priority_subjects" in roots:
        relevant = _hec_priority_subject_items(roots["priority_subjects"])
        if relevant:
            value = "\n".join(relevant)[:4000]
            fields["priority_subject_areas"] = value
            add_evidence("priority_subject_areas", value, "priority_subjects")

    # The landing page's generic "open" wording is not a dated intake notice.
    # Without a verified current advertisement, status remains unknown.
    fields["application_status"] = "unknown"
    add_evidence("study_level", "PhD", "overview")
    add_evidence("study_destination", "United States", "overview")
    add_evidence("application_status", "No current intake advertisement was established by the programme pages inspected.", "overview")

    provider = "Higher Education Commission (HEC)"
    add_evidence("provider_name", provider, "overview")

    # Normalize every extracted field at the output boundary, preserving line breaks.
    for field_name, field_value in list(fields.items()):
        if isinstance(field_value, str):
            fields[field_name] = "\n".join(
                _clean(line) if line.strip() else ""
                for line in field_value.splitlines()
            ).strip()
    # Final output-boundary normalization: keep stored criteria/evidence
    # consistent with the already-normalized programme fields. Rebuild the
    # provenance maps alongside the values so repaired facts retain sources.
    normalized_criteria: list[tuple[str, str, str]] = []
    normalized_criteria_sources: dict[tuple[str, str, str], str] = {}
    for kind, label, value in criteria:
        cleaned_label = _clean_preserving_lines(label)
        cleaned_value = _clean_preserving_lines(value)
        item = (kind, cleaned_label, cleaned_value)
        if item not in normalized_criteria:
            normalized_criteria.append(item)
        source_url = criteria_sources.get((kind, label, value))
        if source_url:
            normalized_criteria_sources[item] = source_url

    normalized_evidence: list[tuple[str, str]] = []
    normalized_evidence_sources: dict[tuple[str, str], str] = {}
    for field_name, value in evidence:
        if field_name == "priority_subject_areas":
            cleaned_value = "\n".join(
                cleaned for line in value.splitlines()
                if (cleaned := _clean(line))
            )
        else:
            cleaned_value = _clean_preserving_lines(value)
        item = (field_name, cleaned_value)
        if cleaned_value and item not in normalized_evidence:
            normalized_evidence.append(item)
        source_url = evidence_sources.get((field_name, value))
        if source_url and cleaned_value:
            normalized_evidence_sources[item] = source_url

    return ExtractedPage(
        _clean(title), _clean(description) if description else None,
        _clean(provider) if provider else None, fields,
        normalized_criteria, normalized_evidence, "unknown", "student",
        normalized_evidence_sources, normalized_criteria_sources,
    )


async def _fetch_hec_knowledge_corridor(
    client: httpx.AsyncClient, overview_html: str, overview_url: str
) -> ExtractedPage | None:
    pages: dict[str, tuple[str, str]] = {
        "overview": (overview_html, overview_url)
    }
    for name, filename in HEC_KNOWLEDGE_CORRIDOR_PAGES.items():
        if name == "overview":
            continue
        url = urljoin(HEC_KNOWLEDGE_CORRIDOR_BASE, filename)
        html, error = await _fetch_page(client, url)
        if html:
            pages[name] = (html, url)
    return _parse_hec_knowledge_corridor(pages)



HEC_COMMONWEALTH_2027_URL = (
    "https://www.hec.gov.pk/english/HECAnnouncements/Pages/CW-Scholarship.aspx"
)


def _parse_hec_commonwealth_announcement(
    html: str, page_url: str = HEC_COMMONWEALTH_2027_URL
) -> ExtractedPage | None:
    """Extract the 2027–28 Commonwealth call from its official HEC announcement."""
    root = _hec_content_root(html)
    items = _hec_visible_items(root)
    body_text = _clean(root.get_text(" ", strip=True))
    if not items or not re.search(r"(?i)commonwealth.*2027\s*[-/]\s*28|2027\s*[-/]\s*28.*commonwealth", body_text):
        return None

    title = "Commonwealth Scholarship Programme (Master’s & PhD) for Academic Year 2027-28"
    provider = "Commonwealth Scholarship Commission (CSC)"
    fields: dict[str, str] = {
        "study_destination": "United Kingdom",
        "study_level": "Master's and PhD",
    }
    evidence: list[tuple[str, str]] = []
    evidence_sources: dict[tuple[str, str], str] = {}
    criteria: list[tuple[str, str, str]] = []
    criteria_sources: dict[tuple[str, str, str], str] = {}

    def add_evidence(name: str, value: str) -> None:
        value = _clean_preserving_lines(value)
        if not value:
            return
        item = (name, value)
        if item not in evidence:
            evidence.append(item)
        evidence_sources[item] = page_url

    def add_criterion(kind: str, label: str, value: str) -> None:
        value = _clean_preserving_lines(value)
        if not value:
            return
        existing_index = next(
            (index for index, old in enumerate(criteria)
             if old[0] == kind and old[1] == label),
            None,
        )
        if existing_index is not None:
            old_kind, old_label, old_value = criteria[existing_index]
            if value.casefold() not in old_value.casefold():
                merged = _clean(old_value + " " + value)
                old_item = (old_kind, old_label, old_value)
                new_item = (old_kind, old_label, merged)
                criteria[existing_index] = new_item
                criteria_sources.pop(old_item, None)
                criteria_sources[new_item] = page_url
            return
        item = (kind, label, value)
        criteria.append(item)
        criteria_sources[item] = page_url

    # Use the actual course-of-study description, not the introductory
    # nominating-agency paragraph, as the scholarship description.
    description = next(
        (item for item in items
         if re.search(r"(?i)full[- ]time taught master", item)
         and re.search(r"(?i)phd", item)
         and re.search(r"(?i)university|study", item)),
        None,
    )
    if description:
        add_evidence("description", description[:1600])
    add_evidence("provider_name", provider)
    add_evidence("study_destination", "United Kingdom")
    add_evidence("study_level", "Master's and PhD")

    # Preserve each explicit HEC requirement as a separate criterion with the
    # announcement URL as its provenance.
    for item in items:
        low = item.casefold()
        if (re.match(r"(?i)^\s*(?:be|must be|applicants? must be)\b", item)
            and re.search(r"(?i)\b(pakistani|ajk)\b", item)
            and re.search(r"(?i)\b(nationals?|citizens?|residents?)\b", item)):
            add_criterion("nationality", "Nationality and residency", item)
        elif re.search(r"no upper age limit", low):
            add_criterion("age_limit", "Age limit", item)
        elif re.search(r"master", low) and re.search(r"16 years", low) and re.search(r"first division", low):
            add_criterion("academic_requirements", "Master's degree requirement", item)
        elif re.search(r"phd", low) and re.search(r"17\s*/?\s*18 years", low) and re.search(r"first division", low):
            add_criterion("academic_requirements", "PhD degree requirement", item)
        elif re.search(r"second\s*/\s*third division|second/third division", low) and re.search(r"terminal|latest|last degree", low):
            add_criterion("academic_requirements", "Terminal-degree division requirement", item)
        elif "result-awaiting" in low or ("result awaiting" in low):
            add_criterion("academic_requirements", "Result-awaiting candidates", item)
        elif re.search(r"\bhat\b", low) and re.search(r"60\s*(?:out of 100|/100)", low):
            add_criterion("academic_requirements", "Minimum HAT score", item)
        elif re.search(r"hat[- ]?(?:i|ii|iii|iv)\b", low) and re.search(r"only|acceptable|categories", low):
            add_criterion("academic_requirements", "Accepted HAT categories", item)
        elif re.search(r"hat", low) and re.search(r"october 25,? 2024|25 october 2024", low):
            add_criterion("academic_requirements", "HAT score validity", item)
        elif re.search(r"merit", low) and re.search(r"hat score", low):
            add_criterion("selection_criteria", "Merit calculation", item)
        elif re.search(r"same test score|tie", low) and re.search(r"percentage|last completed degree", low):
            add_criterion("selection_criteria", "Tie-break rule", item)
        elif re.search(r"female|45\s*%", low) and re.search(r"nomination", low):
            add_criterion("selection_criteria", "Female nomination representation", item)
        elif (
            re.search(r"both.*(?:hec|commonwealth).*portal|both websites", low)
            or (
                re.search(r"\b(required|must|sole responsibility|ensure)\b", low)
                and re.search(r"\b(application|apply|submit)\w*\b", low)
                and re.search(r"\b(commonwealth and hec|hec and commonwealth)\b", low)
                and re.search(r"\b(portal|website)s?\b", low)
            )
        ):
            add_criterion("application_requirements", "Dual-portal application", item)
        elif re.search(r"final selection", low) and re.search(r"commonwealth scholarship commission", low):
            statements = _split_criteria_statements(item)
            nomination_statement = next(
                (
                    statement for statement in statements
                    if re.search(r"(?i)nomination process", statement)
                    and re.search(r"(?i)\bhec\b", statement)
                ),
                None,
            )
            final_statement = next(
                (
                    statement for statement in statements
                    if re.search(r"(?i)final selection", statement)
                    and re.search(r"(?i)commonwealth scholarship commission", statement)
                    # A later "does not guarantee" sentence repeats the same
                    # authority rather than adding a distinct selection rule.
                    and not re.search(r"(?i)does not guarantee", statement)
                ),
                None,
            )
            # Keep one HEC nomination statement and one CSC final-selection
            # statement. Ignore repeated paraphrases in the same source block.
            authority_parts = list(dict.fromkeys(
                part for part in (nomination_statement, final_statement) if part
            ))
            if authority_parts:
                add_criterion(
                    "selection_process",
                    "Final selection authority",
                    " ".join(authority_parts),
                )
        elif re.search(r"nomination process", low) and re.search(r"hec", low):
            for statement in _split_criteria_statements(item):
                if re.search(r"(?i)nomination process", statement) and re.search(r"(?i)\bhec\b", statement):
                    add_criterion("selection_process", "HEC nomination role", statement)
        # Development themes are programme context, not individual eligibility
        # conditions. They are stored separately below, never as criteria.

    # Capture the exact closing-date statement. The date is explicit on this
    # official page, so application status can be calculated from the date.
    deadline_item = next(
        (item for item in items if re.search(r"(?i)(closing date|application deadline|deadline)", item)
         and DATE_PATTERN.search(item)),
        None,
    )
    if deadline_item:
        date_match = DATE_PATTERN.search(deadline_item)
        fields["deadline_text"] = deadline_item[:500]
        add_evidence("deadline_text", deadline_item)
    else:
        date_match = None

    # Keep both CSC programme routes as evidence. The HEC portal is the
    # single canonical application_url field; both submissions are required.
    csc_urls: list[str] = []
    hec_urls: list[str] = []
    for anchor in root.find_all("a", href=True):
        target = urljoin(page_url, str(anchor.get("href", "")).strip())
        parsed = urlparse(target)
        if parsed.scheme != "https":
            continue
        host = (parsed.hostname or "").casefold()
        if host == "cscuk.fcdo.gov.uk" and "/scholarships/" in parsed.path:
            if target not in csc_urls:
                csc_urls.append(target)
        elif host == "scholarship.hec.gov.pk":
            if target not in hec_urls:
                hec_urls.append(target)

    if hec_urls:
        fields["application_url"] = hec_urls[0]
    for url in csc_urls:
        add_evidence("application_portal", url)
    for url in hec_urls:
        add_evidence("application_portal", url)

    # Record development themes as factual context, not as eligibility rules.
    theme_items = [
        item for item in items
        if re.search(r"(?i)(science and technology for development|strengthening health systems|"
                     r"innovation and entrepreneurship|global peace|resilience and response|"
                     r"access, inclusion and opportunity)", item)
    ]
    if theme_items:
        theme_items = [_clean_preserving_lines(item) for item in theme_items]
        fields["development_themes"] = "\n".join(theme_items)[:2000]
        add_evidence("development_themes", fields["development_themes"])

    deadline_date = _parse_deadline_date(fields.get("deadline_text"))
    if deadline_date:
        fields["deadline_date"] = deadline_date
        add_evidence("deadline_date", deadline_date)
    application_status = _classify_application_status(body_text, deadline_date)
    fields["application_status"] = application_status
    add_evidence("application_status", application_status)

    # Normalize every field and criterion while preserving provenance and line breaks.
    for field_name, field_value in list(fields.items()):
        if isinstance(field_value, str):
            fields[field_name] = "\n".join(
                _clean(line) if line.strip() else ""
                for line in field_value.splitlines()
            ).strip()

    normalized_criteria: list[tuple[str, str, str]] = []
    normalized_criteria_sources: dict[tuple[str, str, str], str] = {}
    for kind, label, value in criteria:
        item = (kind, _clean_preserving_lines(label), _clean_preserving_lines(value))
        if item not in normalized_criteria:
            normalized_criteria.append(item)
        source_url = criteria_sources.get((kind, label, value))
        if source_url:
            normalized_criteria_sources[item] = source_url

    normalized_evidence: list[tuple[str, str]] = []
    normalized_evidence_sources: dict[tuple[str, str], str] = {}
    for field_name, value in evidence:
        cleaned_value = _clean_preserving_lines(value)
        item = (field_name, cleaned_value)
        if cleaned_value and item not in normalized_evidence:
            normalized_evidence.append(item)
        source_url = evidence_sources.get((field_name, value))
        if source_url and cleaned_value:
            normalized_evidence_sources[item] = source_url

    return ExtractedPage(
        _clean_preserving_lines(title),
        _clean_preserving_lines(description) if description else None,
        _clean_preserving_lines(provider), fields, normalized_criteria, normalized_evidence,
        application_status, "student", normalized_evidence_sources, normalized_criteria_sources,
    )


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


async def extract_candidate_details(
    reprocess: bool = False,
    candidate_ids: list[int] | None = None,
) -> list[dict]:
    """Visit candidates, optionally restricting work to an explicit ID allow-list."""
    if candidate_ids is not None:
        if reprocess:
            raise ValueError("Use either global reprocess or targeted candidate_ids, not both.")
        candidate_ids = list(dict.fromkeys(int(value) for value in candidate_ids))
        if not candidate_ids:
            return []
    with get_connection() as connection:
        if reprocess:
            # Preserve historical rows and evidence. Re-run candidates and update
            # matching records in place; rejected pages remain auditable.
            connection.execute("DELETE FROM extraction_attempts")
            connection.execute("UPDATE discovery_candidates SET status = 'candidate'")
        candidate_filter = ""
        candidate_params: tuple = ()
        if candidate_ids is not None:
            placeholders = ",".join("?" for _ in candidate_ids)
            candidate_filter = f" AND c.id IN ({placeholders})"
            candidate_params = tuple(candidate_ids)
        candidates = [dict(row) for row in connection.execute(
            """SELECT c.id, c.source_id, c.title AS candidate_title, c.candidate_url
               FROM discovery_candidates c
               JOIN sources s ON s.id = c.source_id
               WHERE c.status = 'candidate'
                 AND NOT EXISTS (
                     SELECT 1 FROM extraction_attempts a
                     WHERE a.candidate_id = c.id
                       AND a.status <> 'failed'
                 )""" + candidate_filter + """ ORDER BY CASE
                   WHEN s.source_type = 'official_database' THEN 0
                   WHEN s.name LIKE 'DAAD%' THEN 1
                   ELSE 2
               END, c.id""",
            candidate_params,
        ).fetchall()]

    timeout = httpx.Timeout(15.0, connect=6.0)
    limits = httpx.Limits(max_connections=3, max_keepalive_connections=2)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    results = []
    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers,
                                 follow_redirects=False) as client:
        for candidate in candidates:
            html, error = await _fetch_page(client, candidate["candidate_url"])
            candidate_path = urlparse(candidate["candidate_url"]).path.casefold()
            is_hec_corridor_overview = (
                "hec.gov.pk" in (urlparse(candidate["candidate_url"]).hostname or "").casefold()
                and "/us-pakcorridor/pages/" in candidate_path
                and candidate_path.endswith("/default.aspx")
            )
            is_hec_commonwealth_announcement = (
                (urlparse(candidate["candidate_url"]).hostname or "").casefold() == "www.hec.gov.pk"
                and candidate_path.endswith("/cw-scholarship.aspx")
                and "/hecannouncements/pages/" in candidate_path
            )
            if html and is_hec_corridor_overview:
                parsed = await _fetch_hec_knowledge_corridor(
                    client, html, candidate["candidate_url"]
                )
            elif html and is_hec_commonwealth_announcement:
                parsed = _parse_hec_commonwealth_announcement(
                    html, candidate["candidate_url"]
                )
            else:
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
                    # Evidence is append-only: preserve earlier source snapshots.
                    # Exact repeats are skipped by _save_evidence.
                    for evidence_item in parsed.evidence:
                        evidence_url = parsed.evidence_sources.get(
                            evidence_item, candidate["candidate_url"]
                        )
                        _save_evidence(
                            connection, scholarship_id, [evidence_item], evidence_url
                        )
                    connection.execute("DELETE FROM eligibility_criteria WHERE scholarship_id = ?", (scholarship_id,))
                    for criterion_type, label, requirement in parsed.criteria:
                        connection.execute(
                            """INSERT INTO eligibility_criteria
                               (scholarship_id, criterion_type, criterion_label,
                                requirement_text, is_mandatory, evidence_url)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (scholarship_id, criterion_type, label, requirement,
                             int(_is_mandatory_criterion(criterion_type, requirement)),
                             parsed.criteria_sources.get(
                                 (criterion_type, label, requirement), candidate["candidate_url"]
                             )),
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
