"""Regression tests for live extraction of Göttingen scholarship pages."""
import unittest

from bs4 import BeautifulSoup

from app.extraction import (
    FIELD_LABELS, _find_labeled_text, _parse_deadline_date, _remove_site_chrome, parse_scholarship_page,
)
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
        html = f"""
        <html><body><article>
          <h1 class="headline">Scholarships of the Openbank Deutschland AG</h1>
          <div class="card card-featured">
            <div class="collapse-box transparent">
              <b>The Sorgenfrei Scholarship 2026/2027 offers students at the University of Göttingen
              financial support in the amount of €1,000.</b>
              <b><p> The application deadline is November 30th, 2026. A total of 10 scholarships will be awarded.</p></b>
              <i>Who can apply?</i><p></p>
              All regular students of the University of Göttingen in the winter semester 2026/2027
              are eligible to apply. Exchange students are not eligible for funding as they are only temporarily
              enrolled at the University of Göttingen and do not graduate from the University of Göttingen. <p></p>
              <i>How to apply?</i><p></p>
              The application is made via the Santander Open Academy. You can access the application portal
              <a href="{SANTANDER_APPLICATION_URL}">here</a>. <p></p>
              <i>When is the deadline?</i><p></p>
              The application deadline is November 30th, 2026. <p></p>
              <i>The scholarships are offered by Openbank Deutschland AG.</i><p></p>
            </div>
          </div>
        </article></body></html>
        """
        parsed = parse_scholarship_page(
            html, SANTANDER_URL, "Santander Sorgenfrei Scholarship 2026/2027"
        )
        content_root = _remove_site_chrome(BeautifulSoup(html, "html.parser"), SANTANDER_URL)
        self.assertEqual(
            _find_labeled_text(content_root, FIELD_LABELS["deadline_text"], "deadline_text"),
            "November 30th, 2026. A total of 10 scholarships will be awarded.",
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.fields.get("deadline_text"), "November 30th, 2026. A total of 10 scholarships will be awarded.")
        self.assertEqual(_parse_deadline_date(parsed.fields.get("deadline_text")), "2026-11-30")
        self.assertEqual(parsed.fields.get("application_url"), SANTANDER_APPLICATION_URL)
        self.assertIn("€1,000", parsed.fields.get("funding_summary", ""))
        self.assertTrue(any("regular students" in item[2].lower() for item in parsed.criteria))
        self.assertTrue(any("exchange students are not eligible" in item[2].lower() for item in parsed.criteria))

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
        self.assertTrue(any(item["field_name"] == "deadline_text" for item in record["evidence"]))
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
