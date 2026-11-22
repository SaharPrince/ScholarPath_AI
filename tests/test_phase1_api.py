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


if __name__ == "__main__":
    unittest.main()
