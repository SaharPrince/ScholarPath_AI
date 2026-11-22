import unittest
from datetime import datetime
from dataclasses import replace

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
        self.assertIsNotNone(datetime.fromisoformat(record["last_checked_at"]))

        # When a page does not expose a provider name, retain the curated
        # official source name rather than returning an empty provider field.
        fallback_record = _as_record(replace(page, provider_name=None), source, "https://provider.example/scholarship")
        self.assertEqual(fallback_record["provider_name"], source["name"])

    def test_live_ids_are_stable_and_do_not_require_database_ids(self):
        url = "https://provider.example/scholarship"
        self.assertEqual(_opportunity_id(url), _opportunity_id(url))
        self.assertIsInstance(_opportunity_id(url), int)


class SourcePagePromotionTests(unittest.TestCase):
    def test_goettingen_programmes_are_first_in_the_bounded_priority_scan(self):
        from app.live_discovery import _priority_sources
        from app.source_catalog import GERMANY_SOURCES

        names = [source["name"] for source in _priority_sources(GERMANY_SOURCES)]
        expected = {
            "University of Göttingen – Academic Degree Bursaries for International Students",
            "University of Göttingen – Emergency Grants for Students in Financial Difficulty",
        }
        self.assertEqual(set(names[:2]), expected)
    def test_directory_sources_are_never_promoted_as_individual_scholarships(self):
        from app.live_discovery import _is_promotable_source_page

        record = {"title": "Funding Opportunities from other Organisations"}
        for source_type in ("official_index", "official_database"):
            with self.subTest(source_type=source_type):
                self.assertFalse(
                    _is_promotable_source_page(record, {"source_type": source_type})
                )
        for source_type in ("government", "university"):
            with self.subTest(source_type=source_type):
                self.assertFalse(
                    _is_promotable_source_page(record, {"source_type": source_type})
                )

    def test_records_are_promoted_after_linked_eligibility_is_attached(self):
        from app.live_discovery import (
            _merge_linked_criteria,
            _promote_actionable_records,
        )

        record = {
            "id": 123,
            "source_url": "https://provider.example/programme",
            "criteria": [],
            "evidence": [],
        }
        results = {}
        _merge_linked_criteria(
            record,
            [("nationality", "Nationality", "International applicants may apply.")],
            "https://provider.example/eligibility",
        )
        _promote_actionable_records(results, [(record, "<main></main>")])
        self.assertIn(record["source_url"], results)
        self.assertEqual(
            results[record["source_url"]]["criteria"][0]["evidence_url"],
            "https://provider.example/eligibility",
        )

    def test_record_requires_actionable_eligibility_criteria(self):
        from app.live_discovery import _has_actionable_eligibility

        self.assertFalse(_has_actionable_eligibility({"criteria": []}))
        self.assertFalse(_has_actionable_eligibility({
            "criteria": [{"criterion_type": "selection_process", "requirement_text": "Selection by donor."}]
        }))
        self.assertTrue(_has_actionable_eligibility({
            "criteria": [{"criterion_type": "eligibility", "requirement_text": "Applicants must hold a degree."}]
        }))

    def test_index_root_is_not_a_scholarship_but_curated_programme_is(self):
        from app.live_discovery import _is_promotable_source_page

        source = {
            "source_type": "official_index",
            "official_url": "https://provider.example/scholarships",
        }
        self.assertFalse(_is_promotable_source_page({
            "title": "Scholarship Opportunities",
            "source_url": "https://provider.example/scholarships",
        }, source))
        self.assertTrue(_is_promotable_source_page({
            "title": "International Student Scholarship",
            "source_url": "https://provider.example/scholarships/international-students",
        }, source))


    def test_stale_index_candidate_is_excluded_when_dedicated_page_is_curated(self):
        from app.live_discovery import _is_excluded_candidate_url

        source = {
            "source_type": "official_index",
            "exclude_candidate_urls": ("https://uni-goettingen.de/en/707360.html",),
        }
        self.assertTrue(_is_excluded_candidate_url(
            source, "https://www.uni-goettingen.de/en/707360.html"
        ))
        self.assertFalse(_is_excluded_candidate_url(
            source, "https://www.uni-goettingen.de/en/516679.html"
        ))
        self.assertFalse(_is_excluded_candidate_url(
            {"source_type": "official_index"},
            "https://www.uni-goettingen.de/en/707360.html",
        ))

    def test_application_guides_are_not_promoted_as_scholarships(self):
        from app.live_discovery import _is_promotable_source_page

        for title in ("Applying for a scholarship", "How to apply", "Application procedure"):
            with self.subTest(title=title):
                self.assertFalse(_is_promotable_source_page(
                    {"title": title},
                    {"source_type": "official_programme"},
                ))

    def test_generic_provider_landing_titles_are_rejected(self):
        from app.live_discovery import _is_promotable_source_page

        for title in (
            "Welcome",
            "Scholarship Providers",
            "Scholarships by Target Group and Stage of University Education",
            "Scholarship Programmes for Pakistan",
            "Studienwerk",
            "Stipendium",
            "Stipendien",
            "Scholarship Department",
            "Scholarships & Funding",
            "The Most Important Domestic Scholarship Programmes:",
            "DAAD Scholarships - An Overview",
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

    def test_named_government_and_university_programmes_can_be_promoted(self):
        from app.live_discovery import _is_promotable_source_page

        for source_type in ("government", "university"):
            with self.subTest(source_type=source_type):
                self.assertTrue(
                    _is_promotable_source_page(
                        {"title": "Deutschlandstipendium – Federal Scholarship Programme"},
                        {"source_type": source_type},
                    )
                )


    def test_source_level_eligibility_is_not_inherited_by_child_programmes(self):
        from app.live_discovery import _should_merge_source_eligibility

        source_url = "https://www.hss.de/stipendium/"
        self.assertTrue(_should_merge_source_eligibility({"source_url": source_url}, source_url))
        self.assertFalse(_should_merge_source_eligibility({
            "source_url": "https://www.hss.de/stipendium/foerderung/foerderung-auszubildender/"
        }, source_url))

    def test_source_candidate_title_uses_curated_programme_title(self):
        from app.live_discovery import _source_candidate_title

        url = "https://provider.example/student-scholarship"
        source = {
            "name": "Provider Scholarship Directory",
            "programme_titles": {url: "Provider International Student Scholarship"},
        }
        self.assertEqual(
            _source_candidate_title(source, url),
            "Provider International Student Scholarship",
        )
        self.assertEqual(
            _source_candidate_title(source, "https://provider.example/other"),
            "Provider Scholarship Directory",
        )

    def test_source_page_urls_include_curated_same_host_programmes_only(self):
        from app.live_discovery import _source_page_urls

        source = {
            "official_url": "https://provider.example/scholarships",
            "programme_urls": (
                "https://provider.example/student-scholarship",
                "https://provider.example/doctoral-scholarship",
                "http://provider.example/insecure",
                "https://untrusted.example/foreign",
            ),
        }
        self.assertEqual(
            _source_page_urls(source),
            [
                "https://provider.example/student-scholarship",
                "https://provider.example/doctoral-scholarship",
                "https://provider.example/scholarships",
            ],
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


    def test_live_scan_report_marks_a_timed_out_source_as_partial(self):
        from unittest.mock import AsyncMock, patch
        import asyncio
        from app import live_discovery

        sources = (
            {
                "name": "Fast official source",
                "official_url": "https://fast.example/scholarships",
                "source_type": "official_index",
                "country": "Germany",
            },
            {
                "name": "Slow official source",
                "official_url": "https://slow.example/scholarships",
                "source_type": "official_index",
                "country": "Germany",
            },
        )

        async def fake_fetch(_client, url):
            if "slow.example" in url:
                await asyncio.sleep(0.1)
            return "<html><body><main>No individual awards listed.</main></body></html>", None

        async def run():
            with (
                patch.object(live_discovery, "GERMANY_SOURCES", sources),
                patch.object(live_discovery, "DISCOVERY_BUDGET_SECONDS", 0.02),
                patch.object(live_discovery, "_fetch_page", new=AsyncMock(side_effect=fake_fetch)),
                patch.object(live_discovery, "parse_scholarship_page", return_value=None),
            ):
                rows = await live_discovery.discover_live_scholarships()
            return rows, live_discovery.get_last_discovery_report()

        rows, report = asyncio.run(run())
        self.assertEqual(rows, [])
        self.assertTrue(report["partial"])
        self.assertEqual(report["total_sources"], 2)
        self.assertEqual(report["completed_sources"], 1)
        self.assertEqual(report["timed_out_sources"], ["Slow official source"])
        self.assertGreaterEqual(report["pages_attempted"], 1)
        self.assertGreaterEqual(report["pages_succeeded"], 1)


if __name__ == "__main__":
    unittest.main()
