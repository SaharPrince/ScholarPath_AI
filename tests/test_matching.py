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

    def test_application_documents_are_informational_not_eligibility_gates(self):
        scholarship = {"id": 7, "title": "Test", "status": "unverified", "application_status": "open"}
        criteria = [self.criterion("required_documents", "Documents", "Submit transcript.", False)]
        result = match_scholarship(scholarship, criteria, {})
        self.assertEqual(result["match_status"], "needs_more_information")
        self.assertEqual(result["checks"][0]["status"], "informational")
        self.assertEqual(result["checks"][-1]["criterion_label"], "Eligibility criteria unavailable")
        self.assertEqual(result["checks"][-1]["status"], "unknown")

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

    def test_germany_residence_and_enrolment_conditions_are_matched_conservatively(self):
        residence = self.criterion("eligibility", "Residence duration", "Applicants must not have been in Germany for more than 15 months.")
        self.assertEqual(evaluate_criterion(residence, {})["status"], "unknown")
        self.assertEqual(evaluate_criterion(residence, {"months_in_germany": 12})["status"], "pass")
        self.assertEqual(evaluate_criterion(residence, {"months_in_germany": 16})["status"], "fail")

        enrolled = self.criterion("eligibility", "Current study", "Applicants must already be studying in Germany.")
        self.assertEqual(evaluate_criterion(enrolled, {})["status"], "unknown")
        self.assertEqual(evaluate_criterion(enrolled, {"currently_enrolled_in_germany": True})["status"], "pass")
        self.assertEqual(evaluate_criterion(enrolled, {"currently_enrolled_in_germany": False})["status"], "fail")

    def test_kaad_residence_permit_and_remaining_programme_conditions(self):
        permit = self.criterion("eligibility", "Residence permit", "Hold a residence permit for study purposes.")
        self.assertEqual(evaluate_criterion(permit, {})["status"], "unknown")
        self.assertEqual(evaluate_criterion(permit, {"german_residence_permit": "study"})["status"], "pass")
        self.assertEqual(evaluate_criterion(permit, {"german_residence_permit": "other"})["status"], "fail")

        remaining = self.criterion("eligibility", "Programme duration", "Have at least six months remaining in your programme.")
        self.assertEqual(evaluate_criterion(remaining, {"months_remaining_in_program": 8})["status"], "pass")
        self.assertEqual(evaluate_criterion(remaining, {"months_remaining_in_program": 4})["status"], "fail")

    def test_apprenticeship_specific_conditions_are_matched(self):
        year = self.criterion("eligibility", "Training year", "Be at the beginning of the first and no later than the beginning of the second Ausbildungsjahr.")
        self.assertEqual(evaluate_criterion(year, {"apprenticeship_year": 2})["status"], "pass")
        self.assertEqual(evaluate_criterion(year, {"apprenticeship_year": 3})["status"], "fail")
        recognized = self.criterion("eligibility", "Recognized occupation", "Learn a staatlich anerkannten Ausbildungsberuf.")
        self.assertEqual(evaluate_criterion(recognized, {"recognized_apprenticeship": True})["status"], "pass")
        contract = self.criterion("eligibility", "Training contract", "Have an Ausbildungsvertrag or written confirmation of a training place.")
        self.assertEqual(evaluate_criterion(contract, {"has_training_contract": False})["status"], "fail")

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

    def test_financial_need_is_not_inferred_or_requested(self):
        c = self.criterion("eligibility", "Financial need", "Applicants must demonstrate financial need.")
        result = evaluate_criterion(c, {})
        self.assertEqual(result["status"], "unknown")
        self.assertIn("does not ask for income", result["explanation"])

    def test_sensitive_personal_conditions_are_left_for_private_provider_review(self):
        examples = [
            ("Disability", "Applicants with a disability may apply."),
            ("Religion", "Applicants must belong to the Protestant denomination."),
            ("Refugee status", "Applicants must have refugee status."),
            ("Gender", "This scholarship is for women applicants."),
            ("Care responsibilities", "Applicants caring for minor children are eligible."),
        ]
        for label, requirement in examples:
            with self.subTest(label=label):
                result = evaluate_criterion(self.criterion("eligibility", label, requirement), {})
                self.assertEqual(result["status"], "unknown")
                self.assertIn("does not ask you to disclose", result["explanation"])

    def test_named_university_enrolment_requires_name_and_confirmation(self):
        c = self.criterion("eligibility", "Enrolment", "Applicants must be currently enrolled at the University of Würzburg.")
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")
        self.assertEqual(evaluate_criterion(c, {"current_university_name": "University of Würzburg"})["status"], "unknown")
        self.assertEqual(evaluate_criterion(c, {
            "current_university_name": "University of Würzburg",
            "currently_enrolled_at_current_university": True,
        })["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {
            "current_university_name": "TU Berlin",
            "currently_enrolled_at_current_university": True,
        })["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {
            "current_university_name": "University of Würzburg",
            "currently_enrolled_at_current_university": False,
        })["status"], "fail")

    def test_university_name_without_enrolment_confirmation_remains_unknown(self):
        c = self.criterion("institution_eligibility", "TU Berlin students", "International students enrolled at TU Berlin.")
        self.assertEqual(evaluate_criterion(c, {
            "current_university_name": "TU Berlin",
        })["status"], "unknown")

    def test_preferred_language_is_not_a_mandatory_match_failure(self):
        c = self.criterion("language_requirements", "Language", "German language skills are preferred.", mandatory=False)
        self.assertEqual(evaluate_criterion(c, {})["status"], "informational")


    def test_unspecified_german_proficiency_remains_unknown(self):
        c = self.criterion("language_requirements", "German language", "Applicants must have good German language skills.")
        self.assertEqual(evaluate_criterion(c, {"german_language_level": "A1"})["status"], "unknown")
        self.assertEqual(evaluate_criterion(c, {"german_language_level": "C1"})["status"], "unknown")


class GermanStudyLevelFilteringTests(unittest.TestCase):
    def criterion(self, kind, label, text, mandatory=True):
        return {
            "id": 99, "criterion_type": kind, "criterion_label": label,
            "requirement_text": text, "is_mandatory": mandatory,
            "evidence_url": "https://official.example/eligibility",
        }

    def test_master_profile_excludes_german_doctoral_scholarship(self):
        from app.matching import match_profile_to_scholarships
        rows = [{"id": 91, "title": "Promotionsstipendium"}]
        criteria = {91: [self.criterion("study_level", "Academic qualification", "Promotionszulassung an einer deutschen Hochschule erforderlich.")]}
        self.assertEqual(match_profile_to_scholarships(rows, criteria, {"target_study_level": "master"}), [])

    def test_master_profile_excludes_apprenticeship_scholarship(self):
        from app.matching import match_profile_to_scholarships
        rows = [{"id": 92, "title": "Stipendium für Auszubildende"}]
        criteria = {92: [self.criterion("eligibility", "Applicant type", "Applicants must have an Ausbildungsvertrag.")]}
        self.assertEqual(match_profile_to_scholarships(rows, criteria, {"target_study_level": "master"}), [])

    def test_vocational_training_profile_keeps_apprenticeship_award(self):
        from app.matching import match_profile_to_scholarships
        rows = [{"id": 93, "title": "Stipendium für Auszubildende"}]
        criteria = {93: [self.criterion("eligibility", "Applicant type", "Applicants must have an Ausbildungsvertrag.")]}
        results = match_profile_to_scholarships(rows, criteria, {"target_study_level": "vocational_training"})
        self.assertEqual([item["id"] for item in results], [93])


    def test_master_profile_excludes_hyphenated_german_doctoral_award(self):
        from app.matching import match_profile_to_scholarships
        rows = [{"id": 94, "title": "Promotions-förderung"}]
        criteria = {94: [self.criterion("study_level", "Academic qualification", "Promotionsstipendium für Doktorandinnen.")]}
        self.assertEqual(match_profile_to_scholarships(rows, criteria, {"target_study_level": "master"}), [])
