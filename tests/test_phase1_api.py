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

    async def test_apprenticeship_second_year_stage_remains_a_text_choice(self):
        with patch("app.main._live_results", new=AsyncMock(return_value=[])):
            result = await api.match_profile(
                self.profile(apprenticeship_second_year_stage="beginning")
            )
        self.assertEqual(result["total"], 0)

    async def test_apprenticeship_second_year_stage_rejects_unsupported_values(self):
        with self.assertRaises(api.HTTPException) as raised:
            await api.match_profile(
                self.profile(apprenticeship_second_year_stage={"stage": "beginning"})
            )
        self.assertEqual(raised.exception.status_code, 422)

        with self.assertRaises(api.HTTPException) as raised:
            await api.match_profile(
                self.profile(apprenticeship_second_year_stage="finished")
            )
        self.assertEqual(raised.exception.status_code, 422)

    async def test_numeric_profile_fields_reject_objects_and_non_finite_values(self):
        for invalid in ({"value": 10}, float("inf"), float("nan"), True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(api.HTTPException) as raised:
                    await api.match_profile(self.profile(age=invalid))
                self.assertEqual(raised.exception.status_code, 422)


    async def test_all_select_profile_fields_accept_supported_choices(self):
        profile = self.profile(
            hat_category="IV",
            latest_degree_division="second",
            german_language_level="C1",
            residence_duration_exception="prior_study",
            german_residence_permit="study",
            first_semester_timing="at_beginning",
            domicile_region="Punjab",
        )
        with patch("app.main._live_results", new=AsyncMock(return_value=[])):
            result = await api.match_profile(profile)
        self.assertEqual(result["total"], 0)

    async def test_select_profile_fields_reject_unsupported_choices(self):
        invalid_choices = {
            "hat_category": "V",
            "latest_degree_division": "excellent",
            "german_language_level": "D1",
            "residence_duration_exception": "financial_need",
            "german_residence_permit": "tourism",
            "first_semester_timing": "semester_two",
            "domicile_region": "Atlantis",
            "test_score_type": "sat",
        }
        for field, value in invalid_choices.items():
            with self.subTest(field=field):
                with self.assertRaises(api.HTTPException) as raised:
                    await api.match_profile(self.profile(**{field: value}))
                self.assertEqual(raised.exception.status_code, 422)

    async def test_count_and_whole_number_score_fields_reject_fractional_values(self):
        for field, value in (
            ("age", 19.5),
            ("hat_score", 59.5),
            ("gre_score", 300.5),
            ("university_qs_rank", 100.5),
            ("years_of_education", 16.5),
            ("months_in_germany", 2.5),
            ("remaining_semesters_in_program", 2.5),
            ("current_semester_in_program", 1.5),
            ("standard_programme_semesters", 6.5),
            ("apprenticeship_year", 1.5),
        ):
            with self.subTest(field=field):
                with self.assertRaises(api.HTTPException) as raised:
                    await api.match_profile(self.profile(**{field: value}))
                self.assertEqual(raised.exception.status_code, 422)

    async def test_apprenticeship_year_must_match_supported_year_range(self):
        for value in (0, 5):
            with self.subTest(value=value):
                with self.assertRaises(api.HTTPException) as raised:
                    await api.match_profile(self.profile(apprenticeship_year=value))
                self.assertEqual(raised.exception.status_code, 422)

    async def test_fractional_cgpa_and_professional_experience_remain_supported(self):
        with patch("app.main._live_results", new=AsyncMock(return_value=[])):
            result = await api.match_profile(
                self.profile(cgpa=3.45, professional_experience_years=2.5)
            )
        self.assertEqual(result["total"], 0)


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
