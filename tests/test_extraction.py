import sqlite3
import unittest

from app.extraction import (
    _clean, _classify_application_status, _classify_applicant_category,
    _parse_deadline_date, _find_application_url, _is_mandatory_criterion, _extract_description_criteria, _split_criteria_statements, parse_scholarship_page, _save_evidence,
)


class ScholarshipPageExtractionTests(unittest.TestCase):
    def test_repairs_known_joined_words_from_official_source_copy(self) -> None:
        cleaned = _clean(
            "permanentresident eligiblefields onbehalf of residents of Pakistan "
            "14–15 years ofeducation four-yearbachelor Afterselection "
            "InstitutionalTOEFL Applicantsmust apply "
            "one of thelisted eligiblefields subject tothe rule "
            "at least 5 yearsofexperience in the UnitedStates OR(2) route "
            "three-year degree holders mayapply; permanentresidency; Department of Stateemployees; "
            "academic,training, or research programs"
        )
        self.assertEqual(
            cleaned,
            "permanent resident eligible fields on behalf of residents of Pakistan "
            "14–15 years of education four-year bachelor After selection "
            "Institutional TOEFL Applicants must apply "
            "one of the listed eligible fields subject to the rule "
            "at least 5 years of experience in the United States OR (2) route "
            "three-year degree holders may apply; permanent residency; Department of State employees; "
            "academic, training, or research programs",
        )

    def test_extracts_visible_facts_and_keeps_evidence(self) -> None:
        html = """
        <html><head>
          <meta name="description" content="Funding for postgraduate study.">
          <meta property="og:site_name" content="Example Foundation">
        </head><body>
          <h1>Example Global Scholarship</h1>
          <p>Scholarship provider: Example Foundation</p>
          <p>Application deadline: 30 September 2027</p>
          <p>Funding: Full tuition and monthly stipend</p>
          <p>Eligibility: Applicants must be citizens of Pakistan.</p>
        </body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.title, "Example Global Scholarship")
        self.assertEqual(page.provider_name, "Example Foundation")
        self.assertEqual(page.fields["deadline_text"], "30 September 2027")
        self.assertEqual(page.fields["funding_summary"], "Full tuition and monthly stipend")
        self.assertEqual(page.fields["eligibility"], "Applicants must be citizens of Pakistan.")
        self.assertTrue(all(snippet for _, snippet in page.evidence))

    def test_insufficient_page_returns_none(self) -> None:
        self.assertIsNone(
            parse_scholarship_page(
                "<html><body><h1>Welcome</h1><p>Contact our office.</p></body></html>",
                "https://example.org/",
            )
        )

    def test_normalizes_explicit_deadline_date(self) -> None:
        self.assertEqual(_parse_deadline_date("August 1, 2020"), "2020-08-01")
        self.assertEqual(_parse_deadline_date("30 September 2027"), "2027-09-30")


    def test_ignores_navigation_and_footer_text(self) -> None:
        html = """
        <html><body>
          <nav><p>Eligibility</p><p>University Partnerships</p></nav>
          <main>
            <h1>Example Fellowship Programme</h1>
            <p>Application deadline: 15 March 2027</p>
            <p>Eligibility: Applicants must be Pakistani citizens with a completed bachelor's degree.</p>
            <p>Funding: Full tuition and a monthly stipend.</p>
          </main>
          <footer><p>Eligibility: University Partnerships</p></footer>
        </body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/fellowship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(
            page.fields["eligibility"],
            "Applicants must be Pakistani citizens with a completed bachelor's degree.",
        )

    def test_rejects_title_like_eligibility_value(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <p>Eligibility</p>
          <p>University Partnerships</p>
          <p>Application deadline: 15 March 2027</p>
          <p>Funding: Full tuition award.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertNotIn("eligibility", page.fields)

    def test_does_not_invent_date_for_rolling_deadline(self) -> None:
        self.assertIsNone(_parse_deadline_date("Applications accepted throughout the year"))
        self.assertIsNone(_parse_deadline_date("All year around"))

    def test_past_deadline_marks_that_cycle_closed(self) -> None:
        self.assertEqual(_classify_application_status("Application deadline: 1 January 2020", "2020-01-01"), "closed")

    def test_future_deadline_alone_does_not_mean_open(self) -> None:
        self.assertEqual(_classify_application_status("Application deadline: 1 January 2099", "2099-01-01"), "unknown")

    def test_explicit_open_and_upcoming_language(self) -> None:
        self.assertEqual(_classify_application_status("Applications are now open", None), "open")
        self.assertEqual(_classify_application_status("Applications will open in October", None), "upcoming")

    def test_rolling_and_discontinued_statuses(self) -> None:
        self.assertEqual(_classify_application_status("Applications accepted throughout the year", None), "open")
        self.assertEqual(_classify_application_status("This programme has been discontinued", None), "discontinued")

    def test_applicant_category_requires_clear_language(self) -> None:
        self.assertEqual(_classify_applicant_category("Designed for mid-career professionals"), "professional")
        self.assertEqual(_classify_applicant_category("For currently enrolled undergraduate students"), "student")
        self.assertEqual(_classify_applicant_category("A programme for interested people"), "unknown")

    def test_classifies_senior_us_scholars_and_professionals(self) -> None:
        self.assertEqual(
            _classify_applicant_category(
                "The program allows senior U.S. scholars and professionals."
            ),
            "professional",
        )

    def test_classifies_officials_and_administrators_as_professionals(self) -> None:
        self.assertEqual(
            _classify_applicant_category(
                "For Pakistani officials with higher education planning responsibilities "
                "and administrators from post-secondary institutions."
            ),
            "professional",
        )

    def test_faculty_training_precedes_degree_title_classification(self) -> None:
        self.assertEqual(
            _classify_applicant_category(
                "HEC UESTP Faculty Training Programme - Master Leading to PhD"
            ),
            "faculty",
        )

    def test_extracts_heading_based_eligibility_and_prose_funding(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Master's Scholarship</h1>
          <h2>Eligibility Criteria</h2>
          <ul>
            <li>Applicants must be citizens of Pakistan.</li>
            <li>Applicants must hold a bachelor's degree.</li>
            <li>Applicants must apply for a master's programme.</li>
          </ul>
          <h2>Financial Support</h2>
          <p>The scholarship covers tuition fees and provides a stipend for living costs.</p>
          <p>Applications are now open.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/masters-scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("citizens of Pakistan", page.fields["eligibility"])
        self.assertIn("bachelor's degree", page.fields["eligibility"])
        self.assertIn("scholarship covers tuition fees", page.fields["funding_summary"])
        self.assertTrue(any(name == "eligibility" for name, _ in page.evidence))
        self.assertEqual(page.applicant_category, "student")

    def test_applicant_category_ignores_unrelated_page_references(self) -> None:
        self.assertEqual(
            _classify_applicant_category("Example Degree Scholarship for master's applicants"),
            "student",
        )
        self.assertEqual(
            _classify_applicant_category("Example scholarship for master's applicants"),
            "student",
        )

    def test_extracts_explicit_provider_and_study_destination(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Graduate Scholarship</h1>
          <p>The scholarship is managed by Example Foundation under its international programme.</p>
          <p>The scholarship funds graduate study at universities all over the United States for a Master's degree.</p>
          <p>Eligibility: Pakistani citizens with a bachelor's degree may apply.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarships/example")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.provider_name, "Example Foundation")
        self.assertEqual(page.fields["study_destination"], "United States")
        self.assertIn(("provider_name", "Example Foundation"), page.evidence)
        self.assertIn(("study_destination", "United States"), page.evidence)

    def test_extracts_explicit_application_link(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <p>Eligibility: Pakistani citizens with a bachelor's degree may apply.</p>
          <h2>How to Apply</h2>
          <p>Complete the online application.</p>
          <a href="https://apply.example.edu/start">Apply Now</a>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.fields["application_url"], "https://apply.example.edu/start")
        self.assertIn(("application_url", "https://apply.example.edu/start"), page.evidence)

    def test_does_not_treat_source_page_or_document_as_application_url(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <p>Eligibility: Pakistani citizens with a bachelor's degree may apply.</p>
          <h2>How to Apply</h2>
          <a href="#instructions">Apply</a>
          <a href="/scholarship">Apply Now</a>
          <a href="/application-guide.pdf">Application Form</a>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertNotIn("application_url", page.fields)

    def test_ambiguous_application_links_are_not_guessed(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <p>Eligibility: Pakistani citizens with a bachelor's degree may apply.</p>
          <a href="https://apply-one.example.edu">Apply Now</a>
          <a href="https://apply-two.example.edu">Apply Now</a>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertNotIn("application_url", page.fields)

    def test_extracts_additional_heading_based_eligibility_categories(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Master's Scholarship</h1>
          <h2>Eligibility</h2>
          <p>Eligibility: Applicants must be enrolled in a recognized university.</p>
          <ul><li>Applicants must be Pakistani citizens.</li></ul>
          <h2>Academic Requirements</h2>
          <ul><li>Applicants must have a minimum GPA of 3.0.</li></ul>
          <h2>Age Limit</h2>
          <p>Applicants must be under 35 years old.</p>
          <h2>Required Documents</h2>
          <ul><li>Applicants must submit academic transcripts.</li></ul>
          <h2>Language Requirements</h2>
          <p>Applicants must provide proof of English proficiency.</p>
          <h2>Degree Level</h2>
          <p>Applicants must apply for a master's degree.</p>
          <p>The scholarship provides financial support for postgraduate study.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/masters-scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        for field in (
            "eligibility", "academic_requirements", "age_limit",
            "required_documents", "language_requirements", "study_level",
        ):
            self.assertIn(field, page.fields)
            self.assertTrue(page.fields[field])
        self.assertIn("recognized university", page.fields["eligibility"])
        self.assertIn("Pakistani citizens", page.fields["eligibility"])
        criterion_types = {criterion[0] for criterion in page.criteria}
        self.assertTrue({
            "eligibility", "academic_requirements", "age_limit",
            "required_documents", "language_requirements", "study_level",
        }.issubset(criterion_types))

    def test_extracts_explicit_eligibility_from_description_prose(self) -> None:
        description = (
            "The Community College Initiative Program supports Pakistani professionals. "
            "The applicants must be resident in Pakistan, currently employed in a listed field, "
            "have 14-15 years of education, English language proficiency and demonstrated leadership. "
            "Participants return home after the programme."
        )
        criteria = _extract_description_criteria(description)
        self.assertEqual(len(criteria), 1)
        self.assertEqual(criteria[0][0], "eligibility")
        self.assertIn("must be resident in Pakistan", criteria[0][2])

    def test_distinguishes_host_institution_eligibility_from_applicant_eligibility(self) -> None:
        description = (
            "Non-U.S. post-secondary academic institutions are eligible to host a U.S. scholar. "
            "Projects must be approved by the programme administrator."
        )
        criteria = _extract_description_criteria(description)
        self.assertEqual(len(criteria), 1)
        self.assertEqual(criteria[0][0], "institution_eligibility")

    def test_rejects_malformed_host_eligibility_sentence_but_keeps_clean_host_rule(self) -> None:
        description = (
            "Non-U.S. post-secondary academic institutions are eligible to host a U.S. "
            "scholar or profession although the Fulbright Specialists Program."
        )
        self.assertEqual(_extract_description_criteria(description), [])

        clean_description = (
            "Non-U.S. post-secondary academic institutions are eligible to host a U.S. scholar."
        )
        criteria = _extract_description_criteria(clean_description)
        self.assertEqual(len(criteria), 1)
        self.assertEqual(criteria[0][0], "institution_eligibility")

    def test_recognizes_shortlisted_only_restriction(self) -> None:
        self.assertEqual(
            _classify_application_status(
                "This information is only for candidates who have been shortlisted by HEC.",
                None,
            ),
            "shortlisted_only",
        )

    def test_sentence_splitter_preserves_academic_abbreviations_and_initials(self) -> None:
        statements = _split_criteria_statements(
            "Employees of the Fulbright organization or the U.S. Department of State are ineligible. "
            "The programme honours the memory of Hubert H. Humphrey. Applicants must hold a Ph.D."
        )
        self.assertEqual(len(statements), 3)
        self.assertIn("U.S. Department of State", statements[0])
        self.assertIn("Hubert H. Humphrey", statements[1])
        self.assertIn("Ph.D.", statements[2])

    def test_heading_eligibility_keeps_list_items_as_separate_criteria(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship</h1>
          <h2>Eligibility Criteria</h2>
          <ul>
            <li>Applicants must be citizens of Pakistan.</li>
            <li>Applicants must hold a bachelor's degree.</li>
            <li>Applicants with science backgrounds are particularly encouraged.</li>
          </ul>
          <p>Funding: The scholarship provides tuition support and a stipend.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        eligibility = [item for item in page.criteria if item[0] == "eligibility"]
        self.assertEqual(len(eligibility), 3)
        self.assertTrue(_is_mandatory_criterion(eligibility[0][0], eligibility[0][2]))
        self.assertFalse(_is_mandatory_criterion(eligibility[2][0], eligibility[2][2]))

    def test_mandatory_criteria_classification_is_conservative(self) -> None:
        self.assertTrue(_is_mandatory_criterion("eligibility", "Applicants must hold a bachelor's degree."))
        self.assertTrue(_is_mandatory_criterion("ineligibility", "Applicants with dual nationality are not eligible."))
        self.assertTrue(_is_mandatory_criterion("required_documents", "Academic transcripts and reference letters."))
        self.assertFalse(_is_mandatory_criterion("eligibility", "Applicants with science backgrounds are particularly encouraged."))
        self.assertFalse(_is_mandatory_criterion("eligibility", "Relevant experience is preferred."))

    def test_deadline_only_page_is_not_promoted(self) -> None:
        html = """<html><body><main>
          <h1>Example Scholarship</h1>
          <p>Application deadline: 1 January 2020</p>
        </main></body></html>"""
        self.assertIsNone(parse_scholarship_page(html, "https://example.org/scholarship"))


    def test_explicit_official_current_status_overrides_date_inference(self) -> None:
        self.assertEqual(
            _classify_application_status("Deadline: 1 January 2099", "2099-01-01", "Closed"),
            "closed",
        )
        self.assertEqual(
            _classify_application_status("Deadline: 1 January 2020", "2020-01-01", "Open"),
            "open",
        )
        self.assertEqual(
            _classify_application_status("Some programme information", None, "Upcoming"),
            "upcoming",
        )

    def test_extracts_current_status_from_official_table(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Fellowship Programme</h1>
          <table>
            <tr><td>Current Status</td><td>Closed</td></tr>
            <tr><td>Deadline</td><td>April 1, 2099</td></tr>
          </table>
          <p>Eligibility: Applicants must be citizens of Pakistan.</p>
          <p>Funding: The programme provides a full tuition scholarship.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarships/fellowship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.fields["application_status"], "Closed")
        self.assertEqual(page.fields["deadline_text"], "April 1, 2099")
        self.assertEqual(page.application_status, "closed")
        self.assertIn(("application_status", "Closed"), page.evidence)


    def test_evidence_is_append_only_and_exact_duplicates_are_skipped(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.execute("""
            CREATE TABLE scholarship_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scholarship_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                evidence_text TEXT NOT NULL,
                evidence_url TEXT NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        _save_evidence(
            connection, 1,
            [("deadline_text", "April 1, 2026")],
            "https://example.org/scholarship",
        )
        _save_evidence(
            connection, 1,
            [("deadline_text", "April 1, 2026")],
            "https://example.org/scholarship",
        )
        _save_evidence(
            connection, 1,
            [("deadline_text", "April 1, 2027")],
            "https://example.org/scholarship",
        )

        rows = connection.execute(
            "SELECT field_name, evidence_text FROM scholarship_evidence ORDER BY id"
        ).fetchall()
        self.assertEqual(rows, [
            ("deadline_text", "April 1, 2026"),
            ("deadline_text", "April 1, 2027"),
        ])
        connection.close()


    def test_technical_eligibility_requirements_heading_is_extracted(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Community College Initiative Program</h1>
          <h2>Technical Eligibility Requirements</h2>
          <ul>
            <li>Applicants must be Pakistani citizens residing in Pakistan.</li>
            <li>Applicants must have English language proficiency.</li>
          </ul>
          <p>The programme was created to promote mutual understanding.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarships/ccip")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("Pakistani citizens", page.fields["eligibility"])
        self.assertEqual(len([x for x in page.criteria if x[0] == "eligibility"]), 2)

    def test_ineligibility_section_excludes_programme_history_and_selection_copy(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Fellowship Programme</h1>
          <h2>Ineligibility</h2>
          <ul>
            <li>Persons with dual U.S./Pakistan nationality.</li>
            <li>Employees of the sponsoring organization are also ineligible.</li>
            <li>The programme honours the memory of its founder.</li>
            <li>Fellows are selected through a competitive process.</li>
          </ul>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarships/fellowship")
        self.assertIsNotNone(page)
        assert page is not None
        exclusions = [x[2] for x in page.criteria if x[0] == "ineligibility"]
        self.assertEqual(len(exclusions), 2)
        self.assertTrue(any("dual U.S./Pakistan nationality" in x for x in exclusions))
        self.assertTrue(any("Employees of the sponsoring organization" in x for x in exclusions))
        self.assertFalse(any("honours the memory" in x for x in exclusions))
        self.assertFalse(any("selected through a competitive process" in x for x in exclusions))

    def test_mandatory_classifier_recognizes_plain_eligibility_requirements(self) -> None:
        self.assertTrue(_is_mandatory_criterion("eligibility", "Currently working as a journalist."))
        self.assertTrue(_is_mandatory_criterion("eligibility", "Three to ten years of active experience in journalism."))
        self.assertTrue(_is_mandatory_criterion("eligibility", "Proficient in written and spoken English."))
        self.assertFalse(_is_mandatory_criterion("eligibility", "Prior teaching experience is preferred."))


    def test_splits_ccap_exclusions_introduced_between_separate_lists(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Community College Administrator Program</h1>
          <h3>Technical Eligibility Requirements</h3>
          <p>Nominees must meet the following criteria:</p>
          <ul>
            <li>Has fluent or professional-level English language ability.</li>
            <li>Is a citizen, national, or permanent resident qualified to hold a valid Pakistan passport.</li>
            <li>Is currently residing in Pakistan.</li>
            <li>Is a full-time education administrator with at least five years of relevant experience.</li>
            <li>Be a Pakistani citizen (dual citizens are eligible EXCEPT for dual U.S.-Pakistan citizens).</li>
          </ul>
          <p>Individuals in the following circumstances are not eligible to be nominated:</p>
          <ul>
            <li>U.S. citizens and permanent residents of the United States;</li>
            <li>Individuals currently participating in academic, training, or research programs in the United States;</li>
            <li>Individuals who are married to a U.S. citizen;</li>
            <li>Individuals currently residing or working outside Pakistan;</li>
            <li>Employees of the Fulbright organization are ineligible;</li>
          </ul>
          <p>The Department reserves the right to verify application information.</p>
          <h3>Financial Provisions of the Grant</h3>
          <p>The programme provides funding for travel and living costs.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html, "https://example.org/scholarships/ccap"
        )
        self.assertIsNotNone(page)
        assert page is not None
        eligibility = [x[2] for x in page.criteria if x[0] == "eligibility"]
        exclusions = [x[2] for x in page.criteria if x[0] == "ineligibility"]
        self.assertTrue(any("fluent or professional-level English" in x for x in eligibility))
        self.assertTrue(any("currently residing in Pakistan" in x for x in eligibility))
        self.assertTrue(any("dual U.S.-Pakistan citizens" in x for x in exclusions))
        self.assertTrue(any("U.S. citizens and permanent residents" in x for x in exclusions))
        self.assertTrue(any("married to a U.S. citizen" in x for x in exclusions))
        self.assertTrue(any("residing or working outside Pakistan" in x for x in exclusions))
        self.assertTrue(any("Employees of the Fulbright organization" in x for x in exclusions))
        self.assertFalse(any("currently participating in academic" in x for x in eligibility))
        self.assertFalse(any("right to verify" in x for x in eligibility + exclusions))

    def test_splits_embedded_ccap_exclusions_from_technical_eligibility(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Community College Administrator Program</h1>
          <h2>Technical Eligibility Requirements</h2>
          <ul>
            <li>Applicants must be Pakistani citizens residing in Pakistan.</li>
            <li>Applicants must have fluent English language ability.</li>
            <li>Individuals in the following circumstances are not eligible to be nominated:</li>
            <li>U.S. citizens and permanent residents of the United States;</li>
            <li>Individuals who are married to a U.S. citizen;</li>
            <li>Employees of the sponsoring organization are ineligible;</li>
          </ul>
          <h3>Financial Provisions of the Grant</h3>
          <p>The programme provides funding for travel and living costs.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html, "https://example.org/scholarships/ccap"
        )
        self.assertIsNotNone(page)
        assert page is not None
        eligibility = [x[2] for x in page.criteria if x[0] == "eligibility"]
        exclusions = [x[2] for x in page.criteria if x[0] == "ineligibility"]
        self.assertTrue(any("Pakistani citizens residing in Pakistan" in x for x in eligibility))
        self.assertTrue(any("fluent English" in x for x in eligibility))
        self.assertEqual(len(exclusions), 3)
        self.assertTrue(any("U.S. citizens" in x for x in exclusions))
        self.assertTrue(any("married to a U.S. citizen" in x for x in exclusions))
        self.assertTrue(any("Employees of the sponsoring organization" in x for x in exclusions))

    def test_age_range_worded_with_should_is_mandatory(self) -> None:
        self.assertTrue(
            _is_mandatory_criterion(
                "eligibility",
                "Applicants should be between 18-24 years old by the deadline",
            )
        )


    def test_splits_explicit_exceptions_into_ineligibility(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Fulbright Scholar Programme</h1>
          <h2>Eligibility</h2>
          <p>Scholars and professionals from all disciplines are welcome to apply,
             with the exception of clinical medicine.</p>
          <p>Applicants must hold a Ph.D. or terminal degree.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html, "https://example.org/scholarships/fulbright-scholar"
        )
        self.assertIsNotNone(page)
        assert page is not None
        self.assertTrue(any(
            kind == "eligibility" and "all disciplines" in text
            for kind, _, text in page.criteria
        ))
        self.assertTrue(any(
            kind == "ineligibility" and "clinical medicine" in text
            for kind, _, text in page.criteria
        ))

    def test_ccip_faq_creates_separate_degree_and_post_selection_rules(self) -> None:
        html = """
        <html><body><main>
          <h1>Community College Initiative Program</h1>
          <p>The applicants must be resident in Pakistan, currently employed in one
          of the fields listed above, have 14-15 years of education (2-year Bachelors),
          English language proficiency, potential to have a positive impact on
          Pakistan's future development and demonstrated leadership.</p>
          <h2>Important Questions</h2>
          <p>For whom is this program intended?</p>
          <p>The program is designed for young professionals from Pakistan with
          2 year Bachelor's degree and less than 3 years of work experience.</p>
          <p>I have completed a three year Bachelors degree and I am working in
          one of the eligible fields, can I apply?</p>
          <p>Yes, you can apply if you are working in one of the specified fields.</p>
          <p>I have completed a four years Bachelors degree, can I apply?</p>
          <p>No, persons with a four years Bachelors degree are ineligible.</p>
          <p>I have completed my Masters degree, can I apply?</p>
          <p>No, persons with a Master's degree are ineligible.</p>
          <p>I am enrolled into a Master's program, can I apply?</p>
          <p>No, current students are ineligible.</p>
          <p>After selection, applicants must take the Institutional TOEFL (ITP).
          A minimum of 400 score (out of 677) is required to qualify.</p>
          <p>The programme provides tuition and living support.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html, "https://usefp.org/scholarships/ccip.cfm"
        )
        self.assertIsNotNone(page)
        assert page is not None
        eligibility = [x[2].casefold() for x in page.criteria if x[0] == "eligibility"]
        exclusions = [x[2].casefold() for x in page.criteria if x[0] == "ineligibility"]
        audience = [x for x in page.criteria if x[0] == "target_audience"]
        post_selection = [x for x in page.criteria if x[0] == "post_selection_requirement"]
        self.assertTrue(any("resident in pakistan" in x for x in eligibility))
        self.assertTrue(any("three-year bachelor's degree" in x for x in eligibility))
        self.assertEqual(len(audience), 1)
        self.assertIn("less than three years", audience[0][2].casefold())
        self.assertFalse(_is_mandatory_criterion(audience[0][0], audience[0][2]))
        self.assertEqual(len(post_selection), 1)
        self.assertIn("after selection", post_selection[0][2].casefold())
        self.assertTrue(_is_mandatory_criterion(post_selection[0][0], post_selection[0][2]))
        self.assertTrue(any("four-year bachelor's degree" in x for x in exclusions))
        self.assertTrue(any("master's degree" in x for x in exclusions))
        self.assertTrue(any("currently enrolled" in x for x in exclusions))
        self.assertFalse(any("less than 3 years" in x for x in exclusions))

    def test_ccap_filters_delivery_notes_and_completes_dual_citizenship_rule(self) -> None:
        html = """
        <html><body><main>
          <h1>Community College Administrator Program</h1>
          <h2>Technical Eligibility Requirements</h2>
          <ul>
            <li>Is a citizen, national, or permanent resident qualified to hold a valid passport issued by the government of Pakistan;</li>
            <li>Be a Pakistani citizen (dual citizens are eligible EXCEPT for dual U.S. - Pakistan citizens or those having a spouse, parent, fiance or child over 18 years of age who is a U.S. citizen or permanent resident)</li>
            <li>All program activities will be in English.</li>
            <li>No translation services will be provided on the program.</li>
          </ul>
          <p>Individuals in the following circumstances are not eligible:</p>
          <ul>
            <li>U.S. citizens and permanent residents of the United States;</li>
            <li>Individuals who are married to a U.S. citizen;</li>
          </ul>
          <p>The programme provides funding for travel and living costs.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html, "https://usefp.org/scholarships/ccap.cfm"
        )
        self.assertIsNotNone(page)
        assert page is not None
        criteria = [x[2].casefold() for x in page.criteria]
        self.assertTrue(any("dual citizenship is generally permitted" in x for x in criteria))
        self.assertTrue(any("dual u.s." in x and "spouse" in x for x in criteria))
        self.assertTrue(any("citizen, national, or permanent resident" in x for x in criteria))
        self.assertEqual(
            sum("be a pakistani citizen" in x for x in criteria),
            0,
            "The duplicate Pakistani-citizenship sentence should be consolidated.",
        )
        self.assertFalse(any("married to a u.s. citizen" in x for x in criteria))
        self.assertTrue(any("u.s. citizens and permanent residents" in x for x in criteria))
        self.assertFalse(any("all program activities" in x for x in criteria))
        self.assertFalse(any("no translation services" in x for x in criteria))


    def test_ccap_alternative_routes_are_combined_and_spacing_is_repaired(self) -> None:
        html = """
        <html><body><main>
          <h1>Community College Administrator Program</h1>
          <h2>Technical Eligibility Requirements</h2>
          <ul>
            <li>Is a citizen, national, or permanent residentsof Pakistan qualified to hold a valid passport.</li>
            <li>Is a full-time government official with at least 10 yearsof experience overseeing technical institutions.</li>
            <li>Is a full-time education administrator with at least 5 years of experience withintechnical institutions.</li>
          </ul>
          <p>Funding: The programme provides travel and living support.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html, "https://usefp.org/scholarships/ccap.cfm"
        )
        self.assertIsNotNone(page)
        assert page is not None
        eligibility = [x[2] for x in page.criteria if x[0] == "eligibility"]
        self.assertEqual(len(eligibility), 2)
        combined = next(x for x in eligibility if "qualify through either" in x)
        self.assertIn("10 years of experience", combined)
        self.assertIn("OR", combined)
        self.assertIn("5 years of experience", combined)
        self.assertFalse(any("10 yearsof" in x for x in eligibility))
        self.assertFalse(any("withintechnical" in x for x in eligibility))
        self.assertTrue(any("permanent residents of Pakistan" in x for x in eligibility))

if __name__ == "__main__":
    unittest.main()
