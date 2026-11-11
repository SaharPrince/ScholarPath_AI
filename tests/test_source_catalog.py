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

    def test_hss_declares_its_official_eligibility_page(self) -> None:
        hss = next(source for source in GERMANY_SOURCES if source["name"].startswith("Hanns Seidel"))
        self.assertEqual(
            hss["eligibility_urls"],
            ("https://www.hss.de/stipendium/wen-suchen-wir/",),
        )
        self.assertEqual(urlparse(hss["eligibility_urls"][0]).hostname, "www.hss.de")

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
