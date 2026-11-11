import unittest

from app.extraction import ExtractedPage
from app.live_discovery import _as_record, _opportunity_id


class LiveDiscoveryRecordTests(unittest.TestCase):
    def test_live_record_contains_extracted_facts_and_source_evidence(self):
        page = ExtractedPage(
            title="International Student Scholarship",
            description="Support for eligible international students.",
            provider_name="Example German Foundation",
            fields={
                "funding_summary": "Monthly stipend",
                "deadline_text": "December 15, 2027",
                "study_destination": "Germany",
                "application_url": "https://provider.example/apply",
            },
            criteria=[
                ("nationality", "Nationality", "International applicants may apply."),
            ],
            evidence=[("funding_summary", "Monthly stipend")],
            application_status="open",
            applicant_category="student",
            evidence_sources={("funding_summary", "Monthly stipend"): "https://provider.example/funding"},
            criteria_sources={
                ("nationality", "Nationality", "International applicants may apply."):
                    "https://provider.example/eligibility"
            },
        )
        source = {
            "name": "Example German Foundation",
            "country": "Germany",
            "official_url": "https://provider.example/scholarships",
            "source_type": "official_programme",
        }

        record = _as_record(page, source, "https://provider.example/scholarship")

        self.assertEqual(record["title"], "International Student Scholarship")
        self.assertEqual(record["provider_name"], "Example German Foundation")
        self.assertEqual(record["deadline_date"], "2027-12-15")
        self.assertEqual(record["application_status"], "open")
        self.assertEqual(record["criteria"][0]["evidence_url"], "https://provider.example/eligibility")
        self.assertEqual(record["evidence"][0]["evidence_url"], "https://provider.example/funding")
        self.assertEqual(record["status"], "unverified")

    def test_live_ids_are_stable_and_do_not_require_database_ids(self):
        url = "https://provider.example/scholarship"
        self.assertEqual(_opportunity_id(url), _opportunity_id(url))
        self.assertIsInstance(_opportunity_id(url), int)


class SourcePagePromotionTests(unittest.TestCase):
    def test_directory_sources_are_never_promoted_as_individual_scholarships(self):
        from app.live_discovery import _is_promotable_source_page

        record = {"title": "Funding Opportunities from other Organisations"}
        for source_type in ("official_index", "official_database", "government", "university"):
            with self.subTest(source_type=source_type):
                self.assertFalse(
                    _is_promotable_source_page(record, {"source_type": source_type})
                )

    def test_generic_provider_landing_titles_are_rejected(self):
        from app.live_discovery import _is_promotable_source_page

        for title in (
            "Welcome",
            "Scholarship Providers",
            "Scholarships by Target Group and Stage of University Education",
            "Scholarship Programmes for Pakistan",
            "Studienwerk",
            "Scholarship Department",
            "Scholarships & Funding",
            "The Most Important Domestic Scholarship Programmes:",
        ):
            with self.subTest(title=title):
                self.assertFalse(
                    _is_promotable_source_page(
                        {"title": title}, {"source_type": "official_programme"}
                    )
                )

    def test_named_programme_page_can_be_promoted(self):
        from app.live_discovery import _is_promotable_source_page

        self.assertTrue(
            _is_promotable_source_page(
                {"title": "Tailwind for Talents: Scholarships for Graduates and PhD students"},
                {"source_type": "official_programme"},
            )
        )


    def test_eligibility_links_include_german_provider_requirements_pages(self):
        from app.live_discovery import _eligibility_links

        html = """
        <html><body><main>
          <a href="/stipendium/wen-suchen-wir/">Weitere Informationen</a>
          <a href="/contact/">Contact</a>
        </main></body></html>
        """
        self.assertEqual(
            _eligibility_links(html, "https://www.hss.de/stipendium/"),
            ["https://www.hss.de/stipendium/wen-suchen-wir/"],
        )


if __name__ == "__main__":
    unittest.main()
