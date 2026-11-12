import unittest

from app.matching import evaluate_criterion, match_scholarship


class ProfileMatchingTests(unittest.TestCase):
    def criterion(self, kind, label, text, mandatory=True):
        return {
            "id": 1, "criterion_type": kind, "criterion_label": label,
            "requirement_text": text, "is_mandatory": mandatory,
            "evidence_url": "https://official.example/eligibility",
        }

    def test_bachelors_profile_excludes_completed_masters_requirement(self):
        result = evaluate_criterion(
            self.criterion("study_level", "Study level", "Applicants should have completed their Master degree within the last 2 years."),
            {"target_study_level": "bachelors"},
        )
        self.assertEqual(result["status"], "fail")

    def test_bachelors_profile_excludes_phd_program_requirement(self):
        result = evaluate_criterion(
            self.criterion("study_level", "Study level", "International PhD students may apply for a PhD program in Germany."),
            {"target_study_level": "bachelors"},
        )
        self.assertEqual(result["status"], "fail")

    def test_bachelors_profile_excludes_generic_graduate_and_phd_awards(self):
        from app.matching import match_profile_to_scholarships

        rows = [
            {"id": 1, "title": "Tailwind for Talents: Scholarships for Graduates and PhD students"},
            {"id": 2, "title": "Applying for a scholarship"},
        ]
        criteria = {
            1: [{**self.criterion("study_level", "Study level", "Graduate degree completed abroad"), "is_mandatory": True}],
            2: [{**self.criterion("study_level", "Study level", "Graduate degree completed abroad"), "is_mandatory": True}],
        }
        results = match_profile_to_scholarships(
            rows, criteria, {"target_study_level": "Bachelor's / Undergraduate"}
        )
        self.assertEqual(results, [])

    def test_bachelors_profile_excludes_masters_and_phd_only_awards(self):
        from app.matching import match_profile_to_scholarships
        rows = [
            {"id": 1, "title": "Master's Scholarship"},
            {"id": 2, "title": "PhD Scholarship"},
            {"id": 3, "title": "Undergraduate Scholarship"},
            {"id": 4, "title": "General Education Support"},
        ]
        criteria = {
            1: [self.criterion("academic_requirements", "Study level", "For Master's applicants.")],
            2: [self.criterion("academic_requirements", "Study level", "For PhD applicants.")],
            3: [self.criterion("academic_requirements", "Study level", "For undergraduate applicants.")],
            4: [self.criterion("nationality", "Nationality", "Pakistani nationals")],
        }
        results = match_profile_to_scholarships(rows, criteria, {
            "target_study_level": "bachelors", "current_education_level": "intermediate",
            "nationality": "Pakistani",
        })
        self.assertEqual({item["id"] for item in results}, {3, 4})

    def test_intermediate_profile_excludes_university_level_awards(self):
        from app.matching import match_profile_to_scholarships
        rows = [
            {"id": 1, "title": "Bachelor's Scholarship"},
            {"id": 2, "title": "Intermediate Scholarship"},
        ]
        criteria = {
            1: [self.criterion("academic_requirements", "Study level", "For undergraduate applicants.")],
            2: [self.criterion("academic_requirements", "Study level", "For Intermediate applicants.")],
        }
        results = match_profile_to_scholarships(rows, criteria, {"target_study_level": "intermediate"})
        self.assertEqual([item["id"] for item in results], [2])

    def test_multi_level_masters_and_phd_award_remains_for_phd_profile(self):
        from app.matching import match_profile_to_scholarships
        rows = [{"id": 1, "title": "Commonwealth Master's and PhD Scholarship"}]
        criteria = {1: [self.criterion("academic_requirements", "Study level", "For Master's and PhD applicants.")]}
        results = match_profile_to_scholarships(rows, criteria, {"target_study_level": "phd"})
        self.assertEqual(len(results), 1)

    def test_pakistani_nationality_passes(self):
        result = evaluate_criterion(
            self.criterion("nationality", "Nationality", "Pakistani/AJK nationals"),
            {"nationality": "Pakistani"},
        )
        self.assertEqual(result["status"], "pass")


    def test_punjab_domicile_requirement_passes(self):
        c = self.criterion("nationality", "Domicile", "Applicant must have Punjab domicile.")
        self.assertEqual(evaluate_criterion(c, {"domicile_region": "Punjab"})["status"], "pass")

    def test_wrong_domicile_region_fails(self):
        c = self.criterion("nationality", "Domicile", "Applicant must have Punjab domicile.")
        self.assertEqual(evaluate_criterion(c, {"domicile_region": "Sindh"})["status"], "fail")

    def test_missing_domicile_region_needs_information(self):
        c = self.criterion("nationality", "Domicile", "Applicant must have Punjab domicile.")
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")

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


    def test_matric_student_meets_matric_requirement(self):
        c = self.criterion("academic_requirements", "Matric qualification", "Applicant must have passed Matric / SSC.")
        self.assertEqual(evaluate_criterion(c, {"current_education_level": "matric"})["status"], "pass")

    def test_matric_student_does_not_meet_intermediate_completed_requirement(self):
        c = self.criterion("academic_requirements", "Intermediate qualification", "Applicant must have completed Intermediate / HSSC.")
        self.assertEqual(evaluate_criterion(c, {"current_education_level": "matric"})["status"], "fail")

    def test_intermediate_student_meets_matric_requirement(self):
        c = self.criterion("academic_requirements", "Matric qualification", "Applicant must have passed Matriculation.")
        self.assertEqual(evaluate_criterion(c, {"current_education_level": "intermediate"})["status"], "pass")

    def test_school_student_marks_threshold_is_checked(self):
        c = self.criterion("academic_requirements", "Minimum marks", "At least 60% marks in Matric are required.")
        self.assertEqual(evaluate_criterion(c, {"current_education_level": "matric", "academic_percentage": 75})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"current_education_level": "matric", "academic_percentage": 55})["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {"current_education_level": "matric"})["status"], "unknown")

    def test_school_student_target_level_is_not_confused_with_current_level(self):
        c = self.criterion("academic_requirements", "Intermediate admission", "Scholarship for admission to Intermediate.")
        self.assertEqual(evaluate_criterion(c, {"current_education_level": "matric", "target_study_level": "intermediate"})["status"], "unknown")

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


class GermanScholarshipMatchingTests(unittest.TestCase):
    def criterion(self, kind, label, text, mandatory=True):
        return {
            "id": 99, "criterion_type": kind, "criterion_label": label,
            "requirement_text": text, "is_mandatory": mandatory,
            "evidence_url": "https://official.example/eligibility",
        }

    def test_german_b2_language_requirement_uses_profile_level(self):
        c = self.criterion("language_requirements", "German language", "German language skills of at least level B2.")
        self.assertEqual(evaluate_criterion(c, {"german_language_level": "B2"})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"german_language_level": "B1"})["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")

    def test_university_degree_and_experience_are_checked_separately(self):
        c = self.criterion("study_level", "Study requirements", "have a university degree and professional experience in your home country")
        self.assertEqual(evaluate_criterion(c, {
            "current_education_level": "bachelors",
            "professional_experience_years": 2,
        })["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {
            "current_education_level": "intermediate",
            "professional_experience_years": 2,
        })["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {
            "current_education_level": "bachelors",
        })["status"], "unknown")

    def test_preferred_language_is_not_a_mandatory_match_failure(self):
        c = self.criterion("language_requirements", "Language", "German language skills are preferred.", mandatory=False)
        self.assertEqual(evaluate_criterion(c, {})["status"], "informational")
