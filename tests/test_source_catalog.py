import unittest
from urllib.parse import urlparse

from app.source_catalog import GERMANY_SOURCES, OFFICIAL_DISCOVERY_TARGETS


class OfficialDiscoveryTargetTests(unittest.TestCase):
    def test_every_configured_source_is_an_official_germany_source(self) -> None:
        self.assertGreaterEqual(len(GERMANY_SOURCES), 15)
        for source in GERMANY_SOURCES:
            with self.subTest(source=source["name"]):
                self.assertEqual(source["country"], "Germany")
                self.assertEqual(urlparse(source["official_url"]).scheme, "https")
                self.assertTrue(source["name"].strip())
                programme_urls = source.get("programme_urls", ())
                programme_titles = source.get("programme_titles", {})
                self.assertTrue(set(programme_titles).issubset(set(programme_urls)))
                for programme_title in programme_titles.values():
                    self.assertTrue(programme_title.strip())
                for programme_url in programme_urls:
                    self.assertEqual(urlparse(programme_url).scheme, "https")
                    self.assertEqual(
                        urlparse(programme_url).hostname,
                        urlparse(source["official_url"]).hostname,
                    )

    def test_multi_programme_hss_and_naumann_indexes_are_not_single_awards(self) -> None:
        sources = {source["name"]: source for source in GERMANY_SOURCES}
        self.assertEqual(
            sources["Hanns Seidel Foundation – Scholarships"]["source_type"],
            "official_index",
        )
        self.assertEqual(
            sources["Friedrich Naumann Foundation – Scholarships"]["source_type"],
            "official_index",
        )
        self.assertNotIn("eligibility_urls", sources["Hanns Seidel Foundation – Scholarships"])

    def test_hss_declares_specific_programmes_without_merging_broad_eligibility(self) -> None:
        hss = next(source for source in GERMANY_SOURCES if source["name"].startswith("Hanns Seidel"))
        self.assertNotIn("eligibility_urls", hss)
        self.assertEqual(
            hss["programme_urls"],
            (
                "https://www.hss.de/stipendium/foerderung/foerderung-auszubildender/",
                "https://www.hss.de/stipendium/foerderung/journalistisches-foerderprogramm/",
            ),
        )
        self.assertEqual(
            hss["programme_titles"]["https://www.hss.de/stipendium/foerderung/foerderung-auszubildender/"],
            "Hanns Seidel Scholarship for Apprentices",
        )
        self.assertEqual(hss["source_type"], "official_index")

    def test_evangelisches_student_and_doctoral_programmes_are_separate(self) -> None:
        source = next(
            source for source in GERMANY_SOURCES
            if source["name"].startswith("Evangelisches Studienwerk")
        )
        self.assertEqual(source["source_type"], "official_index")
        self.assertEqual(
            source["official_url"],
            "https://www.evstudienwerk.de/english/our-mission-statement/",
        )
        self.assertEqual(
            source["programme_urls"],
            (
                "https://www.evstudienwerk.de/english/scholarship-for-students/",
                "https://www.evstudienwerk.de/english/scholarship-for-doctoral-students/",
            ),
        )
        self.assertEqual(
            source["programme_titles"]["https://www.evstudienwerk.de/english/scholarship-for-students/"],
            "Evangelisches Studienwerk Scholarship for Students",
        )
        self.assertEqual(
            source["programme_titles"]["https://www.evstudienwerk.de/english/scholarship-for-doctoral-students/"],
            "Evangelisches Studienwerk Doctoral Scholarship",
        )

    def test_avicenna_national_and_international_programmes_are_separate(self) -> None:
        sources = {source["name"]: source for source in GERMANY_SOURCES}
        self.assertEqual(
            sources["Avicenna Studienwerk – Scholarships"]["official_url"],
            "https://www.avicenna-studienwerk.de/stipendium/",
        )
        self.assertEqual(
            sources["Avicenna Studienwerk – International Scholarship Programme"]["official_url"],
            "https://www.avicenna-studienwerk.de/internationales-stipendienprogramm/",
        )
        self.assertEqual(
            sources["Avicenna Studienwerk – International Scholarship Programme"]["source_type"],
            "official_programme",
        )

    def test_university_funding_directories_are_not_individual_awards(self) -> None:
        sources = {source["name"]: source for source in GERMANY_SOURCES}
        self.assertEqual(
            sources["TU Berlin – Scholarships and Funding for International Students"]["source_type"],
            "official_index",
        )
        self.assertEqual(
            sources["University of Würzburg – Scholarships by Target Group"]["source_type"],
            "official_index",
        )

    def test_discovery_targets_belong_to_configured_sources(self) -> None:
        source_urls = {source["official_url"] for source in GERMANY_SOURCES}
        for source_url, candidate_url, title in OFFICIAL_DISCOVERY_TARGETS:
            with self.subTest(candidate_url=candidate_url):
                self.assertIn(source_url, source_urls)
                self.assertTrue(title.strip())
                self.assertEqual(urlparse(source_url).scheme, "https")
                self.assertEqual(urlparse(candidate_url).scheme, "https")
                self.assertEqual(urlparse(source_url).hostname, urlparse(candidate_url).hostname)

    def test_target_urls_are_unique_per_source(self) -> None:
        keys = [(source_url, candidate_url) for source_url, candidate_url, _ in OFFICIAL_DISCOVERY_TARGETS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_daad_database_source_is_included(self) -> None:
        urls = [source["official_url"] for source in GERMANY_SOURCES]
        self.assertTrue(any("daad.pk" in url and "scholarship-database" in url for url in urls))


if __name__ == "__main__":
    unittest.main()
