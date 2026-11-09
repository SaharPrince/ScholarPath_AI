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
        other_applicant = {"regular_government_employee": False, "public_university_faculty": False, "approved_rd_researcher": False}
        self.assertEqual(evaluate_criterion(c, {"age": 34, **other_applicant})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"age": 36, **other_applicant})["status"], "fail")

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
        self.assertEqual(result["match_status"], "needs_more_information")

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

    def test_gre_or_hat_alternative_accepts_either_test(self):
        c = self.criterion("academic_requirements", "GRE or HAT", "GRE score 300 and above/HEC-HAT score 60% and above")
        self.assertEqual(evaluate_criterion(c, {"hat_score": 65})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"gre_score": 305})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"hat_score": 50, "gre_score": 280})["status"], "fail")

    def test_category_i_and_ii_are_alternative_routes(self):
        scholarship = {"id": 7, "title": "Test", "status": "unverified", "application_status": "open"}
        criteria = [
            self.criterion("category_i_eligibility", "Category I", "Secured admission in top 50 QS World Ranked US University."),
            self.criterion("category_ii_eligibility", "Category II", "Secured admission in any top 51-100 QS World Ranked US University."),
        ]
        result = match_scholarship(scholarship, criteria, {"university_qs_rank": 42, "admission_confirmed": True})
        self.assertEqual(result["match_status"], "likely_eligible")
        self.assertEqual(result["checks_failed"], 0)


    def test_category_pass_resolves_unknown_alternative_route(self):
        scholarship = {"id": 7, "title": "Test", "status": "unverified", "application_status": "open"}
        criteria = [
            self.criterion("category_i_eligibility", "Category I", "Secured admission in top 50 QS World Ranked US University."),
            self.criterion("category_ii_eligibility", "Category II", "Secured admission in any top 51-100 QS World Ranked US University."),
        ]
        result = match_scholarship(scholarship, criteria, {"university_qs_rank": 42, "admission_confirmed": True})
        self.assertEqual(result["match_status"], "likely_eligible")
        self.assertEqual(result["checks_unknown"], 0)
        self.assertEqual(result["checks"][1]["status"], "informational")

    def test_category_pass_resolves_failed_alternative_route(self):
        scholarship = {"id": 7, "title": "Test", "status": "unverified", "application_status": "open"}
        criteria = [
            self.criterion("category_i_eligibility", "Category I", "Secured admission in top 50 QS World Ranked US University."),
            self.criterion("category_ii_eligibility", "Category II", "Secured admission in any top 51-100 QS World Ranked US University."),
        ]
        result = match_scholarship(scholarship, criteria, {"university_qs_rank": 42, "admission_confirmed": True})
        self.assertEqual(result["match_status"], "likely_eligible")
        self.assertEqual(result["checks_failed"], 0)
        self.assertEqual(result["checks"][1]["status"], "informational")

    def test_no_structured_criteria_never_means_eligible(self):
        scholarship = {"id": 7, "title": "Test", "status": "unverified", "application_status": "open"}
        result = match_scholarship(scholarship, [], {})
        self.assertEqual(result["match_status"], "needs_more_information")

    def test_public_sector_age_branches_wait_for_employment_answer(self):
        higher = self.criterion("age_limit", "Public-sector maximum age", "40 Years in case of regular Government Employees/regular Faculty members of Public Sector Universities")
        general = self.criterion("age_limit", "Other applicants maximum age", "35 Years in all other cases")
        self.assertEqual(evaluate_criterion(higher, {"age": 38})["status"], "unknown")
        self.assertEqual(evaluate_criterion(general, {"age": 38})["status"], "unknown")
        self.assertEqual(evaluate_criterion(higher, {"age": 38, "regular_government_employee": True})["status"], "pass")
        self.assertEqual(evaluate_criterion(general, {"age": 38, "regular_government_employee": True})["status"], "informational")
        self.assertEqual(evaluate_criterion(general, {"age": 38, "regular_government_employee": False, "public_university_faculty": False, "approved_rd_researcher": False})["status"], "fail")

    def test_higher_degree_rules_require_selected_study_level(self):
        c = self.criterion("academic_requirements", "Master's degree requirement", "For Master scholarship, an applicant must hold a first division in 16 years Bachelors degree.")
        self.assertEqual(evaluate_criterion(c, {"years_of_education": 16, "latest_degree_division": "first"})["status"], "unknown")
        self.assertEqual(evaluate_criterion(c, {"target_study_level": "phd", "years_of_education": 16})["status"], "informational")
        self.assertEqual(evaluate_criterion(c, {"target_study_level": "bachelors"})["status"], "fail")

    def test_gpa_is_not_assumed_equivalent_to_first_division(self):
        c = self.criterion("academic_requirements", "Academic record", "Must have first division in latest degree.")
        self.assertEqual(evaluate_criterion(c, {"latest_degree_division": "other"})["status"], "unknown")

    def test_hat_category_is_checked(self):
        c = self.criterion("academic_requirements", "Accepted HAT categories", "Only HAT categories (HAT-I, II, III and IV) are acceptable.")
        self.assertEqual(evaluate_criterion(c, {"hat_category": "HAT-II"})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"hat_category": "Other"})["status"], "fail")

    def test_minimum_age_is_not_misread_as_maximum(self):
        c = self.criterion("age_limit", "Minimum age", "Minimum age 18 years")
        self.assertEqual(evaluate_criterion(c, {"age": 20})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"age": 17})["status"], "fail")

    def test_age_range_is_checked_as_a_range(self):
        c = self.criterion("age_limit", "Age range", "Applicants must be 18 to 35 years old")
        self.assertEqual(evaluate_criterion(c, {"age": 25})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"age": 36})["status"], "fail")


if __name__ == "__main__":
    unittest.main()
