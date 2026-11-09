import unittest

from app.matching import evaluate_criterion, match_scholarship


class ProfileMatchingTests(unittest.TestCase):
    def criterion(self, kind, label, text, mandatory=True):
        return {
            "id": 1, "criterion_type": kind, "criterion_label": label,
            "requirement_text": text, "is_mandatory": mandatory,
            "evidence_url": "https://official.example/eligibility",
        }

    def test_pakistani_nationality_passes(self):
        result = evaluate_criterion(
            self.criterion("nationality", "Nationality", "Pakistani/AJK nationals"),
            {"nationality": "Pakistani"},
        )
        self.assertEqual(result["status"], "pass")

    def test_wrong_nationality_fails(self):
        result = evaluate_criterion(
            self.criterion("nationality", "Nationality", "Pakistani/AJK nationals"),
            {"nationality": "Canadian"},
        )
        self.assertEqual(result["status"], "fail")

    def test_missing_nationality_needs_information(self):
        result = evaluate_criterion(
            self.criterion("nationality", "Nationality", "Pakistani/AJK nationals"), {}
        )
        self.assertEqual(result["status"], "unknown")

    def test_no_upper_age_limit_is_informational(self):
        result = evaluate_criterion(
            self.criterion("age_limit", "Age limit", "There is no upper age limit for this scholarship."),
            {"age": 55},
        )
        self.assertEqual(result["status"], "informational")

    def test_maximum_age_is_checked(self):
        c = self.criterion("age_limit", "Maximum age", "35 Years in all other cases")
        self.assertEqual(evaluate_criterion(c, {"age": 34})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"age": 36})["status"], "fail")

    def test_hat_score_is_checked(self):
        c = self.criterion("academic_requirements", "Minimum HAT score", "Minimum score of 60 out of 100 in HAT test.")
        self.assertEqual(evaluate_criterion(c, {"hat_score": 65})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"hat_score": 55})["status"], "fail")

    def test_missing_hat_score_needs_information(self):
        c = self.criterion("academic_requirements", "Minimum HAT score", "Minimum score of 60 out of 100 in HAT test.")
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")

    def test_other_scholarship_exclusion(self):
        c = self.criterion("ineligibility", "Other scholarship", "Must not be availing any other Scholarship.")
        self.assertEqual(evaluate_criterion(c, {"receiving_other_scholarship": True})["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {"receiving_other_scholarship": False})["status"], "pass")

    def test_informational_criteria_do_not_block_eligibility(self):
        scholarship = {"id": 7, "title": "Test", "status": "unverified", "application_status": "open"}
        criteria = [self.criterion("selection_process", "Selection", "Final selection is by donor.", False)]
        result = match_scholarship(scholarship, criteria, {})
        self.assertEqual(result["match_status"], "likely_eligible")

    def test_unknown_mandatory_criteria_prevent_false_eligible(self):
        scholarship = {"id": 7, "title": "Test", "status": "unverified", "application_status": "open"}
        criteria = [self.criterion("required_documents", "Documents", "Submit transcript.")]
        result = match_scholarship(scholarship, criteria, {})
        self.assertEqual(result["match_status"], "needs_more_information")

    def test_failed_mandatory_criterion_marks_not_eligible(self):
        scholarship = {"id": 7, "title": "Test", "status": "unverified", "application_status": "open"}
        criteria = [self.criterion("nationality", "Nationality", "Pakistani/AJK nationals")]
        result = match_scholarship(scholarship, criteria, {"nationality": "Canadian"})
        self.assertEqual(result["match_status"], "not_eligible")

    def test_unhandled_rules_are_not_assumed_passed(self):
        result = evaluate_criterion(
            self.criterion("academic_requirements", "Research proposal", "Must submit a research proposal."),
            {},
        )
        self.assertEqual(result["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
