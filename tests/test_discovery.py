import unittest

from app.discovery import _candidate_links, _daad_database_page_urls, _normalized_host


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

    def test_image_alt_text_labels_image_only_scholarship_link(self) -> None:
        html = """
        <a href="/programmes/2027">
            <img src="/banner.png" alt="Commonwealth Scholarship Programme 2027">
        </a>
        """
        results = _candidate_links(html, "https://portal.example/", "portal.example")
        self.assertEqual(
            results,
            [(
                "https://portal.example/programmes/2027",
                "Commonwealth Scholarship Programme 2027",
            )],
        )

    def test_aria_label_is_used_when_link_has_no_visible_text(self) -> None:
        html = '<a href="/funding/current" aria-label="Student funding opportunities"></a>'
        results = _candidate_links(html, "https://portal.example/", "portal.example")
        self.assertEqual(
            results,
            [("https://portal.example/funding/current", "Student funding opportunities")],
        )

    def test_duplicate_candidate_urls_are_collapsed(self) -> None:
        html = """
        <a href="/funding">Funding</a>
        <a href="/funding#details">Funding details</a>
        """
        results = _candidate_links(html, "https://portal.example/", "portal.example")
        self.assertEqual(len(results), 1)


    def test_daad_database_detail_link_keeps_programme_id(self) -> None:
        html = """
        <table><tr><td>Research Grants in Germany</td>
        <td><a href="/en/find-funding/scholarship-database/?detail_to_show=50076777&id=0">More</a></td></tr></table>
        """
        results = _candidate_links(
            html,
            "https://www.daad.pk/en/find-funding/scholarship-database/",
            "www.daad.pk",
        )
        self.assertEqual(len(results), 1)
        self.assertIn("detail_to_show=50076777", results[0][0])

    def test_daad_database_pagination_covers_all_seventeen_pages(self) -> None:
        pages = _daad_database_page_urls(
            "https://www.daad.pk/en/find-funding/scholarship-database/?origin=194&pg=1"
        )
        self.assertEqual(len(pages), 17)
        self.assertIn("pg=1", pages[0])
        self.assertIn("pg=17", pages[-1])

    def test_source_must_use_https(self) -> None:
        self.assertIsNone(_normalized_host("http://portal.example/"))
        self.assertEqual(_normalized_host("https://portal.example/"), "portal.example")


    def test_excludes_sign_in_contact_archive_and_download_links(self) -> None:
        html = """
        <a href="/english/scholarshipsgrants/_layouts/15/Authenticate.aspx">Sign In</a>
        <a href="/english/scholarshipsgrants/HAG/Pages/ContactUs.aspx">ContactUs.aspx</a>
        <a href="/english/scholarshipsgrants/lao/Pages/Inactive-Scholarships.aspx">Inactive/Archive Scholarships</a>
        <a href="/english/scholarshipsgrants/lao/Documents/Test-Pattern-USAT-HAT.pdf">Scholarship test pattern</a>
        """
        results = _candidate_links(html, "https://portal.example/", "portal.example")
        self.assertEqual(results, [])

    def test_excludes_generic_scholarship_root_but_keeps_named_programme_page(self) -> None:
        html = """
        <a href="/english/scholarshipsgrants/Pages/default.aspx">Scholarships</a>
        <a href="/english/scholarshipsgrants/IDPS/Pages/default.aspx">International Development Scholarship Programme</a>
        """
        results = _candidate_links(html, "https://portal.example/", "portal.example")
        self.assertEqual(
            results,
            [(
                "https://portal.example/english/scholarshipsgrants/IDPS/Pages/default.aspx",
                "International Development Scholarship Programme",
            )],
        )


if __name__ == "__main__":
    unittest.main()
