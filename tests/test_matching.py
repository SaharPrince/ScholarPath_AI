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

    def test_kaad_combined_enrolment_and_six_months_rule_checks_both_conditions(self):
        criterion = self.criterion(
            "eligibility",
            "Current study and remaining duration",
            "You are already studying in Germany and have at least six months remaining in your programme.",
        )
        self.assertEqual(evaluate_criterion(criterion, {})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(criterion, {"currently_enrolled_in_germany": False, "months_remaining_in_program": 8})["status"],
            "fail",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"currently_enrolled_in_germany": True})["status"],
            "unknown",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"currently_enrolled_in_germany": True, "months_remaining_in_program": 5})["status"],
            "fail",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"currently_enrolled_in_germany": True, "months_remaining_in_program": 6})["status"],
            "pass",
        )


    def test_tu_berlin_current_student_route_checks_university_and_two_semesters(self):
        criterion = self.criterion(
            "category_i_eligibility",
            "Current TU Berlin students",
            "Regularly enrolled Bachelor's and Master's students already enrolled at TU Berlin at the beginning of the upcoming winter-semester funding period must still have at least two semesters remaining within the standard period of study.",
        )
        self.assertEqual(evaluate_criterion(criterion, {})["status"], "unknown")
        base = {
            "current_university_name": "TU Berlin",
            "currently_enrolled_at_current_university": True,
        }
        self.assertEqual(evaluate_criterion(criterion, base)["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(criterion, {**base, "remaining_semesters_in_program": 1})["status"],
            "fail",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {**base, "remaining_semesters_in_program": 2})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {
                **base, "remaining_semesters_in_program": 2, "current_university_name": "University of Kiel"
            })["status"],
            "fail",
        )

    def test_tu_berlin_prospective_student_route_uses_application_not_enrolment(self):
        criterion = self.criterion(
            "category_ii_eligibility",
            "Prospective TU Berlin students",
            "Prospective students who have applied to begin their studies at TU Berlin in the upcoming winter semester may apply; TU Berlin verifies enrolment in the degree programme before awarding the scholarship.",
        )
        self.assertEqual(evaluate_criterion(criterion, {})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(criterion, {"applied_to_current_university": True})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"applied_to_current_university": False})["status"],
            "fail",
        )

    def test_tu_berlin_current_and_prospective_routes_are_alternatives(self):
        from app.matching import match_scholarship
        current = self.criterion(
            "category_i_eligibility", "Current students",
            "Already enrolled at TU Berlin with at least two semesters remaining."
        )
        prospective = self.criterion(
            "category_ii_eligibility", "Prospective students",
            "Have applied to begin studies at TU Berlin in the upcoming winter semester."
        )
        result = match_scholarship(
            {"id": 77, "title": "TU Berlin Deutschlandstipendium"},
            [current, prospective],
            {"applied_to_current_university": True},
        )
        self.assertEqual(result["match_status"], "likely_eligible")
        self.assertEqual(result["checks"][0]["status"], "informational")
        self.assertEqual(result["checks"][1]["status"], "pass")

    def test_financial_challenges_remain_manual_provider_review(self):
        criterion = self.criterion(
            "eligibility",
            "Financial circumstances",
            "Applicants must be facing financial challenges during their studies.",
        )
        result = evaluate_criterion(criterion, {})
        self.assertEqual(result["status"], "unknown")
        self.assertIn("does not ask for income", result["explanation"])

    def test_two_remaining_semesters_rule_is_matched_exactly(self):
        criterion = self.criterion(
            "eligibility",
            "Remaining study duration",
            "You must still have two remaining semesters before you complete your studies.",
        )
        self.assertEqual(evaluate_criterion(criterion, {})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(criterion, {"remaining_semesters_in_program": 2})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"remaining_semesters_in_program": 3})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"remaining_semesters_in_program": 1})["status"],
            "fail",
        )

    def test_four_remaining_semesters_rule_is_matched_exactly(self):
        criterion = self.criterion(
            "eligibility",
            "Remaining standard study duration",
            "At the time of application, you must have at least four semesters of standard study duration remaining.",
        )
        self.assertEqual(evaluate_criterion(criterion, {})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(criterion, {"remaining_semesters_in_program": 4})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"remaining_semesters_in_program": 5})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"remaining_semesters_in_program": 3})["status"],
            "fail",
        )

    def test_apprenticeship_specific_conditions_are_matched(self):
        year = self.criterion("eligibility", "Training year", "Be at the beginning of the first and no later than the beginning of the second Ausbildungsjahr.")
        self.assertEqual(evaluate_criterion(year, {"apprenticeship_year": 1})["status"], "pass")
        self.assertEqual(evaluate_criterion(year, {"apprenticeship_year": 2})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(year, {"apprenticeship_year": 2, "apprenticeship_second_year_stage": "beginning"})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(year, {"apprenticeship_year": 2, "apprenticeship_second_year_stage": "later"})["status"],
            "fail",
        )
        self.assertEqual(evaluate_criterion(year, {"apprenticeship_year": 3})["status"], "fail")
        recognized = self.criterion("eligibility", "Recognized occupation", "Learn a staatlich anerkannten Ausbildungsberuf.")
        self.assertEqual(evaluate_criterion(recognized, {"recognized_apprenticeship": True})["status"], "pass")
        contract = self.criterion("eligibility", "Training contract", "Have an Ausbildungsvertrag or written confirmation of a training place.")
        self.assertEqual(evaluate_criterion(contract, {"has_training_contract": False})["status"], "fail")

    def test_rosa_apprenticeship_age_exception_is_not_an_automatic_rejection(self):
        age = self.criterion(
            "age_limit",
            "Age",
            "Du bist jünger als 45 Jahre. Manchmal gibt es Ausnahmen, zum Beispiel bei einer Zweitausbildung.",
        )
        self.assertEqual(evaluate_criterion(age, {"age": 40})["status"], "pass")
        self.assertEqual(evaluate_criterion(age, {"age": 46})["status"], "unknown")

    def test_apprenticeship_recognition_accepts_bbig_and_state_regulated_wording(self):
        for wording in (
            "Eine Ausbildung nach BBiG oder HwO absolvieren.",
            "Eine bundesgesetzlich geregelte Fachausbildung im Gesundheitswesen absolvieren.",
            "An equivalent state-regulated vocational occupation absolvieren.",
        ):
            with self.subTest(wording=wording):
                c = self.criterion("eligibility", "Recognised training", wording)
                self.assertEqual(
                    evaluate_criterion(c, {"recognized_apprenticeship": True})["status"],
                    "pass",
                )

    def test_political_engagement_is_not_requested_in_profile(self):
        c = self.criterion("eligibility", "Engagement", "Applicants demonstrate social or political engagement.")
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")

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


    def test_age_over_35_explicitly_allowed_by_provider_is_not_failure(self):
        c = self.criterion(
            "age_limit",
            "Age",
            "I am older than 35. Can I apply for a scholarship for the doctorate? Yes.",
        )
        result = evaluate_criterion(c, {"age": 42})
        self.assertEqual(result["status"], "informational")
        self.assertIn("explicitly allows applicants above the stated age", result["explanation"])

    def test_villigst_requires_doctoral_admission_not_university_enrolment(self):
        admission = self.criterion(
            "doctoral_admission", "Admission to doctoral studies",
            "Applicants must provide evidence of admission (authorisation) to do a doctorate.",
        )
        self.assertEqual(evaluate_criterion(admission, {})["status"], "unknown")
        self.assertEqual(evaluate_criterion(admission, {"doctoral_admission_confirmed": True})["status"], "pass")
        self.assertEqual(evaluate_criterion(admission, {"doctoral_admission_confirmed": False})["status"], "fail")

        not_enrolled = self.criterion(
            "application_requirements", "Doctoral enrolment clarification",
            "Applicants do not have to be enrolled at the university during the doctorate.",
            mandatory=False,
        )
        self.assertEqual(evaluate_criterion(not_enrolled, {})["status"], "informational")

    def test_villigst_final_phase_is_a_real_exclusion_and_unknown_is_not_failed(self):
        criterion = self.criterion(
            "doctoral_project_stage", "Doctoral project stage",
            "Applicants whose doctoral project is already in its final phase cannot be considered.",
        )
        self.assertEqual(evaluate_criterion(criterion, {})["status"], "unknown")
        self.assertEqual(evaluate_criterion(criterion, {"doctoral_project_final_phase": False})["status"], "pass")
        self.assertEqual(evaluate_criterion(criterion, {"doctoral_project_final_phase": True})["status"], "fail")

    def test_age_over_45_with_special_application_is_not_automatic_failure(self):
        c = self.criterion(
            "age_limit",
            "Age",
            "Applicants who are older than 45 must also enclose a special application.",
        )
        result = evaluate_criterion(c, {"age": 52})
        self.assertEqual(result["status"], "informational")
        self.assertIn("not an automatic age-based rejection", result["explanation"])

if __name__ == "__main__":
    unittest.main()


class GermanScholarshipMatchingTests(unittest.TestCase):
    def criterion(self, kind, label, text, mandatory=True):
        return {
            "id": 99, "criterion_type": kind, "criterion_label": label,
            "requirement_text": text, "is_mandatory": mandatory,
            "evidence_url": "https://official.example/eligibility",
        }

    def test_oskar_karl_forster_second_semester_rule_exempts_masters(self):
        criterion = self.criterion(
            "study_level",
            "Minimum study semester",
            "Applicants in non-Master's programmes must be enrolled from the second semester onwards; the second-semester restriction does not apply to Master's students.",
        )
        self.assertEqual(evaluate_criterion(criterion, {})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(criterion, {"target_study_level": "bachelors", "current_semester_in_program": 1})["status"],
            "fail",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"target_study_level": "bachelors", "current_semester_in_program": 2})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"current_semester_in_program": 2})["status"],
            "unknown",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"target_study_level": "master"})["status"],
            "pass",
        )

    def test_heinrich_boll_masters_part_time_rule_does_not_reject_phd_applicants(self):
        criterion = self.criterion(
            "study_level",
            "Master's study format",
            "For Master's applicants, part-time degree programmes are not eligible for funding.",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"target_study_level": "master"})["status"],
            "fail",
        )
        self.assertEqual(
            evaluate_criterion(criterion, {"target_study_level": "phd"})["status"],
            "informational",
        )

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


    def test_fes_bachelor_application_window_checks_both_semester_conditions(self):
        c = self.criterion(
            "eligibility",
            "Application timing",
            "Applications are accepted after the first semester and until three semesters before the end of the standard study period.",
        )
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(c, {"current_semester_in_program": 2, "remaining_semesters_in_program": 3})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"current_semester_in_program": 1, "remaining_semesters_in_program": 4})["status"],
            "fail",
        )
        self.assertEqual(
            evaluate_criterion(c, {"current_semester_in_program": 3, "remaining_semesters_in_program": 2})["status"],
            "fail",
        )

    def test_fes_master_application_is_limited_to_before_or_beginning_of_first_semester(self):
        c = self.criterion(
            "study_level",
            "Master application timing",
            "Apply before or at the beginning of the first semester of the Master's programme.",
        )
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")
        self.assertEqual(evaluate_criterion(c, {"first_semester_timing": "not_started"})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"first_semester_timing": "at_beginning"})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"first_semester_timing": "after_beginning"})["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {"first_semester_timing": "later_semester"})["status"], "fail")

    def test_fes_medical_student_window_is_after_fourth_through_sixth_semester(self):
        c = self.criterion(
            "eligibility",
            "Medical study application timing",
            "Medical students may apply after the fourth semester until the end of the sixth semester.",
        )
        self.assertEqual(evaluate_criterion(c, {"current_semester_in_program": 5})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"current_semester_in_program": 4})["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {"current_semester_in_program": 7})["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")

    def test_rosa_luxemburg_half_standard_duration_rule(self):
        c = self.criterion(
            "eligibility",
            "Remaining study duration",
            "At least half of the standard study period must remain at the start of funding.",
        )
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(c, {"remaining_semesters_in_program": 3, "standard_programme_semesters": 6})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"remaining_semesters_in_program": 2, "standard_programme_semesters": 6})["status"],
            "fail",
        )

    def test_rosa_luxemburg_15_month_rule_respects_published_exceptions(self):
        c = self.criterion(
            "eligibility",
            "Residence duration",
            "You must not have been in Germany for more than 15 months unless you have already studied in Germany or are preparing for university studies.",
        )
        self.assertEqual(evaluate_criterion(c, {"months_in_germany": 18})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(c, {"months_in_germany": 18, "residence_duration_exception": "prior_study"})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"months_in_germany": 18, "residence_duration_exception": "study_preparation"})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"months_in_germany": 18, "residence_duration_exception": "none"})["status"],
            "fail",
        )

    def test_rosa_luxemburg_international_study_requires_completed_bachelors(self):
        c = self.criterion(
            "study_level",
            "Academic qualification",
            "Proof of a completed Bachelor's degree is required.",
        )
        self.assertEqual(
            evaluate_criterion(c, {"current_education_level": "bachelors"})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"current_education_level": "intermediate"})["status"],
            "fail",
        )

    def test_explicit_excluded_study_level_is_not_mistaken_for_eligible(self):
        c = self.criterion(
            "study_level",
            "Excluded study levels",
            "Bachelor's programmes are not eligible for this international scholarship.",
        )
        self.assertEqual(evaluate_criterion(c, {"target_study_level": "bachelors"})["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {"target_study_level": "master"})["status"], "informational")

    def test_fes_german_bachelor_timing_wording_is_supported(self):
        c = self.criterion(
            "eligibility",
            "Bewerbungszeitpunkt",
            "Bewerbung nach dem ersten Semester und bis drei Semester vor Ende der Regelstudienzeit.",
        )
        self.assertEqual(
            evaluate_criterion(c, {"current_semester_in_program": 2, "remaining_semesters_in_program": 3})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"current_semester_in_program": 1, "remaining_semesters_in_program": 4})["status"],
            "fail",
        )

    def test_fes_german_master_timing_wording_is_supported(self):
        c = self.criterion(
            "study_level",
            "Bewerbungszeitpunkt",
            "Bewerbung vor oder zu Beginn des ersten Hochschulsemesters.",
        )
        self.assertEqual(evaluate_criterion(c, {"first_semester_timing": "not_started"})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"first_semester_timing": "at_beginning"})["status"], "pass")
        self.assertEqual(evaluate_criterion(c, {"first_semester_timing": "after_beginning"})["status"], "fail")
        self.assertEqual(evaluate_criterion(c, {"first_semester_timing": "later_semester"})["status"], "fail")

    def test_rosa_german_four_semester_threshold_is_supported(self):
        c = self.criterion(
            "eligibility",
            "Förderzeitraum",
            "Zum Förderbeginn müssen noch mindestens 4 Semester der Regelstudienzeit verbleiben.",
        )
        self.assertEqual(
            evaluate_criterion(c, {"remaining_semesters_in_program": 4})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"remaining_semesters_in_program": 3})["status"],
            "fail",
        )

    def test_rosa_german_residence_exception_is_supported(self):
        c = self.criterion(
            "eligibility",
            "Aufenthaltsdauer",
            "Sie dürfen sich zum Zeitpunkt der Bewerbung nicht länger als 15 Monate in Deutschland aufhalten. Ausnahme: Sie haben bereits in Deutschland studiert oder sich gezielt auf das Studium vorbereitet.",
        )
        self.assertEqual(
            evaluate_criterion(c, {"months_in_germany": 18, "residence_duration_exception": "prior_study"})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"months_in_germany": 18, "residence_duration_exception": "none"})["status"],
            "fail",
        )

    def test_doctoral_admission_is_checked_even_when_extracted_as_study_level(self):
        c = self.criterion(
            "study_level",
            "Promotionszulassung",
            "Ausländische Promovierende müssen an einer deutschen Hochschule zur Promotion zugelassen sein.",
        )
        self.assertEqual(evaluate_criterion(c, {})["status"], "unknown")
        self.assertEqual(
            evaluate_criterion(c, {"doctoral_admission_confirmed": True})["status"],
            "pass",
        )
        self.assertEqual(
            evaluate_criterion(c, {"doctoral_admission_confirmed": False})["status"],
            "fail",
        )

    def test_political_alignment_is_not_requested_or_inferred(self):
        c = self.criterion(
            "eligibility",
            "Values",
            "Applicants must identify with the values of social democracy.",
        )
        result = evaluate_criterion(c, {})
        self.assertEqual(result["status"], "unknown")
        self.assertIn("does not ask you to disclose", result["explanation"])

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
