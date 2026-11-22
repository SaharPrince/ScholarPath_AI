"""Daily exchange-rate snapshots fetched from official central-bank publications.

Rates are indicative planning references, not executable trading quotes.
"""
from __future__ import annotations

import asyncio
import copy
import re
from datetime import datetime, timezone
from io import BytesIO
from time import monotonic
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader


SBP_INDEX_URL = "https://www.sbp.org.pk/economic-data"
ECB_XML_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
SBP_HOSTS = {"sbp.org.pk", "www.sbp.org.pk"}
ECB_HOSTS = {"ecb.europa.eu", "www.ecb.europa.eu"}
CACHE_TTL_SECONDS = 3 * 60 * 60
_REQUEST_TIMEOUT_SECONDS = 12

_cache: dict | None = None
_cache_expires_at = 0.0
_cache_lock = asyncio.Lock()


class CurrencyRateUnavailable(RuntimeError):
    """Raised when no safe, current official rate snapshot can be fetched."""


def _official_https_url(candidate: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise CurrencyRateUnavailable("The exchange-rate source returned an unexpected URL.")
    return candidate


def find_sbp_pdf_url(html: str, page_url: str = SBP_INDEX_URL) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        text = anchor.get_text(" ", strip=True)
        if "weighted-average-customer-exchange-rates" in href.lower() or (
            "weighted average customer exchange rates" in text.lower()
            and href.lower().endswith(".pdf")
        ):
            return _official_https_url(urljoin(page_url, href), SBP_HOSTS)
    raise CurrencyRateUnavailable("The State Bank of Pakistan has not exposed its latest customer-rate PDF link.")


def parse_sbp_rate_text(text: str) -> dict:
    date_match = re.search(
        r"as\s+on\s+(\d{1,2})[-\s]+([A-Za-z]{3,9})[-\s]+(\d{2,4})",
        text,
        re.IGNORECASE,
    )
    rate_date = None
    if date_match:
        day, month, year = date_match.groups()
        year = int(year)
        if year < 100:
            year += 2000
        for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
            try:
                rate_date = datetime.strptime(f"{int(day)}-{month}-{year}", fmt).date().isoformat()
                break
            except ValueError:
                continue

    number = r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)"
    row_pattern = re.compile(rf"\b([A-Z]{{3}})\s+{number}\s+{number}\b")
    rates = {}
    for match in row_pattern.finditer(text.upper()):
        code, buying, selling = match.groups()
        buying_value = float(buying.replace(",", ""))
        selling_value = float(selling.replace(",", ""))
        if 0 < buying_value < 10_000_000 and 0 < selling_value < 10_000_000:
            rates[code] = {
                "buying": buying_value,
                "selling": selling_value,
                "mid": (buying_value + selling_value) / 2,
                "source": "SBP weighted-average customer rates",
            }
    if not rates:
        raise CurrencyRateUnavailable("The State Bank of Pakistan PDF did not contain recognizable currency rows.")
    return {"rate_date": rate_date, "rates": rates}


def parse_ecb_xml(xml_text: str) -> dict:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise CurrencyRateUnavailable("The ECB reference-rate feed could not be parsed.") from exc

    rate_date = None
    rates = {}
    for element in root.iter():
        if element.tag.endswith("Cube") and element.attrib.get("time"):
            rate_date = element.attrib["time"]
        code = element.attrib.get("currency")
        value = element.attrib.get("rate")
        if code and value:
            try:
                parsed = float(value)
            except ValueError:
                continue
            if parsed > 0:
                rates[code.upper()] = parsed
    if not rate_date or "USD" not in rates:
        raise CurrencyRateUnavailable("The ECB feed did not contain a dated reference-rate set.")
    return {"rate_date": rate_date, "rates": rates}


async def _get_sbp_rates(client: httpx.AsyncClient) -> dict:
    page = await client.get(SBP_INDEX_URL)
    page.raise_for_status()
    pdf_url = find_sbp_pdf_url(page.text, str(page.url))
    pdf_response = await client.get(pdf_url)
    pdf_response.raise_for_status()
    if urlparse(str(pdf_response.url)).hostname not in SBP_HOSTS:
        raise CurrencyRateUnavailable("The State Bank PDF redirected outside its official domain.")
    try:
        reader = PdfReader(BytesIO(pdf_response.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise CurrencyRateUnavailable("The State Bank PDF could not be read.") from exc
    result = parse_sbp_rate_text(text)
    result["source_url"] = pdf_url
    return result


async def _get_ecb_rates(client: httpx.AsyncClient) -> dict:
    response = await client.get(ECB_XML_URL)
    response.raise_for_status()
    if urlparse(str(response.url)).hostname not in ECB_HOSTS:
        raise CurrencyRateUnavailable("The ECB feed redirected outside its official domain.")
    result = parse_ecb_xml(response.text)
    result["source_url"] = ECB_XML_URL
    return result


async def _fetch_snapshot() -> dict:
    headers = {"User-Agent": "ScholarCompass/1.0 (public scholarship cost-planning rates)"}
    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=headers,
    ) as client:
        sbp, ecb = await asyncio.gather(
            _get_sbp_rates(client),
            _get_ecb_rates(client),
            return_exceptions=True,
        )

    if isinstance(sbp, BaseException):
        raise CurrencyRateUnavailable("The latest SBP PKR rates are temporarily unavailable.") from sbp
    if isinstance(ecb, BaseException):
        ecb = None

    eur_pkr = sbp["rates"].get("EUR", {}).get("mid")
    if not eur_pkr:
        raise CurrencyRateUnavailable("The SBP publication did not include an EUR/PKR reference rate.")

    rates = {
        "PKR": {
            "pkr_per_unit": 1.0,
            "source": "Base currency",
            "rate_type": "identity",
        }
    }
    for code, values in sbp["rates"].items():
        rates[code] = {
            "pkr_per_unit": values["mid"],
            "buying": values["buying"],
            "selling": values["selling"],
            "source": values["source"],
            "rate_type": "SBP indicative customer rate",
        }

    sources = [{
        "name": "State Bank of Pakistan — Weighted Average Customer Exchange Rates",
        "url": sbp["source_url"],
        "rate_date": sbp["rate_date"],
    }]
    if ecb:
        # ECB quotes foreign-currency units per EUR. Convert each to PKR using
        # the SBP EUR/PKR customer midpoint; SBP-published pairs take precedence.
        for code, units_per_eur in ecb["rates"].items():
            if code not in rates and units_per_eur > 0:
                rates[code] = {
                    "pkr_per_unit": eur_pkr / units_per_eur,
                    "source": "ECB reference rate cross-calculated through EUR/PKR",
                    "rate_type": "ECB-derived indicative reference",
                }
        sources.append({
            "name": "European Central Bank — Euro foreign exchange reference rates",
            "url": ecb["source_url"],
            "rate_date": ecb["rate_date"],
        })

    return {
        "base": "PKR",
        "rate_date": sbp["rate_date"],
        "rates": rates,
        "sources": sources,
        "is_stale": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "notice": (
            "Indicative daily reference rates for planning only. Actual bank, card, "
            "cash-exchange and transfer rates may differ and may include fees."
        ),
    }


async def get_currency_snapshot() -> dict:
    global _cache, _cache_expires_at
    now = monotonic()
    if _cache is not None and now < _cache_expires_at:
        return copy.deepcopy(_cache)

    async with _cache_lock:
        now = monotonic()
        if _cache is not None and now < _cache_expires_at:
            return copy.deepcopy(_cache)
        try:
            snapshot = await _fetch_snapshot()
        except Exception as exc:
            if _cache is not None:
                stale = copy.deepcopy(_cache)
                stale["is_stale"] = True
                stale["notice"] += " The source could not be refreshed; showing the last successful snapshot."
                return stale
            if isinstance(exc, CurrencyRateUnavailable):
                raise
            raise CurrencyRateUnavailable("Official exchange-rate sources are temporarily unavailable.") from exc

        _cache = copy.deepcopy(snapshot)
        _cache_expires_at = monotonic() + CACHE_TTL_SECONDS
        return copy.deepcopy(_cache)
