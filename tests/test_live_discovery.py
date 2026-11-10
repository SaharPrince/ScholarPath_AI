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


if __name__ == "__main__":
    unittest.main()
