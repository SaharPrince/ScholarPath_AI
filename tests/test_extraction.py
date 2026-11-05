import unittest

from app.extraction import (\n    _classify_application_status, _classify_applicant_category,\n    _parse_deadline_date, parse_scholarship_page,\n)


class ScholarshipPageExtractionTests(unittest.TestCase):
    def test_extracts_visible_facts_and_keeps_evidence(self) -> None:
        html = """
        <html><head>
          <meta name="description" content="Funding for postgraduate study.">
          <meta property="og:site_name" content="Example Foundation">
        </head><body>
          <h1>Example Global Scholarship</h1>
          <p>Scholarship provider: Example Foundation</p>
          <p>Application deadline: 30 September 2027</p>
          <p>Funding: Full tuition and monthly stipend</p>
          <p>Eligibility: Applicants must be citizens of Pakistan.</p>
        </body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.title, "Example Global Scholarship")
        self.assertEqual(page.provider_name, "Example Foundation")
        self.assertEqual(page.fields["deadline_text"], "30 September 2027")
        self.assertEqual(page.fields["funding_summary"], "Full tuition and monthly stipend")
        self.assertEqual(page.fields["eligibility"], "Applicants must be citizens of Pakistan.")
        self.assertTrue(all(snippet for _, snippet in page.evidence))

    def test_insufficient_page_returns_none(self) -> None:
        self.assertIsNone(
            parse_scholarship_page(
                "<html><body><h1>Welcome</h1><p>Contact our office.</p></body></html>",
                "https://example.org/",
            )
        )

    def test_normalizes_explicit_deadline_date(self) -> None:
        self.assertEqual(_parse_deadline_date("August 1, 2020"), "2020-08-01")
        self.assertEqual(_parse_deadline_date("30 September 2027"), "2027-09-30")


    def test_ignores_navigation_and_footer_text(self) -> None:
        html = """
        <html><body>
          <nav><p>Eligibility</p><p>University Partnerships</p></nav>
          <main>
            <h1>Example Fellowship Programme</h1>
            <p>Application deadline: 15 March 2027</p>
            <p>Eligibility: Applicants must be Pakistani citizens with a completed bachelor's degree.</p>
            <p>Funding: Full tuition and a monthly stipend.</p>
          </main>
          <footer><p>Eligibility: University Partnerships</p></footer>
        </body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/fellowship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(
            page.fields["eligibility"],
            "Applicants must be Pakistani citizens with a completed bachelor's degree.",
        )

    def test_rejects_title_like_eligibility_value(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <p>Eligibility</p>
          <p>University Partnerships</p>
          <p>Application deadline: 15 March 2027</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertNotIn("eligibility", page.fields)

    def test_does_not_invent_date_for_rolling_deadline(self) -> None:
        self.assertIsNone(_parse_deadline_date("Applications accepted throughout the year"))
        self.assertIsNone(_parse_deadline_date("All year around"))


if __name__ == "__main__":
    unittest.main()
