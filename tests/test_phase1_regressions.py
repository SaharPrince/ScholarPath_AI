import unittest

from app.matching import evaluate_criterion, match_profile_to_scholarships


class PhaseOneRegressionTests(unittest.TestCase):
    def criterion(self, kind, label, text):
        return {
            "id": 501,
            "criterion_type": kind,
            "criterion_label": label,
            "requirement_text": text,
            "is_mandatory": True,
            "evidence_url": "https://official.example/eligibility",
        }

    def test_negative_named_university_exclusion_is_not_a_positive_enrolment_gate(self):
        criterion = self.criterion(
            "eligibility",
            "Exchange students",
            "Exchange students are not eligible if they are temporarily enrolled at the University of Göttingen.",
        )
        result = evaluate_criterion(criterion, {})
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("enter the name of your current university", result["explanation"])

    def test_positive_named_university_requirement_still_requests_confirmation(self):
        criterion = self.criterion(
            "eligibility",
            "Enrolment",
            "Applicants must be currently enrolled at the University of Würzburg.",
        )
        result = evaluate_criterion(criterion, {})
        self.assertEqual(result["status"], "unknown")
        self.assertIn("name of your current university", result["explanation"])

    def test_ambiguous_university_degree_reference_is_not_assumed_to_be_a_prerequisite(self):
        criterion = self.criterion(
            "study_level",
            "Funding",
            "The scholarship provides funding for a university degree in Germany.",
        )
        result = evaluate_criterion(
            criterion,
            {"current_education_level": "intermediate", "target_study_level": "bachelors"},
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIn("does not clearly establish", result["explanation"])

    def test_explicit_university_degree_prerequisite_still_rejects_intermediate_applicant(self):
        criterion = self.criterion(
            "study_level",
            "Academic qualification",
            "Applicants must have a university degree.",
        )
        result = evaluate_criterion(criterion, {"current_education_level": "intermediate"})
        self.assertEqual(result["status"], "fail")

    def test_aggregate_marks_threshold_is_checked_even_though_aggregate_contains_gre(self):
        criterion = self.criterion(
            "academic_requirements",
            "Minimum aggregate",
            "At least 60% aggregate marks are required.",
        )
        result = evaluate_criterion(
            criterion,
            {
                "current_education_level": "intermediate",
                "target_study_level": "bachelors",
                "academic_percentage": 57.9,
            },
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("below the published minimum of 60", result["explanation"])

    def test_multi_level_award_is_not_narrowed_by_masters_subclause(self):
        from app.matching import match_profile_to_scholarships

        rows = [{"id": 501, "title": "International Student Support"}]
        criteria = {
            501: [
                self.criterion(
                    "study_level",
                    "Eligible applicants",
                    "The award is open to Bachelor's and Master's students. Master's applicants must have completed 16 years of education.",
                )
            ]
        }
        results = match_profile_to_scholarships(
            rows,
            criteria,
            {"target_study_level": "bachelors", "current_education_level": "intermediate"},
        )
        self.assertEqual([item["id"] for item in results], [501])


if __name__ == "__main__":
    unittest.main()
