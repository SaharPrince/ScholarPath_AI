import unittest
from unittest.mock import AsyncMock, patch

from app import main as api


class MatchingApiVisibilityTests(unittest.IsolatedAsyncioTestCase):
    def profile(self, **extra):
        return {
            "nationality": "Pakistani",
            "current_education_level": "intermediate",
            "target_study_level": "bachelors",
            **extra,
        }

    def scholarship(self, criteria):
        return {
            "id": 701,
            "title": "Regression Test Scholarship",
            "provider_name": "Official Provider",
            "status": "unverified",
            "application_status": "open",
            "source_url": "https://official.example/scholarship",
            "criteria": criteria,
        }

    def criterion(self, kind, label, text):
        return {
            "id": 1,
            "criterion_type": kind,
            "criterion_label": label,
            "requirement_text": text,
            "is_mandatory": True,
            "evidence_url": "https://official.example/eligibility",
        }

    async def test_confirmed_marks_failure_is_not_exposed_as_a_match_or_review_candidate(self):
        row = self.scholarship([
            self.criterion("academic_requirements", "Minimum aggregate", "At least 60% aggregate marks are required."),
            self.criterion("age_limit", "Age limit", "Applicants must be 35 years old or younger."),
        ])
        with patch("app.main._live_results", new=AsyncMock(return_value=[row])):
            result = await api.match_profile(self.profile(academic_percentage=57.9))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["not_eligible"], 1)
        self.assertEqual(result["needs_more_information"], 0)
        self.assertEqual(result["results"], [])
        self.assertNotIn("review_results", result)

    async def test_unknown_only_candidate_remains_visible_for_one_adaptive_follow_up(self):
        row = self.scholarship([
            self.criterion("age_limit", "Age limit", "Applicants must be 35 years old or younger."),
        ])
        with patch("app.main._live_results", new=AsyncMock(return_value=[row])):
            result = await api.match_profile(self.profile())

        self.assertEqual(result["needs_more_information"], 1)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["match_status"], "needs_more_information")
        self.assertIn("Add your age", result["results"][0]["checks"][0]["explanation"])

    async def test_test_score_type_is_accepted_for_adaptive_gre_or_hat_follow_up(self):
        row = self.scholarship([
            self.criterion(
                "academic_requirements",
                "GRE / HEC-HAT",
                "Applicants need a GRE score of at least 300 or a HEC-HAT score of at least 60.",
            ),
        ])
        with patch("app.main._live_results", new=AsyncMock(return_value=[row])):
            result = await api.match_profile(self.profile(test_score_type="hat"))
        self.assertEqual(result["needs_more_information"], 1)

    async def test_test_score_type_rejects_unsupported_choices(self):
        with self.assertRaises(api.HTTPException) as raised:
            await api.match_profile(self.profile(test_score_type="sat"))
        self.assertEqual(raised.exception.status_code, 422)

    async def test_required_profile_fields_must_be_nonempty_text(self):
        with self.assertRaises(api.HTTPException) as raised:
            await api.match_profile(self.profile(nationality={"value": "Pakistani"}))
        self.assertEqual(raised.exception.status_code, 422)

    async def test_oversized_profile_text_is_rejected(self):
        with self.assertRaises(api.HTTPException) as raised:
            await api.match_profile(self.profile(education_field="A" * 121))
        self.assertEqual(raised.exception.status_code, 422)

    async def test_unsupported_study_level_is_rejected(self):
        with self.assertRaises(api.HTTPException) as raised:
            await api.match_profile(self.profile(target_study_level="space tourism"))
        self.assertEqual(raised.exception.status_code, 422)

    async def test_boolean_profile_fields_reject_string_values(self):
        with self.assertRaises(api.HTTPException) as raised:
            await api.match_profile(self.profile(admission_confirmed="true"))
        self.assertEqual(raised.exception.status_code, 422)

    async def test_numeric_profile_fields_reject_objects_and_non_finite_values(self):
        for invalid in ({"value": 10}, float("inf"), float("nan"), True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(api.HTTPException) as raised:
                    await api.match_profile(self.profile(age=invalid))
                self.assertEqual(raised.exception.status_code, 422)


class BrowserSecurityHeaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_security_headers_apply_without_caching_applicant_post_responses(self):
        from starlette.requests import Request
        from starlette.responses import Response

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/match",
            "raw_path": b"/api/match",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 12345),
            "server": ("testserver", 443),
        }

        async def call_next(_request):
            response = Response("ok")
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            return response

        response = await api.cache_public_scholarship_reads(Request(scope), call_next)

        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(
            response.headers["Permissions-Policy"],
            "camera=(), microphone=(), geolocation=()",
        )
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("connect-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
