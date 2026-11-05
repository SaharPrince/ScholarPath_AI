import unittest

from app.discovery import _candidate_links, _normalized_host


class DiscoveryParsingTests(unittest.TestCase):
    def test_only_same_host_https_scholarship_links_are_kept(self) -> None:
        html = """
        <a href="/scholarships/merit">Merit scholarship</a>
        <a href="https://other.example/scholarship">External scholarship</a>
        <a href="http://portal.example/grants">Insecure grant</a>
        <a href="/about">About us</a>
        <a href="mailto:help@example.org">Email</a>
        """
        results = _candidate_links(
            html,
            "https://portal.example/",
            "portal.example",
        )
        self.assertEqual(
            results,
            [("https://portal.example/scholarships/merit", "Merit scholarship")],
        )

    def test_duplicate_candidate_urls_are_collapsed(self) -> None:
        html = """
        <a href="/funding">Funding</a>
        <a href="/funding#details">Funding details</a>
        """
        results = _candidate_links(html, "https://portal.example/", "portal.example")
        self.assertEqual(len(results), 1)

    def test_source_must_use_https(self) -> None:
        self.assertIsNone(_normalized_host("http://portal.example/"))
        self.assertEqual(_normalized_host("https://portal.example/"), "portal.example")


if __name__ == "__main__":
    unittest.main()
