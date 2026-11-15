"""Regression tests for live extraction of Göttingen scholarship pages."""
import unittest

from app.extraction import _parse_deadline_date, parse_scholarship_page
from app.live_discovery import _as_record


SANTANDER_URL = "https://www.uni-goettingen.de/en/santander%2Bstipendien/707360.html"
SANTANDER_APPLICATION_URL = (
    "https://app.santanderopenacademy.com/en/program/"
    "sorgenfrei-stipendium-deutschland-2026-10-x-10-000-eur-fuer-dein-studium"
)


class GoettingenScholarshipExtractionTests(unittest.TestCase):
    def test_english_ordinal_deadline_is_normalized(self):
        self.assertEqual(_parse_deadline_date("November 30th, 2026"), "2026-11-30")
        self.assertEqual(_parse_deadline_date("November 1st, 2026"), "2026-11-01")

    def test_santander_page_preserves_current_cycle_deadline_application_and_eligibility(self):
        html = """
        <html><body><main>
          <h1>Scholarships of the Openbank Deutschland AG</h1>
          <p>The Sorgenfrei Scholarship 2026/2027 offers students at the University of Göttingen
          financial support in the amount of €1,000.</p>
          <p>The application deadline is November 30th, 2026. A total of 10 scholarships will be awarded.</p>
          <h2>Who can apply?</h2>
          <p>All regular students of the University of Göttingen in the winter semester 2026/2027
          are eligible to apply.</p>
          <p>Exchange students are not eligible for funding because they are only temporarily
          enrolled at the University of Göttingen and do not graduate from the University of Göttingen.</p>
          <h2>How to apply?</h2>
          <p>The application is made via the Santander Open Academy. You can access the application
          portal <a href="""" + SANTANDER_APPLICATION_URL + """"">here</a>.</p>
          <p>The scholarships are offered by Openbank Deutschland AG.</p>
        </main></body></html>
        """
        parsed = parse_scholarship_page(html, SANTANDER_URL)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.fields.get("deadline_text"), "November 30th, 2026")
        self.assertEqual(_parse_deadline_date(parsed.fields.get("deadline_text")), "2026-11-30")
        self.assertEqual(parsed.fields.get("application_url"), SANTANDER_APPLICATION_URL)
        self.assertTrue(any("regular students" in item[2].lower() for item in parsed.criteria))
        self.assertTrue(any("exchange students are not eligible" in item[2].lower() for item in parsed.criteria))
        self.assertEqual(parsed.provider_name, "Openbank Deutschland AG")

        source = {
            "name": "University of Göttingen – Santander Sorgenfrei Scholarship 2026/2027",
            "provider_name": "Openbank Deutschland AG",
            "source_type": "official_programme",
            "programme_titles": {SANTANDER_URL: "Santander Sorgenfrei Scholarship 2026/2027"},
        }
        record = _as_record(parsed, source, SANTANDER_URL)
        self.assertEqual(record["title"], "Santander Sorgenfrei Scholarship 2026/2027")
        self.assertEqual(record["provider_name"], "Openbank Deutschland AG")
        self.assertEqual(record["deadline_date"], "2026-11-30")
        self.assertEqual(record["application_url"], SANTANDER_APPLICATION_URL)
        self.assertTrue(all(item.get("evidence_url") == SANTANDER_URL for item in record["evidence"]))

    def test_degree_bursary_keeps_thesis_registration_as_an_explicit_condition(self):
        html = """
        <html><body><main>
          <h1>Academic Degree Bursaries</h1>
          <p>Through funding provided by the German Academic Exchange Service (DAAD), the
          bursary and financial assistance committee awards partial scholarships to international students.</p>
          <p>They are intended for students who have financed most of their studies on their own
          and are about to complete their studies at the University of Göttingen at the time of application.</p>
          <p>Bursaries provide financial assistance without completely covering all living expenses.</p>
          <p>The scholarships are awarded for a maximum of six months.</p>
          <p>Applicants must have registered the written thesis of their current course of study.</p>
        </main></body></html>
        """
        parsed = parse_scholarship_page(html, "https://www.uni-goettingen.de/en/516679.html")
        self.assertIsNotNone(parsed)
        self.assertTrue(any("registered the written thesis" in item[2].lower() for item in parsed.criteria))

    def test_emergency_grant_keeps_semester_and_self_funding_conditions(self):
        html = """
        <html><body><main>
          <h1>Emergency Grants for Students in Financial Difficulty</h1>
          <p>International students of Göttingen University, regularly at least in their 3rd semester,
          who find themselves in unexpected financial difficulty while studying at Göttingen University
          and who have financed most of their studies on their own can receive short-term support
          through the Scholarships and Grants Committee.</p>
          <p>The scholarships are awarded for a maximum of six months. An application is required.</p>
        </main></body></html>
        """
        parsed = parse_scholarship_page(html, "https://www.uni-goettingen.de/en/516678.html")
        self.assertIsNotNone(parsed)
        joined = " ".join(item[2].lower() for item in parsed.criteria)
        self.assertIn("3rd semester", joined)
        self.assertIn("financial difficulty", joined)
        self.assertIn("financed most", joined)


if __name__ == "__main__":
    unittest.main()
