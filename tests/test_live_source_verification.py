import httpx
import unittest

from scripts.live_source_verification import _is_transient_failure, _programme_candidate_title


class LiveSourceVerificationTests(unittest.TestCase):
    def test_timeout_is_treated_as_transient(self):
        self.assertTrue(_is_transient_failure(httpx.ReadTimeout("provider timed out")))

    def test_server_error_is_treated_as_transient(self):
        request = httpx.Request("GET", "https://example.org/programme")
        response = httpx.Response(502, request=request)
        error = httpx.HTTPStatusError("bad gateway", request=request, response=response)
        self.assertTrue(_is_transient_failure(error))

    def test_not_found_is_not_treated_as_transient(self):
        request = httpx.Request("GET", "https://example.org/programme")
        response = httpx.Response(404, request=request)
        error = httpx.HTTPStatusError("not found", request=request, response=response)
        self.assertFalse(_is_transient_failure(error))

    def test_curated_detail_page_uses_its_official_programme_name(self):
        source = {
            "name": "University of Würzburg – Amend Medical Scholarship",
            "official_url": "https://www.med.uni-wuerzburg.de/en/service/stipendien/",
            "source_type": "official_programme",
        }
        self.assertEqual(
            _programme_candidate_title(source, source["official_url"]),
            source["name"],
        )

    def test_broad_index_does_not_get_promoted_to_a_programme_title(self):
        source = {
            "name": "University of Würzburg – Scholarships by Target Group",
            "official_url": "https://www.uni-wuerzburg.de/en/scholarships/by-target-group/",
            "source_type": "official_index",
        }
        self.assertIsNone(_programme_candidate_title(source, source["official_url"]))

    def test_explicit_programme_title_takes_precedence(self):
        url = "https://example.org/programme"
        source = {
            "name": "Official Provider Index",
            "programme_urls": (url,),
            "programme_titles": {url: "Named Individual Scholarship"},
            "source_type": "official_index",
        }
        self.assertEqual(_programme_candidate_title(source, url), "Named Individual Scholarship")


if __name__ == "__main__":
    unittest.main()
