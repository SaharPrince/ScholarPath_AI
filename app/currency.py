"""Indicative daily currency conversions using ExchangeRate-API Open Access.

The provider's raw rate table stays server-side. The public API returns only the
requested pair conversion, source attribution, and update timestamps.
"""
from __future__ import annotations

import asyncio
import copy
import math
from datetime import datetime, timezone
from time import monotonic

import httpx


RATE_URL = "https://open.er-api.com/v6/latest/PKR"
SOURCE_URL = "https://www.exchangerate-api.com/docs/free"
SOURCE_NAME = "ExchangeRate-API (Open Access)"
CACHE_FALLBACK_SECONDS = 24 * 60 * 60
MAX_RATE_AGE_SECONDS = 72 * 60 * 60
_REQUEST_TIMEOUT_SECONDS = 10

_cache: dict | None = None
_cache_expires_at = 0.0
_cache_lock = asyncio.Lock()


class CurrencyRateUnavailable(RuntimeError):
    """Raised when no usable exchange-rate snapshot is available."""


def _utc_from_unix(value: object, field: str) -> datetime:
    try:
        is_finite = math.isfinite(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else False
    except (OverflowError, TypeError, ValueError):
        is_finite = False
    if not is_finite:
        raise CurrencyRateUnavailable(f"The exchange-rate provider returned an invalid {field} time.")
    try:
        parsed = datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise CurrencyRateUnavailable(f"The exchange-rate provider returned an invalid {field} time.") from exc
    if parsed.timestamp() <= 0:
        raise CurrencyRateUnavailable(f"The exchange-rate provider returned an invalid {field} time.")
    return parsed


def parse_rate_response(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("result") != "success":
        raise CurrencyRateUnavailable("The exchange-rate provider did not return a successful response.")
    if payload.get("base_code") != "PKR" or not isinstance(payload.get("rates"), dict):
        raise CurrencyRateUnavailable("The exchange-rate provider returned an unexpected base currency.")

    updated = _utc_from_unix(payload.get("time_last_update_unix"), "last update")
    next_update = _utc_from_unix(payload.get("time_next_update_unix"), "next update")
    now = datetime.now(timezone.utc)
    if updated > now.replace(microsecond=0):
        raise CurrencyRateUnavailable("The exchange-rate provider returned a future update time.")
    if next_update <= updated:
        raise CurrencyRateUnavailable("The exchange-rate provider returned an invalid refresh schedule.")

    rates = {"PKR": 1.0}
    for code, raw_rate in payload["rates"].items():
        if not isinstance(code, str) or len(code) != 3 or not code.isalpha():
            continue
        if isinstance(raw_rate, bool) or not isinstance(raw_rate, (int, float)):
            continue
        try:
            rate = float(raw_rate)
        except (OverflowError, TypeError, ValueError):
            continue
        if math.isfinite(rate) and 0 < rate < 1_000_000:
            rates[code.upper()] = rate
    if "EUR" not in rates or "USD" not in rates:
        raise CurrencyRateUnavailable("The exchange-rate provider omitted essential currencies.")

    return {
        "base": "PKR",
        "rates": rates,
        "rate_date": updated.date().isoformat(),
        "updated_at": updated.isoformat(),
        "next_update_at": next_update.isoformat(),
        "is_stale": (now - updated).total_seconds() > MAX_RATE_AGE_SECONDS,
    }


async def _fetch_snapshot() -> dict:
    headers = {"User-Agent": "ScholarPath-AI/1.0 (student cost-planning currency converter)"}
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        response = await client.get(RATE_URL)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise CurrencyRateUnavailable("The exchange-rate provider returned unreadable data.") from exc
    snapshot = parse_rate_response(payload)
    snapshot["source"] = {"name": SOURCE_NAME, "url": SOURCE_URL}
    return snapshot


async def get_currency_snapshot() -> dict:
    """Return an in-process cached provider snapshot; never expose it from the API."""
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
                stale["notice"] = "Showing the last successful rate snapshot because the source could not be refreshed."
                _cache_expires_at = monotonic() + 300
                return stale
            if isinstance(exc, CurrencyRateUnavailable):
                raise
            raise CurrencyRateUnavailable("The exchange-rate provider is temporarily unavailable.") from exc

        _cache = copy.deepcopy(snapshot)
        next_update = datetime.fromisoformat(snapshot["next_update_at"])
        seconds_until_refresh = max(60, (next_update - datetime.now(timezone.utc)).total_seconds())
        _cache_expires_at = monotonic() + min(seconds_until_refresh, CACHE_FALLBACK_SECONDS)
        return copy.deepcopy(_cache)


def build_conversion(snapshot: dict, amount: float, from_currency: str, to_currency: str) -> dict:
    if not isinstance(from_currency, str) or not isinstance(to_currency, str):
        raise CurrencyRateUnavailable("Choose two supported currencies.")
    source = from_currency.upper()
    target = to_currency.upper()
    rates = snapshot.get("rates", {})
    if source not in rates or target not in rates:
        raise CurrencyRateUnavailable("That currency pair is not available.")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
        raise CurrencyRateUnavailable("Enter a valid amount.")
    rate = rates[target] / rates[source]
    return {
        "amount": float(amount),
        "from_currency": source,
        "to_currency": target,
        "rate": rate,
        "converted_amount": float(amount) * rate,
        "rate_date": snapshot["rate_date"],
        "updated_at": snapshot["updated_at"],
        "next_update_at": snapshot["next_update_at"],
        "source": snapshot["source"],
        "is_stale": bool(snapshot.get("is_stale", False)),
        "notice": snapshot.get(
            "notice",
            "Indicative daily rate only. Your bank, card or transfer service may use a different rate or add fees.",
        ),
    }
