import httpx
import unittest

from scripts.live_source_verification import _is_transient_failure


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


if __name__ == "__main__":
    unittest.main()
