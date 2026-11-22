import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import main as api
from app.currency import (
    CurrencyRateUnavailable,
    _official_https_url,
    find_sbp_pdf_url,
    parse_ecb_xml,
    parse_sbp_rate_text,
)


class CurrencyParsingTests(unittest.TestCase):
    def test_parses_sbp_customer_rates_and_publication_date(self):
        text = """
        Weighted Average Customer Exchange Rates as on 20-Nov-26
        CURRENCY BUYING SELLING
        AED 75.2202 75.3357
        EUR 304.3672 304.8692
        USD 276.2672 276.7241
        """
        result = parse_sbp_rate_text(text)
        self.assertEqual(result["rate_date"], "2026-11-20")
        self.assertAlmostEqual(result["rates"]["EUR"]["buying"], 304.3672)
        self.assertAlmostEqual(result["rates"]["EUR"]["selling"], 304.8692)
        self.assertAlmostEqual(result["rates"]["EUR"]["mid"], (304.3672 + 304.8692) / 2)

    def test_rejects_sbp_pdf_text_without_rate_rows(self):
        with self.assertRaises(CurrencyRateUnavailable):
            parse_sbp_rate_text("The report is temporarily unavailable.")

    def test_finds_only_the_official_sbp_customer_rate_pdf(self):
        html = '''
        <a href="/assets/document/weighted-average-customer-exchange-rates-20-November-2026.pdf">
          Download
        </a>
        '''
        url = find_sbp_pdf_url(html)
        self.assertEqual(
            url,
            "https://www.sbp.org.pk/assets/document/weighted-average-customer-exchange-rates-20-November-2026.pdf",
        )

    def test_rejects_untrusted_rate_pdf_host(self):
        html = '<a href="https://example.com/weighted-average-customer-exchange-rates.pdf">PDF</a>'
        with self.assertRaises(CurrencyRateUnavailable):
            find_sbp_pdf_url(html)

    def test_rejects_non_https_or_untrusted_source_url(self):
        with self.assertRaises(CurrencyRateUnavailable):
            _official_https_url("http://www.sbp.org.pk/rates.pdf", {"www.sbp.org.pk"})
        with self.assertRaises(CurrencyRateUnavailable):
            _official_https_url("https://evil.example/rates.pdf", {"www.sbp.org.pk"})

    def test_parses_ecb_xml_reference_rates_and_date(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
          xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
          <Cube><Cube time="2026-11-20">
            <Cube currency="USD" rate="1.0990"/>
            <Cube currency="GBP" rate="0.83735"/>
          </Cube></Cube>
        </gesmes:Envelope>"""
        result = parse_ecb_xml(xml)
        self.assertEqual(result["rate_date"], "2026-11-20")
        self.assertAlmostEqual(result["rates"]["USD"], 1.0990)
        self.assertAlmostEqual(result["rates"]["GBP"], 0.83735)

    def test_rejects_ecb_xml_without_a_dated_reference_set(self):
        with self.assertRaises(CurrencyRateUnavailable):
            parse_ecb_xml("<root><rate currency='USD' rate='1.1'/></root>")


class CurrencyApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_currency_endpoint_returns_the_cached_snapshot(self):
        snapshot = {
            "base": "PKR",
            "rate_date": "2026-11-20",
            "rates": {"PKR": {"pkr_per_unit": 1.0}, "EUR": {"pkr_per_unit": 304.6}},
            "sources": [],
            "is_stale": False,
        }
        with patch("app.main.get_currency_snapshot", new=AsyncMock(return_value=snapshot)):
            result = await api.currency_rates()
        self.assertEqual(result["base"], "PKR")
        self.assertIn("EUR", result["rates"])

    async def test_currency_endpoint_returns_503_when_no_official_rates_are_available(self):
        with patch(
            "app.main.get_currency_snapshot",
            new=AsyncMock(side_effect=CurrencyRateUnavailable("offline")),
        ):
            with self.assertRaises(HTTPException) as raised:
                await api.currency_rates()
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
