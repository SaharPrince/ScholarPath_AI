import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import main as api
from app.currency import (
    CurrencyRateUnavailable,
    build_conversion,
    parse_rate_response,
)


def provider_payload():
    updated = int(datetime(2026, 11, 22, tzinfo=timezone.utc).timestamp())
    next_update = int(datetime(2026, 11, 23, tzinfo=timezone.utc).timestamp())
    return {
        "result": "success",
        "base_code": "PKR",
        "time_last_update_unix": updated,
        "time_next_update_unix": next_update,
        "rates": {"PKR": 1, "USD": 0.0036, "EUR": 0.0031, "GBP": 0.0027},
    }


class CurrencyParsingTests(unittest.TestCase):
    def test_parses_provider_snapshot_and_timestamps(self):
        result = parse_rate_response(provider_payload())
        self.assertEqual(result["base"], "PKR")
        self.assertEqual(result["rate_date"], "2026-11-22")
        self.assertAlmostEqual(result["rates"]["USD"], 0.0036)
        self.assertIn("next_update_at", result)

    def test_rejects_wrong_base_or_failed_provider_response(self):
        payload = provider_payload()
        payload["base_code"] = "USD"
        with self.assertRaises(CurrencyRateUnavailable):
            parse_rate_response(payload)
        with self.assertRaises(CurrencyRateUnavailable):
            parse_rate_response({"result": "error"})

    def test_rejects_missing_essential_rates(self):
        payload = provider_payload()
        payload["rates"].pop("EUR")
        with self.assertRaises(CurrencyRateUnavailable):
            parse_rate_response(payload)

    def test_rejects_non_finite_provider_timestamps(self):
        for invalid_time in (float("nan"), float("inf"), float("-inf")):
            payload = provider_payload()
            payload["time_last_update_unix"] = invalid_time
            with self.subTest(invalid_time=invalid_time):
                with self.assertRaises(CurrencyRateUnavailable):
                    parse_rate_response(payload)

    def test_rejects_invalid_provider_refresh_schedule(self):
        payload = provider_payload()
        payload["time_next_update_unix"] = payload["time_last_update_unix"]
        with self.assertRaises(CurrencyRateUnavailable):
            parse_rate_response(payload)

    def test_rejects_oversized_provider_timestamp(self):
        payload = provider_payload()
        payload["time_last_update_unix"] = 10**1000
        with self.assertRaises(CurrencyRateUnavailable):
            parse_rate_response(payload)

    def test_ignores_oversized_provider_rate(self):
        payload = provider_payload()
        payload["rates"]["BAD"] = 10**1000
        result = parse_rate_response(payload)
        self.assertNotIn("BAD", result["rates"])

    def test_ignores_invalid_rate_values(self):
        payload = provider_payload()
        payload["rates"]["BAD"] = -1
        payload["rates"]["NAN"] = float("nan")
        result = parse_rate_response(payload)
        self.assertNotIn("BAD", result["rates"])
        self.assertNotIn("NAN", result["rates"])

    def test_cross_currency_conversion_uses_pkr_base_rates(self):
        snapshot = {
            "rates": {"PKR": 1.0, "USD": 0.004, "EUR": 0.003},
            "rate_date": "2026-11-22",
            "updated_at": "2026-11-22T00:00:00+00:00",
            "next_update_at": "2026-11-23T00:00:00+00:00",
            "source": {"name": "Provider", "url": "https://example.com"},
        }
        result = build_conversion(snapshot, 100, "USD", "EUR")
        self.assertAlmostEqual(result["rate"], 0.75)
        self.assertAlmostEqual(result["converted_amount"], 75)

    def test_rejects_unsupported_currency_pair(self):
        snapshot = {
            "rates": {"PKR": 1.0, "USD": 0.004},
            "rate_date": "2026-11-22",
            "updated_at": "2026-11-22T00:00:00+00:00",
            "next_update_at": "2026-11-23T00:00:00+00:00",
            "source": {"name": "Provider", "url": "https://example.com"},
        }
        with self.assertRaises(CurrencyRateUnavailable):
            build_conversion(snapshot, 1, "USD", "EUR")


class CurrencyApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_currency_endpoint_returns_only_requested_conversion(self):
        snapshot = {
            "rates": {"PKR": 1.0, "USD": 0.004, "EUR": 0.003},
            "rate_date": "2026-11-22",
            "updated_at": "2026-11-22T00:00:00+00:00",
            "next_update_at": "2026-11-23T00:00:00+00:00",
            "source": {"name": "Provider", "url": "https://example.com"},
            "is_stale": False,
        }
        with patch("app.main.get_currency_snapshot", new=AsyncMock(return_value=snapshot)):
            result = await api.currency_rates(amount=100, from_currency="USD", to_currency="EUR")
        self.assertAlmostEqual(result["converted_amount"], 75)
        self.assertNotIn("rates", result)
        self.assertEqual(result["from_currency"], "USD")

    async def test_currency_endpoint_returns_503_when_source_is_unavailable(self):
        with patch(
            "app.main.get_currency_snapshot",
            new=AsyncMock(side_effect=CurrencyRateUnavailable("offline")),
        ):
            with self.assertRaises(HTTPException) as raised:
                await api.currency_rates(amount=1, from_currency="PKR", to_currency="EUR")
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
