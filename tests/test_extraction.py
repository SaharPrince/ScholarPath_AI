import unittest

from app.extraction import (
    _classify_application_status, _classify_applicant_category,
    _parse_deadline_date, _find_application_url, parse_scholarship_page,
)


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
          <p>Funding: Full tuition award.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertNotIn("eligibility", page.fields)

    def test_does_not_invent_date_for_rolling_deadline(self) -> None:
        self.assertIsNone(_parse_deadline_date("Applications accepted throughout the year"))
        self.assertIsNone(_parse_deadline_date("All year around"))

    def test_past_deadline_marks_that_cycle_closed(self) -> None:
        self.assertEqual(_classify_application_status("Application deadline: 1 January 2020", "2020-01-01"), "closed")

    def test_future_deadline_alone_does_not_mean_open(self) -> None:
        self.assertEqual(_classify_application_status("Application deadline: 1 January 2099", "2099-01-01"), "unknown")

    def test_explicit_open_and_upcoming_language(self) -> None:
        self.assertEqual(_classify_application_status("Applications are now open", None), "open")
        self.assertEqual(_classify_application_status("Applications will open in October", None), "upcoming")

    def test_rolling_and_discontinued_statuses(self) -> None:
        self.assertEqual(_classify_application_status("Applications accepted throughout the year", None), "open")
        self.assertEqual(_classify_application_status("This programme has been discontinued", None), "discontinued")

    def test_applicant_category_requires_clear_language(self) -> None:
        self.assertEqual(_classify_applicant_category("Designed for mid-career professionals"), "professional")
        self.assertEqual(_classify_applicant_category("For currently enrolled undergraduate students"), "student")
        self.assertEqual(_classify_applicant_category("A programme for interested people"), "unknown")

    def test_extracts_heading_based_eligibility_and_prose_funding(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Master's Scholarship</h1>
          <h2>Eligibility Criteria</h2>
          <ul>
            <li>Applicants must be citizens of Pakistan.</li>
            <li>Applicants must hold a bachelor's degree.</li>
            <li>Applicants must apply for a master's programme.</li>
          </ul>
          <h2>Financial Support</h2>
          <p>The scholarship covers tuition fees and provides a stipend for living costs.</p>
          <p>Applications are now open.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/masters-scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("citizens of Pakistan", page.fields["eligibility"])
        self.assertIn("bachelor's degree", page.fields["eligibility"])
        self.assertIn("scholarship covers tuition fees", page.fields["funding_summary"])
        self.assertTrue(any(name == "eligibility" for name, _ in page.evidence))
        self.assertEqual(page.applicant_category, "student")

    def test_applicant_category_ignores_unrelated_page_references(self) -> None:
        self.assertEqual(
            _classify_applicant_category("Example Degree Scholarship for master's applicants"),
            "student",
        )
        self.assertEqual(
            _classify_applicant_category("Example scholarship for master's applicants"),
            "student",
        )

    def test_extracts_explicit_provider_and_study_destination(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Graduate Scholarship</h1>
          <p>The scholarship is managed by Example Foundation under its international programme.</p>
          <p>The scholarship funds graduate study at universities all over the United States for a Master's degree.</p>
          <p>Eligibility: Pakistani citizens with a bachelor's degree may apply.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarships/example")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.provider_name, "Example Foundation")
        self.assertEqual(page.fields["study_destination"], "United States")
        self.assertIn(("provider_name", "Example Foundation"), page.evidence)
        self.assertIn(("study_destination", "United States"), page.evidence)

    def test_extracts_explicit_application_link(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <p>Eligibility: Pakistani citizens with a bachelor's degree may apply.</p>
          <h2>How to Apply</h2>
          <p>Complete the online application.</p>
          <a href="https://apply.example.edu/start">Apply Now</a>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.fields["application_url"], "https://apply.example.edu/start")
        self.assertIn(("application_url", "https://apply.example.edu/start"), page.evidence)

    def test_does_not_treat_source_page_or_document_as_application_url(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <p>Eligibility: Pakistani citizens with a bachelor's degree may apply.</p>
          <h2>How to Apply</h2>
          <a href="#instructions">Apply</a>
          <a href="/scholarship">Apply Now</a>
          <a href="/application-guide.pdf">Application Form</a>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertNotIn("application_url", page.fields)

    def test_ambiguous_application_links_are_not_guessed(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <p>Eligibility: Pakistani citizens with a bachelor's degree may apply.</p>
          <a href="https://apply-one.example.edu">Apply Now</a>
          <a href="https://apply-two.example.edu">Apply Now</a>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertNotIn("application_url", page.fields)

    def test_deadline_only_page_is_not_promoted(self) -> None:
        html = """<html><body><main>
          <h1>Example Scholarship</h1>
          <p>Application deadline: 1 January 2020</p>
        </main></body></html>"""
        self.assertIsNone(parse_scholarship_page(html, "https://example.org/scholarship"))


if __name__ == "__main__":
    unittest.main()
