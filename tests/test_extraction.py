import unittest

from app.extraction import parse_scholarship_page


class ScholarshipPageExtractionTests(unittest.TestCase):
    def test_extracts_visible_facts_and_keeps_evidence(self) -> None:
        html = """
        <html><head>
          <meta name="description" content="Funding for postgraduate study.">
          <meta property="og:site_name" content="Example Foundation">
        </head><body>
          <h1>Example Global Scholarship</h1>
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


if __name__ == "__main__":
    unittest.main()
