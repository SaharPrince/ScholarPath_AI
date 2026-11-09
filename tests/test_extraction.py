import sqlite3
import unittest

from app.extraction import (
    _clean, _classify_application_status, _classify_applicant_category,
    _parse_deadline_date, _find_application_url, _is_mandatory_criterion, _extract_description_criteria, _split_criteria_statements, parse_scholarship_page, _save_evidence, _parse_hec_knowledge_corridor, _remove_site_chrome,
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
            "academic,training, or research programs "
            "be afull-time education administrator; permanent residency inthe past three years; "
            "U.S. Departmentof State; i.e.spouses"
        )
        self.assertEqual(
            cleaned,
            "permanent resident eligible fields on behalf of residents of Pakistan "
            "14–15 years of education four-year bachelor After selection "
            "Institutional TOEFL Applicants must apply "
            "one of the listed eligible fields subject to the rule "
            "at least 5 years of experience in the United States OR (2) route "
            "three-year degree holders may apply; permanent residency; Department of State employees; "
            "academic, training, or research programs "
            "be a full-time education administrator; permanent residency in the past three years; "
            "U.S. Department of State; i.e. spouses",
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

    def test_nested_site_chrome_is_removed_without_mutating_during_traversal(self) -> None:
        html = """
        <html><body>
          <div role="navigation">
            <div id="nested-navigation" class="menu-item">
              <a href="/scholarships">Scholarships</a>
            </div>
          </div>
          <main>
            <h1>Example Fellowship Programme</h1>
            <p>Application deadline: 15 March 2027</p>
            <p>Eligibility: Applicants must be Pakistani citizens with a completed bachelor's degree.</p>
            <p>Funding: Full tuition and a monthly stipend.</p>
          </main>
        </body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/fellowship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.title, "Example Fellowship Programme")
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


    def test_age_limits_are_mandatory_even_when_source_uses_case_of_wording(self) -> None:
        self.assertTrue(
            _is_mandatory_criterion(
                "age_limit",
                "40 Years in case of regular Government Employees.",
            )
        )
        self.assertTrue(
            _is_mandatory_criterion(
                "age_limit",
                "35 Years in case of all other applicants.",
            )
        )

    def test_provider_extraction_stops_before_descriptive_clause(self) -> None:
        from bs4 import BeautifulSoup
        from app.extraction import _find_provider_statement

        html = """
        <html><body><main>
          <p>The scholarships are offered by the Commonwealth Scholarship
          Commission (CSC) in the UK and are intended to support talented
          candidates from eligible Commonwealth countries.</p>
        </main></body></html>
        """
        provider = _find_provider_statement(
            _remove_site_chrome(BeautifulSoup(html, "html.parser"))
        )
        self.assertEqual(provider, "Commonwealth Scholarship Commission (CSC)")


class HecKnowledgeCorridorExtractionTests(unittest.TestCase):
    def test_sharepoint_rich_content_is_selected_over_site_chrome(self) -> None:
        html = """
        <html><body>
          <div class="page-body">
            <nav>Scholarships navigation must not be extracted</nav>
            <div class="ms-rtestate-field">
              <p>Official programme eligibility content</p>
            </div>
          </div>
        </body></html>
        """
        root = _remove_site_chrome(__import__("bs4").BeautifulSoup(html, "html.parser"))
        self.assertEqual(root.get_text(" ", strip=True), "Official programme eligibility content")

    def test_aggregates_hec_pages_with_exact_source_provenance(self) -> None:
        base = "https://www.hec.gov.pk/english/scholarshipsgrants/US-Pakcorridor/Pages/"
        pages = {
            "overview": ("""
                <html><body><div class="ms-rtestate-field">
                  <h1>US-Pakistan Knowledge Corridor PhD Scholarship</h1>
                  <p>The US-Pakistan Knowledge Corridor provides PhD scholarships
                     for Pakistani students to study in the United States.</p>
                </div></body></html>
            """, base + "default.aspx"),
            "eligibility": ("""
                <html><body><div class="ms-rtestate-field">
                  <p>Applicants must be Pakistani/AJK nationals.</p>
                  <p>Minimum four-year bachelor's degree or 16 years of formal education.</p>
                  <p>Maximum one second division throughout academic career.</p>
                  <p>Maximum age is 40 years for regular government employees and
                     eligible public-sector faculty/researchers, and 35 years for all other applicants.</p>
                  <p>Applicants must not be availing another scholarship.</p>
                  <p>Existing PhD degree holders are not eligible.</p>
                  <p>Category I: admission to a top 50 QS-ranked US university.</p>
                  <p>GRE General score of at least 300 OR HAT score of at least 60%.</p>
                  <p>Category II: admission to a QS-ranked US university ranked 51-100.</p>
                </div></body></html>
            """, base + "Eligibility-Criteria.aspx"),
            "how_to_apply": ("""
                <html><body><div class="ms-rtestate-field">
                  <p>Apply through the official online application portal.</p>
                  <a href="https://scholarship.hec.gov.pk/">Scholarship portal</a>
                </div></body></html>
            """, base + "How-to-Apply.aspx"),
            "faq": ("""
                <html><body><div class="ms-rtestate-field">
                  <p>IELTS and TOEFL are not required by this project.</p>
                  <p>Only a J-1 visa is acceptable.</p>
                  <p>Tuition Cost Fully Funded</p>
                  <p>Annual Tuition Cost Up to USD 12,000/-</p>
                  <p>Annual stipend: USD 19,200.</p>
                  <p>Annual health insurance: USD 2,000 or actual, whichever is lower.</p>
                  <p>Return airfare: PKR 250,000.</p>
                </div></body></html>
            """, base + "FAQ.aspx"),
            "priority_subjects": ("""
                <html><body><div class="ms-rtestate-field">
                  <p>Priority subject areas include life sciences, natural sciences,
                     engineering and technology, social sciences and management,
                     and creative art and design.</p>
                </div></body></html>
            """, base + "Priority-Subject-Areas.aspx"),
        }

        page = _parse_hec_knowledge_corridor(pages)
        self.assertIsNotNone(page)
        assert page is not None

        self.assertEqual(page.title, "US-Pakistan Knowledge Corridor PhD Scholarship")
        self.assertEqual(page.application_status, "unknown")
        self.assertEqual(page.fields["application_url"], "https://scholarship.hec.gov.pk/")
        funding = page.fields["funding_summary"]
        self.assertIn("Category I (QS 1–50)", funding)
        self.assertIn("Category II (QS 51–100)", funding)
        self.assertIn("fully funded", funding.casefold())
        self.assertIn("up to usd 12,000", funding.casefold())
        self.assertIn("Benefits stated without a category restriction", funding)
        category_i_section = funding.split("Category I (QS 1–50):", 1)[1].split(
            "Category II (QS 51–100):", 1
        )[0]
        category_ii_section = funding.split("Category II (QS 51–100):", 1)[1].split(
            "Benefits stated without a category restriction:", 1
        )[0]
        self.assertIn("fully funded", category_i_section.casefold())
        self.assertNotIn("up to usd 12,000", category_i_section.casefold())
        self.assertIn("up to usd 12,000", category_ii_section.casefold())
        self.assertNotIn("fully funded", category_ii_section.casefold())
        self.assertIn("USD 19,200", page.fields["funding_summary"])
        self.assertIn("PKR 250,000", page.fields["funding_summary"])

        criteria = [item[2].casefold() for item in page.criteria]
        self.assertTrue(any("pakistani/ajk nationals" in item for item in criteria))
        self.assertTrue(any("four-year bachelor's" in item for item in criteria))
        self.assertTrue(any("one second division" in item for item in criteria))
        self.assertTrue(any("40 years" in item for item in criteria))
        self.assertTrue(any("35 years" in item for item in criteria))
        age_criteria = [item for item in page.criteria if item[0] == "age_limit"]
        self.assertTrue(any("specified public-sector" in label for _kind, label, _text in age_criteria))
        self.assertTrue(any("all other applicants" in label for _kind, label, _text in age_criteria))
        self.assertTrue(all(_is_mandatory_criterion(kind, text) for kind, _label, text in age_criteria))
        self.assertTrue(any("top 50" in item for item in criteria))
        self.assertTrue(any("51-100" in item for item in criteria))
        self.assertTrue(any(
            kind == "category_i_eligibility" and "top 50" in requirement.casefold()
            for kind, _label, requirement in page.criteria
        ))
        self.assertTrue(any(
            kind == "category_ii_eligibility" and "51-100" in requirement.casefold()
            for kind, _label, requirement in page.criteria
        ))
        self.assertTrue(_is_mandatory_criterion("category_i_eligibility", "Category I admission requirement"))
        self.assertTrue(_is_mandatory_criterion("category_ii_eligibility", "Category II admission requirement"))
        self.assertTrue(any("not be availing another scholarship" in item for item in criteria))
        self.assertTrue(any("phd degree holders" in item for item in criteria))
        self.assertTrue(any("not required" in item and "ielts" in item for item in criteria))
        self.assertTrue(any("j-1" in item for item in criteria))

        eligibility_url = base + "Eligibility-Criteria.aspx"
        faq_url = base + "FAQ.aspx"
        how_to_url = base + "How-to-Apply.aspx"
        self.assertEqual(
            page.criteria_sources[(
                "age_limit", "Maximum age – specified public-sector applicants",
                next(item[2] for item in page.criteria if item[0] == "age_limit" and "40 years" in item[2])
            )],
            eligibility_url,
        )
        funding_evidence_urls = {
            source_url
            for (field_name, _evidence_text), source_url in page.evidence_sources.items()
            if field_name == "funding_summary"
        }
        self.assertEqual(funding_evidence_urls, {faq_url})
        self.assertEqual(
            page.evidence_sources[("application_url", "https://scholarship.hec.gov.pk/")],
            how_to_url,
        )

    def test_nationality_plural_and_duplicate_criteria_are_normalized(self) -> None:
        base = "https://www.hec.gov.pk/english/scholarshipsgrants/US-Pakcorridor/Pages/"
        pages = {
            "overview": ("""
                <html><body><div class="ms-rtestate-field">
                  <h1>US-Pakistan Knowledge Corridor PhD Scholarship</h1>
                  <p>The US-Pakistan Knowledge Corridor provides PhD scholarships.</p>
                </div></body></html>
            """, base + "default.aspx"),
            "eligibility": ("""
                <html><body><div class="ms-rtestate-field">
                  <p>Applicants must be Pakistani/AJK nationals.</p>
                  <p>Valid GRE – General Score (Minimum 300 in total) OR HAT Score (Minimum 60% Score)</p>
                  <p>b. Valid GRE – General Score (Minimum 300 in total) OR HAT Score (Minimum 60% Score). ​</p>
                  <p>Category I – Scholarship (Top 50 QS World Ranked US Universities):</p>
                  <p>Secured admission in top 50 QS World Ranked US University.</p>
                </div></body></html>
            """, base + "Eligibility-Criteria.aspx"),
        }
        page = _parse_hec_knowledge_corridor(pages)
        self.assertIsNotNone(page)
        assert page is not None
        nationality = [item for item in page.criteria if item[0] == "nationality"]
        gre_hat = [item for item in page.criteria if item[1] == "GRE or HAT score"]
        category_i = [item for item in page.criteria if item[0] == "category_i_eligibility"]
        self.assertEqual(len(nationality), 1)
        self.assertEqual(len(gre_hat), 1)
        self.assertEqual(len(category_i), 1)
        self.assertIn("Secured admission", category_i[0][2])

    def test_corridor_repairs_spacing_and_deduplicates_priority_list_items(self) -> None:
        from bs4 import BeautifulSoup
        from app.extraction import _clean, _hec_priority_subject_items

        self.assertEqual(
            _clean("AnnualStipend USD19,200 FullyFunded 1000Ph.D. DairyScience"),
            "Annual Stipend USD 19,200 Fully Funded 1000 Ph.D. Dairy Science",
        )
        self.assertEqual(_clean("United Statesunder the programme commencing October2027"),
                         "United States under the programme commencing October 2027")
        root = BeautifulSoup("""
            <div>
              <ul>
                <li>Crop Production and Soil Sciences</li>
                <li>Computational Biology and Bioinformatics</li>
                <li>Crop Production and Soil Sciences</li>
              </ul>
              <p>Crop Production and Soil Sciences</p>
            </div>
        """, "html.parser")
        self.assertEqual(
            _hec_priority_subject_items(root),
            ["Crop Production and Soil Sciences", "Computational Biology and Bioinformatics"],
        )

    def test_corridor_captures_numbered_division_faq_clarification(self) -> None:
        base = "https://www.hec.gov.pk/english/scholarshipsgrants/US-Pakcorridor/Pages/"
        pages = {
            "overview": ("""
                <div class="ms-rtestate-field">
                  <h1>US-Pakistan Knowledge Corridor PhD Scholarship</h1>
                  <p>The US-Pakistan Knowledge Corridor provides PhD scholarships
                     for Pakistani students to study in the United States.</p>
                </div>
            """, base + "default.aspx"),
            "eligibility": ("""
                <div class="ms-rtestate-field">
                  <p>Pakistani/AJK nationals</p>
                  <p>Maximum one second division throughout academic career.</p>
                </div>
            """, base + "Eligibility-Criteria.aspx"),
            "faq": ("""
                <div class="ms-rtestate-field">
                  <p>Applicants must have no 2nd and 3rd division throughout their entire academic career.</p>
                </div>
            """, base + "FAQ.aspx"),
        }
        page = _parse_hec_knowledge_corridor(pages)
        self.assertIsNotNone(page)
        assert page is not None
        faq_rules = [
            item for item in page.criteria
            if item[1] == "Academic record – FAQ clarification"
        ]
        self.assertEqual(len(faq_rules), 1)
        self.assertIn("2nd and 3rd division", faq_rules[0][2])
        self.assertEqual(
            page.criteria_sources[faq_rules[0]],
            base + "FAQ.aspx",
        )

    def test_corridor_summary_uses_source_evidence_and_faq_score_applies_to_all(self) -> None:
        base = "https://www.hec.gov.pk/english/scholarshipsgrants/US-Pakcorridor/Pages/"
        overview_statement = (
            "Phase – 1 envisions to award 1000 Ph.D. scholarships to outstanding "
            "Pakistani students in US Universities under the project."
        )
        pages = {
            "overview": (f"""
                <div class="ms-rtestate-field">
                  <h1>US-Pakistan Knowledge Corridor PhD Scholarship</h1>
                  <p>{overview_statement}</p>
                </div>
            """, base + "default.aspx"),
            "eligibility": ("""
                <div class="ms-rtestate-field">
                  <p>Pakistani/AJK nationals</p>
                  <p>GRE General score of at least 300 OR HAT score of at least 60%.</p>
                </div>
            """, base + "Eligibility-Criteria.aspx"),
            "faq": ("""
                <div class="ms-rtestate-field">
                  <p>GRE score 300 and above/HEC-HAT score 60% and above.
                     All candidates are required to fulfill this scholarship eligibility criterion
                     regardless of admission in a U.S. university.</p>
                </div>
            """, base + "FAQ.aspx"),
        }
        page = _parse_hec_knowledge_corridor(pages)
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("PhD scholarships for outstanding Pakistani students", page.description or "")
        self.assertEqual(
            page.evidence_sources[("description", overview_statement)],
            base + "default.aspx",
        )
        shared_score_rules = [
            (kind, label, value) for kind, label, value in page.criteria
            if kind == "academic_requirements" and "GRE or HAT score" in label
        ]
        self.assertEqual(len(shared_score_rules), 1)
        self.assertEqual(shared_score_rules[0][1], "GRE or HAT score – all applicants")
        self.assertFalse(any(
            kind == "required_documents" and "GRE" in value
            for kind, _label, value in page.criteria
        ))

    def test_hec_aggregation_requires_overview_and_eligibility_pages(self) -> None:
        self.assertIsNone(_parse_hec_knowledge_corridor({
            "overview": ("<html><body><p>Programme</p></body></html>", "https://example.org/")
        }))



class HecCommonwealthAnnouncementTests(unittest.TestCase):
    def test_extracts_commonwealth_2027_28_requirements_deadline_and_both_portals(self) -> None:
        from app.extraction import _parse_hec_commonwealth_announcement, _is_mandatory_criterion

        url = "https://www.hec.gov.pk/english/HECAnnouncements/Pages/CW-Scholarship.aspx"
        html = """
        <html><body><div class="ms-rtestate-field">
          <h1>Commonwealth Scholarship Programme (Master's &amp; PhD) for Academic Year 2027-28</h1>
          <p>The Higher Education Commission (HEC) Pakistan, as the national nominating agency
          for Pakistan, invites applications from eligible Pakistani/AJ&amp;K nationals.
          The scholarships are offered by the Commonwealth Scholarship Commission (CSC).</p>
          <p>The scholarships are for full-time taught Master's and PhD study at a UK university.</p>
          <h2>Key Dates</h2>
          <ul>
            <li>Closing date for CSC applications: Tuesday, 20 October 2026 at 16:00 BST</li>
            <li>HEC application deadline: 20 October 2026 at 4:00 PM (PST)</li>
          </ul>
          <h2>HEC Eligibility Criteria</h2>
          <ul>
            <li>Be a Pakistani/AJ&amp;K national and permanent resident of Pakistan/AJ&amp;K. Dual nationals are not eligible.</li>
            <li>There is no upper age limit for this scholarship.</li>
            <li>For Master scholarship, an applicant must hold a first division in 16 years Bachelors degree in the relevant field of study.</li>
            <li>For PhD scholarship, an applicant must hold a first division in 17/18 years Masters/MS/MPhil degree in the relevant field of study.</li>
            <li>Not have a Second/Third Division in the terminal (latest) degree.</li>
            <li>Result-awaiting candidates may apply, provided they obtain and submit their final degree and transcript before commencement.</li>
            <li>All applicants are required to provide HAT test score. Applicant must have obtained a minimum score of 60 out of 100 in HAT test.</li>
            <li>Only HAT categories (HAT-I, II, III and IV) are acceptable for the scholarship nomination.</li>
            <li>Merit shall be determined strictly on the basis of HAT score.</li>
            <li>In case two or more applicants have the same test score, merit will be determined based on the percentage obtained in the applicant's last completed degree program.</li>
          </ul>
          <p>HEC will undertake the nomination process in Pakistan, while the final selection will be made by the Commonwealth Scholarship Commission.</p>
          <p>Applicants are required to submit online applications at the Commonwealth and HEC portals.</p>
          <a href="https://cscuk.fcdo.gov.uk/scholarships/commonwealth-masters-scholarships/">Master's application</a>
          <a href="https://cscuk.fcdo.gov.uk/scholarships/commonwealth-phd-scholarships-for-least-developed-countries-and-vulnerable-states/">PhD application</a>
          <a href="https://scholarship.hec.gov.pk/">HEC application portal</a>
        </div></body></html>
        """
        page = _parse_hec_commonwealth_announcement(html, url)
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.provider_name, "Commonwealth Scholarship Commission (CSC)")
        self.assertEqual(page.fields["study_destination"], "United Kingdom")
        self.assertEqual(page.fields["study_level"], "Master's and PhD")
        self.assertEqual(page.fields["deadline_text"], "Closing date for CSC applications: Tuesday, 20 October 2026 at 16:00 BST")
        self.assertEqual(page.fields["deadline_date"], "2026-10-20")
        self.assertEqual(page.fields["application_status"], "closed")
        self.assertEqual(page.application_status, "closed")
        self.assertEqual(page.fields["application_url"], "https://scholarship.hec.gov.pk/")
        criteria = [text.casefold() for _kind, _label, text in page.criteria]
        self.assertTrue(any("pakistani/aj&k" in text and "dual nationals" in text for text in criteria))
        self.assertFalse(any("national nominating agency" in text for text in criteria))
        self.assertFalse(any("development themes" in text for text in criteria))
        self.assertTrue(any("no upper age limit" in text for text in criteria))
        self.assertTrue(any("16 years" in text and "first division" in text for text in criteria))
        self.assertTrue(any("17/18 years" in text and "first division" in text for text in criteria))
        self.assertTrue(any("second/third division" in text for text in criteria))
        self.assertTrue(any("result-awaiting" in text for text in criteria))
        self.assertTrue(any("60 out of 100" in text for text in criteria))
        self.assertTrue(any("hat-i" in text for text in criteria))
        self.assertTrue(any("nomination process" in text for text in criteria))
        dual_portal = [
            (kind, label, value) for kind, label, value in page.criteria
            if label == "Dual-portal application"
        ]
        self.assertEqual(len(dual_portal), 1)
        self.assertTrue(_is_mandatory_criterion(dual_portal[0][0], dual_portal[0][2]))
        final_authority = [
            item for item in page.criteria if item[1] == "Final selection authority"
        ]
        self.assertEqual(len(final_authority), 1)
        self.assertIn("nomination process", final_authority[0][2].casefold())
        self.assertIn("final selection", final_authority[0][2].casefold())
        self.assertFalse(any(item[1] == "National nomination authority" for item in page.criteria))
        self.assertFalse(any(
            _is_mandatory_criterion(kind, value)
            for kind, _label, value in page.criteria
            if kind in {"selection_process", "selection_criteria"}
        ))
        self.assertFalse(any(
            "national nominating agency" in value.casefold()
            for _kind, _label, value in page.criteria
        ))
        self.assertEqual(
            page.description,
            "The scholarships are for full-time taught Master's and PhD study at a UK university.",
        )
        portal_evidence = [value for name, value in page.evidence if name == "application_portal"]
        self.assertEqual(len(portal_evidence), 3)
        self.assertTrue(any("commonwealth-masters-scholarships" in value for value in portal_evidence))
        self.assertTrue(any("commonwealth-phd-scholarships" in value for value in portal_evidence))
        self.assertTrue(any("scholarship.hec.gov.pk" in value for value in portal_evidence))
        self.assertTrue(all(source == url for source in page.evidence_sources.values()))
        self.assertTrue(all(source == url for source in page.criteria_sources.values()))

    def test_hec_sharepoint_repairs_observed_joined_words_without_rewriting_other_spelling(self) -> None:
        self.assertEqual(
            _clean("Benefits stated withouta category restriction; applicationto cancer research"),
            "Benefits stated without a category restriction; application to cancer research",
        )
        # Preserve source spelling rather than silently correcting factual evidence.
        self.assertIn("Pharmacetuical", _clean("Pharmacetuical Sciences"))

    def test_rejects_unrelated_or_wrong_cycle_hec_page(self) -> None:
        from app.extraction import _parse_hec_commonwealth_announcement

        self.assertIsNone(_parse_hec_commonwealth_announcement(
            "<html><body><p>General HEC scholarship information.</p></body></html>"
        ))


if __name__ == "__main__":
    unittest.main()
