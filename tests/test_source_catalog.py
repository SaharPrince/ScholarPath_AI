import unittest
from urllib.parse import urlparse

from app.source_catalog import OFFICIAL_DISCOVERY_TARGETS, OFFICIAL_SOURCES


class OfficialDiscoveryTargetTests(unittest.TestCase):
    def test_targets_belong_to_configured_official_sources(self) -> None:
        source_urls = {source["official_url"] for source in OFFICIAL_SOURCES}
        for source_url, candidate_url, title in OFFICIAL_DISCOVERY_TARGETS:
            with self.subTest(candidate_url=candidate_url):
                self.assertIn(source_url, source_urls)
                self.assertTrue(title.strip())
                self.assertEqual(urlparse(source_url).scheme, "https")
                self.assertEqual(urlparse(candidate_url).scheme, "https")
                self.assertEqual(
                    urlparse(source_url).hostname,
                    urlparse(candidate_url).hostname,
                )

    def test_target_urls_are_unique_per_source(self) -> None:
        keys = [(source_url, candidate_url) for source_url, candidate_url, _ in OFFICIAL_DISCOVERY_TARGETS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_school_and_college_opportunities_are_included(self) -> None:
        titles = " ".join(title.lower() for _, _, title in OFFICIAL_DISCOVERY_TARGETS)
        self.assertIn("matric", titles)
        self.assertIn("intermediate", titles)
        self.assertIn("school education", titles)
        self.assertIn("cadet excellence", titles)


if __name__ == "__main__":
    unittest.main()
