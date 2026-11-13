from app.extraction import (
    ExtractedPage,
    VILLIGST_DOCTORAL_FAQ_URL,
    FES_APPRENTICESHIP_FAQ_URL,
    HEINRICH_BOLL_FAQ_URL,
    HEINRICH_BOLL_APPLICATION_URL,
    _augment_heinrich_boll_faq,
    OSKAR_KARL_FORSTER_URL,
    ROMANA_SCHOTT_URL,
    _augment_oskar_karl_forster,
    _augment_romana_schott,
    _augment_villigst_doctoral_faq,
    _augment_fes_apprenticeship_faq,
    TU_BERLIN_DEUTSCHLANDSTIPENDIUM_URL,
    _augment_tu_berlin_deutschlandstipendium,
    KIEL_DEUTSCHLANDSTIPENDIUM_URL,
    _augment_kiel_deutschlandstipendium,
    HAW_KIEL_DEUTSCHLANDSTIPENDIUM_URL,
    _augment_haw_kiel_deutschlandstipendium,
    FU_BERLIN_DEUTSCHLANDSTIPENDIUM_URL,
    _augment_fu_berlin_deutschlandstipendium,
    KLU_DEUTSCHLANDSTIPENDIUM_URL,
    _augment_klu_deutschlandstipendium,
)
import sqlite3
import unittest

from app.extraction import (
    _clean, _classify_application_status, _classify_applicant_category, _classify_eligibility_statement,
    _parse_deadline_date, _find_application_url, _is_mandatory_criterion, _extract_description_criteria, _split_criteria_statements, extract_criteria_from_html, parse_scholarship_page, _save_evidence, _parse_hec_knowledge_corridor, _remove_site_chrome,
)


class ScholarshipPageExtractionTests(unittest.TestCase):
    def test_heinrich_boll_faq_adds_shared_and_route_specific_requirements_with_provenance(self):
        parsed = ExtractedPage(
            title="Heinrich Böll Scholarship for International Graduates and PhD Students",
            description=None,
            provider_name="Heinrich Böll Foundation",
        )
        faq = """
        <html><body><main>
          <p>International students or Bildungsausländer from EU and non-EU countries can apply if they already have a first professional degree such as a Bachelor's degree.</p>
          <p>International PhD candidates may apply after completing their graduate degree abroad, with a research topic, exposé, supervisor and initial preparatory work.</p>
          <p>Good German language skills (DSH II or B2) are required, even for English-taught programmes.</p>
          <p>We do not set any age limits for applicants.</p>
          <p>Priority will be given to international students and PhD candidates from DAC countries.</p>
          <p>We expect very good academic performance and civic engagement.</p>
          <p>Part-time degree programs are not eligible for funding.</p>
          <p>Any BAföG payments or funding from another institution must be discontinued prior to the start of the scholarship.</p>
          <p>We expect application documents in German. PhD candidates must write the abstract of their exposé in German.</p>
          <p>Only applications submitted via our online portal are accepted.</p>
        </main></body></html>
        """
        application = """
        <html><body><main>
          <p>Students of all disciplines may apply to study full-time at a state-recognized university.</p>
          <p>We only fund Master's programmes with a standard duration of four semesters or more.</p>
        </main></body></html>
        """
        result = _augment_heinrich_boll_faq(parsed, faq, application)
        self.assertIs(result, parsed)
        self.assertTrue(any(item[0] == "language_requirements" and "B2 or DSH II" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "age_limit" and "no age limit" in item[2].lower() for item in result.criteria))
        self.assertTrue(any(item[0] == "study_level" and "part-time" in item[2] for item in result.criteria))
        self.assertTrue(any("first degree" in item[2] for item in result.criteria))
        self.assertTrue(any("PhD applicants" in item[2] for item in result.criteria))
        self.assertTrue(any("at least four semesters" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "selection_criteria" and "DAC countries" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "selection_criteria" and "no fixed minimum" in item[2] for item in result.criteria))
        self.assertTrue(any("online application portal" in item[2] for item in result.criteria))
        self.assertTrue(any("discontinued before this scholarship begins" in item[2] for item in result.criteria))
        self.assertTrue(any("exposé abstract in German" in item[2] for item in result.criteria))
        for item in result.criteria:
            self.assertIn(result.criteria_sources[item], {HEINRICH_BOLL_FAQ_URL, HEINRICH_BOLL_APPLICATION_URL})
        self.assertTrue(all(not _is_mandatory_criterion(kind, text) for kind, _label, text in result.criteria if kind == "selection_criteria"))

    def test_oskar_karl_forster_augmentation_preserves_master_semester_exception_and_other_information(self):
        parsed = ExtractedPage("Oskar Karl Forster Scholarship", None, "University of Würzburg")
        html = """
        <html><body><main>
          <p>Enrolled gifted and needy students from the second semester onwards.</p>
          <p>The restrictive requirement of 2nd semester does not apply to students in Master's degree programmes.</p>
          <p>Enrolment at the University of Würzburg must be proven by presenting a current certificate of enrolment.</p>
          <p>Particularly outstanding academic achievements are NOT a prerequisite here.</p>
          <p>In principle, approximately 20 ECTS points per semester indicate continued successful study progress.</p>
          <p>The grant can only be claimed once.</p>
          <p>Foreign documents can only be utilised in officially certified translations or in English-language copies.</p>
        </main></body></html>
        """
        result = _augment_oskar_karl_forster(parsed, html)
        self.assertTrue(any("second semester onwards" in item[2] and "Master's students" in item[2] for item in result.criteria))
        self.assertTrue(any("University of Würzburg" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "eligibility" and "financial need" in item[2].lower() for item in result.criteria))
        academic = next(item for item in result.criteria if item[1] == "Academic performance clarification")
        self.assertEqual(academic[0], "selection_criteria")
        self.assertFalse(_is_mandatory_criterion(academic[0], academic[2]))
        self.assertTrue(any("only once" in item[2] for item in result.criteria))
        self.assertTrue(any("certified translations" in item[2] for item in result.criteria))
        for item in result.criteria:
            self.assertEqual(result.criteria_sources[item], OSKAR_KARL_FORSTER_URL)


    def test_tu_berlin_deutschlandstipendium_keeps_current_and_prospective_routes_separate(self):
        parsed = ExtractedPage("TU Berlin Deutschlandstipendium", None, "TU Berlin")
        html = """
        <html><body><main>
          <p>Regularly enrolled bachelor's and master's students who are already enrolled at TU Berlin at the beginning of the funding period and who are still studying within the standard period of study with at least two semesters remaining.</p>
          <p>New students who have applied and will commence their studies at TU Berlin in the winter semester.</p>
          <p>Students pursuing a second degree or complementary studies are also eligible.</p>
          <p>Doctoral candidates, however, are not eligible to apply for the Deutschlandstipendium.</p>
          <p>International students and applicants of TU Berlin can apply.</p>
        </main></body></html>
        """
        result = _augment_tu_berlin_deutschlandstipendium(parsed, html)
        current = next(item for item in result.criteria if item[0] == "category_i_eligibility")
        prospective = next(item for item in result.criteria if item[0] == "category_ii_eligibility")
        doctoral = next(item for item in result.criteria if item[0] == "ineligibility")
        self.assertIn("at least two semesters remaining", current[2])
        self.assertIn("have applied", prospective[2])
        self.assertIn("Doctoral candidates", doctoral[2])
        self.assertTrue(any(item[0] == "target_audience" and "second degree" in item[2] for item in result.criteria))
        self.assertTrue(all(result.criteria_sources[item] == TU_BERLIN_DEUTSCHLANDSTIPENDIUM_URL for item in result.criteria))
        self.assertTrue(all(result.evidence_sources[("eligibility", item[2])] == TU_BERLIN_DEUTSCHLANDSTIPENDIUM_URL for item in result.criteria))

    def test_tu_berlin_augmentation_does_not_infer_routes_without_official_phrases(self):
        parsed = ExtractedPage("Unrelated scholarship", None, "Example")
        result = _augment_tu_berlin_deutschlandstipendium(
            parsed, "<html><body><main><p>Students may apply.</p></main></body></html>"
        )
        self.assertEqual(result.criteria, [])

    def test_romana_schott_augmentation_records_nomination_process_without_personal_data(self):
        parsed = ExtractedPage("Romana Schott Scholarships", None, "University of Würzburg")
        html = """
        <html><body><main>
          <p>Scholarships are awarded to needy female students of all faculties.</p>
          <p>It is not possible to apply for a scholarship on one's own.</p>
          <p>Consultation between the student and a UFB staff member is obligatory.</p>
          <p>The application deadline is March 31 and September 30 of each year.</p>
          <p>The justification for the proposal must comment on suitability.</p>
          <p>The proposal form must be completed by the student.</p>
          <p>No benefits will be granted if you are not in need. No benefits will be paid for semesters of leave either.</p>
        </main></body></html>
        """
        result = _augment_romana_schott(parsed, html)
        self.assertTrue(any("female students" in item[2] and "financial-need" in item[2] for item in result.criteria))
        self.assertTrue(any("cannot apply independently" in item[2] for item in result.criteria))
        self.assertTrue(any("31 March and 30 September" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "required_documents" and "expert justification" in item[2] for item in result.criteria))
        self.assertTrue(any("semesters of leave" in item[2] for item in result.criteria))
        self.assertTrue(all(result.criteria_sources[item] == ROMANA_SCHOTT_URL for item in result.criteria))

    def test_klu_deutschlandstipendium_keeps_admitted_route_and_selection_factors_distinct(self):
        parsed = ExtractedPage("KLU Deutschlandstipendium", None, "Kühne Logistics University")
        html = """
        <html><body><main>
          <p>Fulfill the admission criteria for studies at KLU.</p>
          <p>Are already enrolled in a degree program at KLU or have been admitted to KLU and are going to start soon.</p>
          <p>The scholarship program provides 300 euros monthly for 12 months.</p>
          <p>The application period will start on March 27 - May 31, 2026.</p>
          <p>The scholarship period will be Sept. 2026 - Aug. 2027 (12 months).</p>
          <p>Study starters and current KLU students will be evaluated separately.</p>
          <p>Only students with very good grades have a chance to receive this scholarship.</p>
          <p>Furthermore, special achievements, awards, and prizes, previous work experience and internships, voluntary work or societal, social, and political engagement, and special personal or familial circumstances will also be recognized.</p>
          <p>Following the call for application sent out by the Dean of Programs, the application portal will be open for the mentioned application period.</p>
        </main></body></html>
        """
        result = _augment_klu_deutschlandstipendium(parsed, html)
        eligibility = next(item for item in result.criteria if item[1] == "KLU admission and study status")
        self.assertEqual(eligibility[0], "eligibility")
        self.assertIn("admitted and plan to start soon", eligibility[2])
        academic = next(item for item in result.criteria if item[1] == "Academic performance")
        self.assertEqual(academic[0], "selection_criteria")
        self.assertIn("fixed minimum eligibility threshold", academic[2])
        additional = next(item for item in result.criteria if item[1] == "Additional selection factors")
        self.assertEqual(additional[0], "selection_criteria")
        self.assertFalse(_is_mandatory_criterion(academic[0], academic[2]))
        self.assertFalse(_is_mandatory_criterion(additional[0], additional[2]))
        self.assertEqual(result.fields["funding_summary"], "€300 per month for 12 months.")
        self.assertIn("has closed", result.fields["deadline_text"])
        self.assertTrue(any(item[1] == "2026–2027 funding period" for item in result.criteria))
        self.assertTrue(any(item[1] == "Application process" for item in result.criteria))
        self.assertTrue(all(result.criteria_sources[item] == KLU_DEUTSCHLANDSTIPENDIUM_URL for item in result.criteria))
        self.assertTrue(all(result.evidence_sources[item] == KLU_DEUTSCHLANDSTIPENDIUM_URL for item in result.evidence))

    def test_fes_social_democratic_values_are_other_information(self):
        statement = "Wir suchen Auszubildende, die die Werte der Sozialen Demokratie teilen."
        kind, label = _classify_eligibility_statement(statement)
        self.assertEqual(kind, "selection_criteria")
        self.assertEqual(label, "Programme fit and selection expectations")
        self.assertFalse(_is_mandatory_criterion(kind, statement))

    def test_fes_apprenticeship_faq_augments_same_award_with_evidence(self):
        parsed = ExtractedPage(
            title="FES Scholarship for Apprentices",
            description=None,
            provider_name="Friedrich Ebert Foundation",
        )
        html = """
        <html><body><main>
          <p>Der Ausbildungsgang muss mit einer staatlich anerkannten Prüfung abschließen.</p>
          <p>Zu Beginn der Ausbildung darf die Bewerberin oder der Bewerber das 45. Lebensjahr noch nicht vollendet haben.</p>
          <p>§8 BAföG lists eligible person groups.</p>
          <p>Die Stipendien für Auszubildende sind nicht auf die Erstausbildung beschränkt.</p>
          <p>Teilzeitberufsausbildungen sind möglich, wenn sie den Vorgaben des BBiG entsprechen.</p>
          <p>Nein, Sie müssen sich nicht in der SPD engagieren oder Mitglied sein.</p>
          <p>Derzeit ist keine Bewerbung möglich. Für die Auswahlrunde 2026 wird das Bewerbungsportal voraussichtlich vom 16. März bis 17. Mai geöffnet.</p>
        </main></body></html>
        """
        result = _augment_fes_apprenticeship_faq(parsed, html)
        self.assertIs(result, parsed)
        self.assertEqual(result.fields["deadline_date"], "2026-05-17")
        self.assertEqual(result.application_status, "closed")
        self.assertTrue(any("state-recognized examination" in item[2] for item in result.criteria))
        self.assertTrue(any("under 45" in item[2] or "45 years" in item[2] for item in result.criteria))
        self.assertTrue(any("not limited to a first vocational qualification" in item[2] for item in result.criteria))
        self.assertTrue(any("Part-time vocational training" in item[2] for item in result.criteria))
        self.assertTrue(any("Membership in the Social Democratic Party" in item[2] for item in result.criteria))
        for item in result.criteria:
            self.assertEqual(result.criteria_sources[item], FES_APPRENTICESHIP_FAQ_URL)

    def test_bachelor_qualification_statements_get_study_level_type(self):
        self.assertEqual(
            _classify_eligibility_statement("Proof of a completed Bachelor's degree is required."),
            ("study_level", "Study level"),
        )
        self.assertEqual(
            _classify_eligibility_statement("Nachweis eines abgeschlossenen Bachelorstudiums."),
            ("study_level", "Study level"),
        )

    def test_rosa_residence_exception_stays_attached_to_15_month_rule(self):
        statements = _split_criteria_statements(
            "You must not have been in Germany for more than 15 months. "
            "This applies unless you have already studied in Germany or are preparing for university studies."
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("15 months", statements[0])
        self.assertIn("unless", statements[0])

        german_statements = _split_criteria_statements(
            "Sie dürfen sich nicht länger als 15 Monate in Deutschland aufhalten. "
            "Ausnahme: Sie haben bereits in Deutschland studiert oder bereiten sich auf das Studium vor."
        )
        self.assertEqual(len(german_statements), 1)
        self.assertIn("Ausnahme", german_statements[0])

    def test_villigst_faq_process_exceptions_are_not_mandatory_but_admission_is(self):
        self.assertTrue(_is_mandatory_criterion(
            "doctoral_admission",
            "Applicants must provide evidence of admission to do a doctorate.",
        ))
        self.assertTrue(_is_mandatory_criterion(
            "doctoral_project_stage",
            "Applicants whose doctoral project is already in its final phase cannot be considered.",
        ))
        self.assertFalse(_is_mandatory_criterion(
            "application_requirements",
            "If you have worked on your doctoral project for longer than one year, you may still apply; explain separately why you are applying now.",
        ))
        self.assertFalse(_is_mandatory_criterion(
            "application_requirements",
            "Applicants do not have to be enrolled at the university during the doctorate.",
        ))

    def test_villigst_doctoral_faq_adds_admission_exceptions_and_final_phase(self):
        parsed = ExtractedPage(
            title="Evangelisches Studienwerk Doctoral Scholarship",
            description=None,
            provider_name="Evangelisches Studienwerk",
        )
        faq = """
        <html><body><main>
          <p>Do I have to be admitted to the doctorate at the time of application?</p>
          <p>Yes. You must provide evidence of admission (authorisation) to do a doctorate.</p>
          <p>Do I have to be enrolled during the doctorate?</p>
          <p>No, you do not have to be enrolled during the doctorate.</p>
          <p>If you are working longer than one year at your project, please inform us with a separate document, why you want to apply now.</p>
          <p>I am older than 35. Can I apply for a scholarship for the doctorate? Yes. Please explain your reasons in your CV.</p>
          <p>Applications from doctoral students whose work is already in the final phase cannot be considered for a doctoral scholarship.</p>
        </main></body></html>
        """
        result = _augment_villigst_doctoral_faq(parsed, faq, VILLIGST_DOCTORAL_FAQ_URL)
        criteria = {item[0]: item[2] for item in result.criteria}
        self.assertIn("doctoral_admission", criteria)
        self.assertIn("application_requirements", criteria)
        self.assertTrue(any("longer than one year" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "age_limit" for item in result.criteria))
        self.assertIn("doctoral_project_stage", criteria)
        self.assertTrue(all(url == VILLIGST_DOCTORAL_FAQ_URL for url in result.criteria_sources.values()))

    def test_line_preserving_cleanup_repairs_live_hec_theme_joins(self) -> None:
        from app.extraction import _clean_preserving_lines

        raw = (
            "Strengthening health systems andcapacity\n"
            "Access,inclusionand opportunity\n"
            "Water Managementand Sustainability\n"
            "CSC'ssix themes"
        )
        expected = (
            "Strengthening health systems and capacity\n"
            "Access, inclusion and opportunity\n"
            "Water Management and Sustainability\n"
            "CSC's six themes"
        )
        cleaned = _clean_preserving_lines(raw)
        self.assertEqual(cleaned, expected)
        self.assertEqual(_clean_preserving_lines(cleaned), cleaned)
        self.assertEqual(cleaned.count("\n"), 3)

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

    def test_filters_provider_directory_descriptions_from_applicant_criteria(self) -> None:
        html = """
        <html><body><main>
          <h1>Example Scholarship Directory</h1>
          <h2>Eligibility</h2>
          <p>International students can apply to various funding options listed here.</p>
          <p>Denominational organisations: Students wishing to study theology may apply for support.</p>
          <p>Applicants must hold a bachelor's degree from a recognised university.</p>
        </main></body></html>
        """
        criteria = extract_criteria_from_html(html)
        texts = [text for _kind, _label, text in criteria]
        self.assertEqual(
            texts,
            ["Applicants must hold a bachelor's degree from a recognised university."],
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

    def test_application_windows_extract_closing_date_not_opening_date(self) -> None:
        value = "Spring 2027: 15 January 2027 until 1 March 2027 Fall 2027: 15 July 2027 until 1 September 2027"
        self.assertEqual(_parse_deadline_date(value), "2027-03-01")

    def test_normalizes_german_application_window_closing_date(self) -> None:
        value = "15. November 2026 bis einschließlich 15. Januar 2027"
        self.assertEqual(_parse_deadline_date(value), "2027-01-15")

    def test_normalizes_german_numeric_application_window_closing_date(self) -> None:
        self.assertEqual(
            _parse_deadline_date("Der Zugang zum Bewerbungsportal ist vom 15.04.-15.06.2026 geöffnet."),
            "2026-06-15",
        )

    def test_extracts_foundation_supported_student_group_and_exclusions(self) -> None:
        html = """
        <html><body><main>
          <h1>Student scholarships</h1>
          <p>Do you have good to very good grades or academic achievements, are you interested in politics, are you committed and have a liberal, cosmopolitan attitude? Then apply for a scholarship.</p>
          <p>We support German and foreign students who study full-time at state or state-recognized universities and technical colleges.</p>
          <h2>Unfortunately, we cannot support the following:</h2>
          <ul>
            <li>Second degrees</li>
            <li>Part-time degrees</li>
            <li>Bachelor programmes for foreign, non-EU students</li>
          </ul>
        </main></body></html>
        """
        from bs4 import BeautifulSoup
        from app.extraction import _find_heading_section, _has_explicit_not_supported_heading
        root = BeautifulSoup(html, "html.parser")
        exclusion_section = _find_heading_section(
            root, ("Unfortunately, we cannot support the following",)
        )
        self.assertTrue(_has_explicit_not_supported_heading(root))
        self.assertIn("Second degrees", exclusion_section or "")
        page = parse_scholarship_page(html, "https://example.org/student-scholarships")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertTrue(any("German and foreign students" in item[2] for item in page.criteria))
        self.assertTrue(any(item[0] == "selection_criteria" for item in page.criteria))
        self.assertTrue(any(item[0] == "ineligibility" and "Second degrees" in item[2] for item in page.criteria))
        self.assertTrue(any(item[0] == "ineligibility" and "non-EU students" in item[2] for item in page.criteria))

    def test_extracts_implied_applicant_conditions_from_kaad_style_lists(self) -> None:
        html = """
        <html><body><main>
          <h1>KAAD Scholarship Programme 2</h1>
          <p>KAAD Scholarship Programme 2 supports international students already studying in Germany.</p>
          <ul>
            <li>come from a country in Africa, Asia, the Near and Middle East, or Latin America</li>
            <li>have not been in Germany for more than 15 months</li>
            <li>hold a residence permit for study purposes</li>
            <li>are already studying in Germany and have at least six months remaining in your program</li>
            <li>wish to pursue a master’s degree or a doctoral degree at a German university</li>
            <li>belong to the Catholic Church or another Christian denomination</li>
            <li>belong to another religion and are nominated by Catholic partners</li>
            <li>have sufficient knowledge of the German language</li>
          </ul>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/kaad-programme-2")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertGreaterEqual(len(page.criteria), 7)
        self.assertTrue(any("15 months" in item[2] for item in page.criteria))
        self.assertTrue(any("residence permit" in item[2] for item in page.criteria))
        self.assertTrue(any("Christian denomination" in item[2] for item in page.criteria))

    def test_filters_promotional_cta_copy_from_german_eligibility(self) -> None:
        html = """
        <html><body><main>
          <h1>Stipendium für Auszubildende – Lux Like Ausbildung</h1>
          <p>Das Stipendium unterstützt Auszubildende mit finanzieller Förderung während ihrer beruflichen Ausbildung und begleitet sie bei gesellschaftlichem Engagement.</p>
          <h2>Wer kann sich bewerben?</h2>
          <ul>
            <li>Personen unter 45 Jahre, die kein berufsqualifizierendes Studium abgeschlossen haben.</li>
            <li>Jetzt über Stipendien für die berufliche Ausbildung informieren und online bewerben!</li>
            <li>Du suchst ein Stipendium für deine Ausbildung?</li>
            <li>Dann kannst du bei der Seite des BMFTR mehr erfahren!</li>
          </ul>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html,
            "https://www.rosalux.de/berufliche-bildung",
            "Lux Like Ausbildung – Apprenticeship Scholarship",
        )
        self.assertIsNotNone(page)
        assert page is not None
        texts = [item[2].casefold() for item in page.criteria]
        self.assertTrue(any("unter 45 jahre" in value for value in texts))
        self.assertFalse(any("jetzt über stipendien" in value for value in texts))
        self.assertFalse(any("du suchst ein stipendium" in value for value in texts))
        self.assertFalse(any("bmftr mehr erfahren" in value for value in texts))

    def test_extracts_german_fes_international_student_requirements(self) -> None:
        html = """
        <html><body><main>
          <h1>Grundförderung</h1>
          <p>Die Grundförderung für Ausländer:innen richtet sich an internationale Studierende, die an einer deutschen Hochschule eingeschrieben sind und gute Leistungen erbringen möchten.</p>
          <p>Voraussetzung für eine Bewerbung sind erste benotete Leistungsnachweise und gute deutsche Sprachkenntnisse.</p>
          <ul>
            <li>bereits an einer deutschen, staatlichen oder staatlich anerkannten Hochschule oder Fachhochschule studieren</li>
            <li>sehr gute deutsche Sprachkenntnisse haben</li>
            <li>überdurchschnittliche Noten im Studium haben</li>
            <li>gesellschaftspolitisch engagiert sind</li>
            <li>sich mit den Werten der Sozialen Demokratie identifizieren</li>
          </ul>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html,
            "https://www.fes.de/studienfoerderung/stipendium/grundfoerderung-fuer-auslaender-innen",
            "FES Scholarship for International Students",
        )
        self.assertIsNotNone(page)
        assert page is not None
        texts = [item[2].casefold() for item in page.criteria]
        self.assertTrue(any("deutsche sprachkenntnisse" in value for value in texts))
        self.assertTrue(any("hochschule" in value for value in texts))
        self.assertTrue(any("noten im studium" in value for value in texts), repr(texts))
        self.assertTrue(any("gesellschaftspolitisch engagiert" in value for value in texts))
        self.assertTrue(any("sozialen demokratie" in value for value in texts), repr(texts))

    def test_extracts_german_fes_apprentice_requirements(self) -> None:
        html = """
        <html><body><main>
          <h1>Förderung für Auszubildende</h1>
          <p>Mit dem Stipendium für Auszubildende unterstützen wir engagierte Nachwuchskräfte während ihrer anerkannten beruflichen Ausbildung und stärken ihre gesellschaftliche Teilhabe.</p>
          <p>Wir suchen Auszubildende, die die Werte der Sozialen Demokratie teilen.</p>
          <ul>
            <li>am Anfang des ersten und spätestens am Anfang des zweiten Ausbildungsjahres stehen</li>
            <li>einen staatlich anerkannten Ausbildungsberuf erlernen</li>
            <li>einen Ausbildungsvertrag oder die schriftliche Zusage für einen Ausbildungsplatz haben</li>
            <li>deutsche Staatsangehörige oder Bürger:innen eines EU- oder EWR-Staates oder Geflüchtete oder geduldete Ausländer:innen sind</li>
            <li>keine anderen Stipendienleistungen aus öffentlichen Mitteln erhalten</li>
          </ul>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html,
            "https://www.fes.de/studienfoerderung/stipendium/stipendien-auszubildende",
            "FES Scholarship for Apprentices",
        )
        self.assertIsNotNone(page)
        assert page is not None
        texts = [item[2].casefold() for item in page.criteria]
        self.assertTrue(any("ausbildungsjahr" in value for value in texts), repr(texts))
        self.assertTrue(any("ausbildungsberuf" in value for value in texts))
        self.assertTrue(any("ausbildungsvertrag" in value for value in texts))
        self.assertTrue(any("staatsangehörige" in value for value in texts))

    def test_fes_related_programme_teasers_do_not_leak_into_apprentice_criteria(self) -> None:
        html = """
        <html><body><main>
          <h1>Förderung für Auszubildende</h1>
          <p>Das Stipendium für Auszubildende unterstützt Auszubildende während ihrer anerkannten beruflichen Ausbildung und stärkt ihre gesellschaftliche Teilhabe durch zusätzliche fachliche und persönliche Begleitung.</p>
          <ul>
            <li>am Anfang des ersten und spätestens am Anfang des zweiten Ausbildungsjahres stehen</li>
            <li>einen staatlich anerkannten Ausbildungsberuf erlernen</li>
          </ul>
          <h2>Finden Sie jetzt Ihr passendes Stipendienprogramm</h2>
          <div class="ce-defaults ce-teaser">
            <h3>Grundförderung für Ausländer:innen</h3>
            <p>Die Förderung richtet sich an Studierende, die bereits an einer deutschen Hochschule studieren.</p>
          </div>
          <div class="ce-defaults ce-teaser">
            <h3>Promotionsförderung für Ausländer:innen</h3>
            <p>Die Förderung richtet sich an ausländische Doktorand:innen, die zur Promotion zugelassen sind.</p>
          </div>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html,
            "https://www.fes.de/studienfoerderung/stipendium/stipendien-auszubildende",
            "FES Scholarship for Apprentices",
        )
        self.assertIsNotNone(page)
        assert page is not None
        texts = [item[2].casefold() for item in page.criteria]
        self.assertTrue(any("ausbildungsjahr" in value for value in texts), repr(texts))
        self.assertTrue(any("ausbildungsberuf" in value for value in texts), repr(texts))
        self.assertFalse(any("doktorand" in value for value in texts), repr(texts))
        self.assertFalse(any("hochschule studieren" in value for value in texts), repr(texts))


    def test_classifies_german_rosa_luxemburg_apprentice_age_and_residence_rules(self) -> None:
        html = """
        <html><body><main>
          <h1>Stipendium für Auszubildende – Lux Like Ausbildung</h1>
          <p>Das Stipendium unterstützt Auszubildende mit finanzieller Förderung während ihrer beruflichen Ausbildung und begleitet sie bei gesellschaftlichem Engagement.</p>
          <h2>Wer kann sich für ein Azubi-Stipendium bewerben?</h2>
          <ul>
            <li>Azubis in einer anerkannten Ausbildung nach BBiG/HwO oder in Gesundheitsberufen</li>
            <li>Engagierte junge Menschen in Schule, Verein, Initiative oder Ähnlichem</li>
            <li>Personen unter 45 Jahre, die kein berufsqualifizierendes Studium abgeschlossen haben</li>
            <li>Bewerber:innen mit ständigem Wohnsitz in Deutschland oder Aufenthaltstitel oder deutscher Staatsangehörigkeit</li>
          </ul>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html,
            "https://www.rosalux.de/berufliche-bildung",
            "Lux Like Ausbildung – Apprenticeship Scholarship",
        )
        self.assertIsNotNone(page)
        assert page is not None
        texts = [item[2].casefold() for item in page.criteria]
        self.assertTrue(any("anerkannten ausbildung" in value for value in texts))
        self.assertTrue(any("unter 45 jahre" in value for value in texts))
        self.assertTrue(any("wohnsitz in deutschland" in value for value in texts))
        self.assertIn("age_limit", [item[0] for item in page.criteria])
        self.assertIn("nationality", [item[0] for item in page.criteria])

    def test_extracts_german_apprentice_scholarship_funding_deadline_and_criteria(self) -> None:
        html = """
        <html><body><main>
          <h1>Stipendien für Auszubildende</h1>
          <p>Der Zugang zu unserem Bewerbungsportal ist zwischen dem 15.04.-15.06.2026 geöffnet.</p>
          <p>Mit unserem Stipendium für Auszubildende erhalten Auszubildende 300 Euro im Monat.</p>
          <h2>Wer kann sich bewerben?</h2>
          <ol>
            <li>eine Ausbildung in einem anerkannten Ausbildungsberuf absolvieren.</li>
            <li>zu dem in § 8 des Berufsausbildungsgesetzes genannten Personenkreis gehören.</li>
            <li>die Voraussetzungen nach § 10 BAföG entsprechend erfüllen.</li>
            <li>Für die Entscheidung über den Zugang zur Förderung ist das Verzeichnis der anerkannten Ausbildungsberufe des Bundesinstituts für Berufsbildung (BIBB) in der jeweils geltenden Fassung zugrunde zu legen.</li>
            <li>Im Bereich der bundesrechtlich geregelten Ausbildungsberufe ist dieses Verzeichnis abschließend.</li>
          </ol>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/apprentice-scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("15.04.-15.06.2026", page.fields["deadline_text"])
        self.assertEqual(_parse_deadline_date(page.fields["deadline_text"]), "2026-06-15")
        self.assertIn("300 Euro im Monat", page.fields["funding_summary"])
        self.assertTrue(any("anerkannten Ausbildungsberuf" in item[2] for item in page.criteria))
        self.assertTrue(any("§ 10 BAföG" in item[2] for item in page.criteria))
        self.assertFalse(any("Für die Entscheidung über den Zugang" in item[2] for item in page.criteria))
        self.assertFalse(any("dieses Verzeichnis abschließend" in item[2] for item in page.criteria))

    def test_extracts_german_application_windows_from_list_items(self) -> None:
        html = """
        <html><body><main>
          <h1>Hanns Seidel Scholarship Programme</h1>
          <p>Unser Bewerbungsportal ist geöffnet:</p>
          <ul>
            <li>15. November 2026 bis einschließlich 15. Januar 2027: Promotionsstipendien.</li>
            <li>15. Mai 2027 bis einschließlich 15. Juli 2027: Journalistisches Förderprogramm.</li>
          </ul>
          <h2>Who can apply?</h2>
          <p>Applicants must hold a recognised degree and study full-time in Germany.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/hss-scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("15. November 2026", page.fields["deadline_text"])
        self.assertIn("15. Mai 2027", page.fields["deadline_text"])
        self.assertEqual(_parse_deadline_date(page.fields["deadline_text"]), "2027-01-15")

    def test_deadline_heading_section_is_extracted(self) -> None:
        html = """
        <html><body><main>
          <h1>Tailwind for Talents Scholarship Programme</h1>
          <h2>Our next application deadlines:</h2>
          <p>Spring 2027: 15 January 2027 until 1 March 2027 Fall 2027: 15 July 2027 until 1 September 2027</p>
          <h2>Who can apply?</h2>
          <p>International students who completed their first degree abroad may apply before starting a Master's degree in Germany.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/scholarships")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("1 March 2027", page.fields["deadline_text"])
        self.assertEqual(_parse_deadline_date(page.fields["deadline_text"]), "2027-03-01")


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
        self.assertEqual(
            _classify_application_status(
                "The online application portal opens on January 15, 2027, and closes on March 1, 2027.",
                "2027-03-01",
            ),
            "upcoming",
        )
        self.assertEqual(
            _classify_application_status("Applications are open until March 1, 2027.", "2027-03-01"),
            "open",
        )

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
        criteria = page.criteria
        self.assertEqual(len(criteria), 3)
        self.assertEqual(
            [item[0] for item in criteria],
            ["eligibility", "study_level", "eligibility"],
        )
        self.assertTrue(_is_mandatory_criterion(criteria[0][0], criteria[0][2]))
        self.assertTrue(_is_mandatory_criterion(criteria[1][0], criteria[1][2]))
        self.assertFalse(_is_mandatory_criterion(criteria[2][0], criteria[2][2]))

    def test_explicit_eligibility_heading_marks_conditions_mandatory_but_priority_informational(self) -> None:
        from app.extraction import _is_mandatory_criterion

        self.assertTrue(_is_mandatory_criterion("eligibility", "am actively involved in voluntary work"))
        self.assertTrue(_is_mandatory_criterion("language_requirements", "German language skills of at least B2"))
        self.assertTrue(_is_mandatory_criterion(
            "nationality",
            "deutsche Staatsangehörige oder Bürger:innen eines EU- oder EWR-Staates oder Geflüchtete oder geduldete Ausländer:innen sind",
        ))
        self.assertTrue(_is_mandatory_criterion(
            "work_experience",
            "einen Ausbildungsvertrag oder die schriftliche Zusage für einen Ausbildungsplatz haben",
        ))
        self.assertFalse(_is_mandatory_criterion("nationality", "Priority is given to applicants from DAC countries"))
        self.assertFalse(_is_mandatory_criterion("work_experience", "Relevant experience is preferred"))
        self.assertFalse(_is_mandatory_criterion("eligibility", "Priority is given to applicants from DAC countries"))

    def test_absence_of_doctoral_completion_awards_is_informational(self):
        self.assertFalse(_is_mandatory_criterion(
            "study_level",
            "No doctoral completion scholarships are awarded.",
        ))
        self.assertFalse(_is_mandatory_criterion(
            "study_level",
            "Keine Promotionsabschlussstipendien werden vergeben.",
        ))

    def test_mandatory_criteria_classification_is_conservative(self) -> None:
        self.assertTrue(_is_mandatory_criterion("eligibility", "Applicants must hold a bachelor's degree."))
        self.assertTrue(_is_mandatory_criterion("ineligibility", "Applicants with dual nationality are not eligible."))
        self.assertFalse(_is_mandatory_criterion("required_documents", "Academic transcripts and reference letters."))
        self.assertFalse(_is_mandatory_criterion("application_requirements", "Submit the application form before the deadline."))
        self.assertTrue(_is_mandatory_criterion("eligibility", "Applicants must hold a bachelor's degree."))
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
        self.assertFalse(_is_mandatory_criterion(post_selection[0][0], post_selection[0][2]))
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
                     All candidates arerequired to fulfill this scholarship eligibility criterion
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
        self.assertIn("All candidates are required", shared_score_rules[0][2])
        self.assertNotIn("arerequired", shared_score_rules[0][2])
        self.assertFalse(any(
            kind == "required_documents" and "GRE" in value
            for kind, _label, value in page.criteria
        ))

    def test_hec_aggregation_requires_overview_and_eligibility_pages(self) -> None:
        self.assertIsNone(_parse_hec_knowledge_corridor({
            "overview": ("<html><body><p>Programme</p></body></html>", "https://example.org/")
        }))


    def test_corridor_classifies_existing_phd_holders_as_ineligible(self) -> None:
        base = "https://www.hec.gov.pk/english/scholarshipsgrants/US-Pakcorridor/Pages/"
        pages = {
            "overview": ("""
                <div class="ms-rtestate-field">
                  <h1>US-Pakistan Knowledge Corridor PhD Scholarship</h1>
                  <p>The programme provides PhD scholarships for Pakistani students.</p>
                </div>
            """, base + "default.aspx"),
            "eligibility": ("""
                <div class="ms-rtestate-field">
                  <p>Pakistani/AJK nationals</p>
                  <p>Those having PhD Degree are not eligible.</p>
                </div>
            """, base + "Eligibility-Criteria.aspx"),
        }
        page = _parse_hec_knowledge_corridor(pages)
        self.assertIsNotNone(page)
        assert page is not None
        exclusions = [item for item in page.criteria if item[0] == "ineligibility"]
        self.assertEqual(len(exclusions), 1)
        self.assertEqual(exclusions[0][1], "Existing PhD holders")


    def test_corridor_priority_subject_evidence_preserves_line_breaks(self) -> None:
        base = "https://www.hec.gov.pk/english/scholarshipsgrants/US-Pakcorridor/Pages/"
        pages = {
            "overview": ("""
                <div class="ms-rtestate-field">
                  <p>PhD scholarships for Pakistani students to study in the United States.</p>
                </div>
            """, base + "default.aspx"),
            "eligibility": ("""
                <div class="ms-rtestate-field">
                  <p>Pakistani/AJK nationals</p>
                </div>
            """, base + "Eligibility-Criteria.aspx"),
            "priority_subjects": ("""
                <div class="ms-rtestate-field">
                  <p>Crop Production<br>Soil and Environmental Sciences<br>Climate Change andEnvironmental Engineering<br>Water Managementand Sustainability<br>Computational Biology</p>
                </div>
            """, base + "Priority-Subject-Areas.aspx"),
        }
        page = _parse_hec_knowledge_corridor(pages)
        self.assertIsNotNone(page)
        assert page is not None
        evidence_text = next(
            value for name, value in page.evidence
            if name == "priority_subject_areas"
        )
        expected_subjects = (
            "Crop Production\nSoil and Environmental Sciences\n"
            "Climate Change and Environmental Engineering\n"
            "Water Management and Sustainability\nComputational Biology"
        )
        self.assertEqual(evidence_text, expected_subjects)
        self.assertEqual(page.fields["priority_subject_areas"], expected_subjects)
        self.assertNotIn("andEnvironmental", evidence_text)
        self.assertNotIn("Managementand", evidence_text)
        self.assertEqual(
            page.evidence_sources[("priority_subject_areas", evidence_text)],
            base + "Priority-Subject-Areas.aspx",
        )



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
          <p>Strengthening health systems andcapacity</p>
          <p>Access, inclusionand opportunity</p>
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

    def test_hec_sharepoint_repairs_joined_words_found_in_saved_eligibility(self) -> None:
        self.assertEqual(
            _clean(
                "throughoutthe academic career; Researchersof approved R&D "
                "Organizations; first divisionin 17/18 years; "
                "Pakistannational; attheCommonwealth portal"
            ),
            "throughout the academic career; Researchers of approved R&D "
            "Organizations; first division in 17/18 years; "
            "Pakistan national; at the Commonwealth portal",
        )

    def test_hec_output_boundary_repairs_fields_and_commonwealth_criteria(self) -> None:
        from app.extraction import _clean

        self.assertEqual(
            _clean("Benefits stated withouta category restriction; "
                   "applicationto cancer research; Thefemale nomination"),
            "Benefits stated without a category restriction; "
            "application to cancer research; The female nomination",
        )
        self.assertEqual(_clean("Closing date: 20 October 2026 at 16:00BST"),
                         "Closing date: 20 October 2026 at 16:00 BST")
        self.assertEqual(_clean("University(overall ranking)"),
                         "University (overall ranking)")

    def test_hec_repairs_exact_joined_tokens_from_live_programme_pages(self) -> None:
        from app.extraction import _clean

        self.assertEqual(
            _clean(
                "doctoralstudy at aUK university under the CSC'ssix themes; "
                "HEC nominationprocess; submit onlineapplication forms; "
                "Access,inclusion and opportunity; HATtests; "
                "onlineapplications"
            ),
            "doctoral study at a UK university under the CSC's six themes; "
            "HEC nomination process; submit online application forms; "
            "Access, inclusion and opportunity; HAT tests; online applications",
        )

    def test_hec_sharepoint_repairs_observed_joined_words_without_rewriting_other_spelling(self) -> None:
        self.assertEqual(
            _clean("Benefits stated withouta category restriction; applicationto cancer research"),
            "Benefits stated without a category restriction; application to cancer research",
        )
        self.assertEqual(
            _clean("doctoralstudy; benefits without acategory restriction; must not beavailing"),
            "doctoral study; benefits without a category restriction; must not be availing",
        )
        self.assertEqual(
            _clean("CSC'ssix themes; Allapplicants; guaranteefinal selection"),
            "CSC's six themes; All applicants; guarantee final selection",
        )
        self.assertEqual(
            _clean("All candidates arerequired to fulfill the scholarship criteria."),
            "All candidates are required to fulfill the scholarship criteria.",
        )
        self.assertEqual(
            _clean("Climate Change andEnvironmental Engineering"),
            "Climate Change and Environmental Engineering",
        )
        self.assertEqual(_clean("Strengthening globalpeace, security and governance"),
                         "Strengthening global peace, security and governance")
        # Preserve source spelling rather than silently correcting factual evidence.
        self.assertIn("Pharmacetuical", _clean("Pharmacetuical Sciences"))

    def test_hec_repairs_saved_commonwealth_text_joins(self) -> None:
        from app.extraction import _clean

        self.assertEqual(
            _clean(
                "Academic Year2027-28; 16years Bachelors degree; "
                "17/18years Masters degree; submittheir final degree; "
                "Pakistan nationaluniversity; USD 2,000/- oractual, whichever is lower"
            ),
            "Academic Year 2027-28; 16 years Bachelors degree; "
            "17/18 years Masters degree; submit their final degree; "
            "Pakistan national university; USD 2,000/- or actual, whichever is lower",
        )

    def test_scrapes_eligibility_from_unlabelled_official_page_paragraphs_and_lists(self) -> None:
        from bs4 import BeautifulSoup
        from app.extraction import _extract_unlabelled_criteria

        html = """
        <main>
          <h1>International Scholarship Programme</h1>
          <p>Applicants must hold a bachelor's degree in a relevant subject.</p>
          <ul>
            <li>Applicants must be citizens of an eligible country.</li>
            <li>Applicants should have English language proficiency at B2 level.</li>
            <li>Relevant professional experience is preferred.</li>
          </ul>
          <p>Applications close on 30 September 2027.</p>
        </main>
        """
        criteria = _extract_unlabelled_criteria(BeautifulSoup(html, "html.parser"))
        texts = [item[2] for item in criteria]

        self.assertTrue(any("bachelor's degree" in text for text in texts))
        self.assertTrue(any("citizens of an eligible country" in text for text in texts))
        self.assertTrue(any("English language proficiency" in text for text in texts))
        preference = next(item for item in criteria if "professional experience" in item[2])
        self.assertEqual(preference[0], "selection_criteria")
        self.assertFalse(any("30 September 2027" in text for text in texts))

    def test_scrapes_requirements_from_linked_official_eligibility_page(self) -> None:
        from app.extraction import extract_criteria_from_html

        html = """
        <main>
          <h1>Eligibility</h1>
          <h2>Who can apply</h2>
          <ul>
            <li>Applicants must hold a recognised bachelor's degree.</li>
            <li>Applicants must be citizens of an eligible country.</li>
          </ul>
          <h2>Language requirements</h2>
          <p>Applicants must demonstrate English language proficiency.</p>
        </main>
        """
        criteria = extract_criteria_from_html(html)
        texts = [item[2] for item in criteria]

        self.assertTrue(any("recognised bachelor's degree" in text for text in texts))
        self.assertTrue(any("eligible country" in text for text in texts))
        self.assertTrue(any("English language proficiency" in text for text in texts))

    def test_no_upper_age_limit_is_informational_not_mandatory(self) -> None:
        from app.extraction import _is_mandatory_criterion

        self.assertFalse(
            _is_mandatory_criterion(
                "age_limit",
                "There is no upper age limit for this scholarship.",
            )
        )
        self.assertTrue(
            _is_mandatory_criterion(
                "age_limit",
                "Maximum age is 35 years.",
            )
        )

    def test_hec_repairs_additional_exact_joins_from_live_announcement(self) -> None:
        from app.extraction import _clean

        self.assertEqual(
            _clean(
                "topursue; Master'sand PHD; forthe Commonwealth; bythe CSC; "
                "femalenomination; permanentresident; fieldof study; "
                "candidatesmay apply; beforethe session; inHAT test; "
                "mayupload results; prescribedby HEC; tosubmit forms; fromthe portal"
            ),
            "to pursue; Master's and PHD; for the Commonwealth; by the CSC; "
            "female nomination; permanent resident; field of study; "
            "candidates may apply; before the session; in HAT test; "
            "may upload results; prescribed by HEC; to submit forms; from the portal",
        )

    def test_commonwealth_authority_keeps_one_nomination_and_final_selection_statement(self) -> None:
        from app.extraction import _parse_hec_commonwealth_announcement

        url = "https://www.hec.gov.pk/english/HECAnnouncements/Pages/CW-Scholarship.aspx"
        html = """
        <div class="ms-rtestate-field">
          <h1>Commonwealth Scholarship Programme 2027-28</h1>
          <p>The scholarships are for full-time taught Master's and PhD study at a UK university.</p>
          <p>HEC will undertake the nomination process in Pakistan in accordance with its prescribed
             eligibility and merit criteria, while the final selection of scholars will be made by
             the Commonwealth Scholarship Commission. Nomination by HEC does not guarantee final
             selection, as the final selection is made by the Commonwealth Scholarship Commission.
             Please note that HEC has only a facilitation role in the nomination process, as the
             final selection will be made by the donor country.</p>
        </div>
        """
        page = _parse_hec_commonwealth_announcement(html, url)
        self.assertIsNotNone(page)
        assert page is not None
        authority = [
            value for kind, label, value in page.criteria
            if kind == "selection_process" and label == "Final selection authority"
        ]
        self.assertEqual(len(authority), 1)
        self.assertIn("HEC will undertake the nomination process", authority[0])
        self.assertIn("final selection of scholars will be made", authority[0])
        self.assertNotIn("does not guarantee", authority[0])
        self.assertNotIn("facilitation role", authority[0])

    def test_rejects_unrelated_or_wrong_cycle_hec_page(self) -> None:
        from app.extraction import _parse_hec_commonwealth_announcement

        self.assertIsNone(_parse_hec_commonwealth_announcement(
            "<html><body><p>General HEC scholarship information.</p></body></html>"
        ))


    def test_line_preserving_cleaner_repairs_live_hec_joined_words(self) -> None:
        from app.extraction import _clean_preserving_lines

        source = (
            "Water Managementand Sustainability\n"
            "Strengthening health systems andcapacity\n"
            "Access, inclusionand opportunity\n"
            "Keep this\n\nseparate"
        )
        self.assertEqual(
            _clean_preserving_lines(source),
            "Water Management and Sustainability\n"
            "Strengthening health systems and capacity\n"
            "Access, inclusion and opportunity\n"
            "Keep this\n\nseparate",
        )

    def test_commonwealth_output_normalizes_description_and_preserves_theme_lines(self) -> None:
        from app.extraction import _parse_hec_commonwealth_announcement

        url = "https://www.hec.gov.pk/english/HECAnnouncements/Pages/CW-Scholarship.aspx"
        html = """
        <div class="ms-rtestate-field">
          <h1>Commonwealth Scholarship Programme 2027-28</h1>
          <p>The scholarships are for full-time taught Master'sand PhD study at aUK university,
             commencing in September/October 2027, and are offered under the CSC'ssix themes.</p>
          <p>HEC will undertake the nominationprocess in Pakistan.</p>
          <p>Applicants are required to submit onlineapplication forms at the HEC portal.</p>
          <p>Science and technology for development</p>
          <p>Strengthening health systems andcapacity</p>
          <p>Access, inclusionand opportunity</p>
          <a href="https://scholarship.hec.gov.pk/">HEC application portal</a>
        </div>
        """
        page = _parse_hec_commonwealth_announcement(html, url)
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("Master's and PhD study at a UK university", page.description or "")
        self.assertIn("CSC's six themes", page.description or "")
        self.assertNotIn("Master'sand", page.description or "")
        self.assertIn("Strengthening health systems and capacity", page.fields["development_themes"])
        self.assertIn("Access, inclusion and opportunity", page.fields["development_themes"])
        self.assertIn("\n", page.fields["development_themes"])
        theme_evidence = next(
            value for name, value in page.evidence if name == "development_themes"
        )
        self.assertEqual(theme_evidence, page.fields["development_themes"])
        self.assertEqual(page.evidence_sources[("development_themes", theme_evidence)], url)
        self.assertTrue(all(source == url for source in page.criteria_sources.values()))
        self.assertTrue(any("nomination process" in value for _kind, _label, value in page.criteria))


    def test_extracts_eligibility_under_question_mark_heading(self) -> None:
        html = """
        <html><body><main>
          <h1>Tailwind for Talents: Scholarships for Graduates and PhD students</h1>
          <h2>Who can apply?</h2>
          <p>International students who have completed their first degree abroad can apply prior to starting a Master's degree program in Germany.</p>
          <p>Priority is given to applicants from DAC countries who have not yet taken up residence in Germany at the time of their application.</p>
          <p>International PhD students who have completed their graduate degree abroad may apply for a PhD program in Germany.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://www.boell.de/en/scholarships")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertTrue(any("completed their first degree abroad" in item[2] for item in page.criteria))
        self.assertTrue(any("DAC countries" in item[2] for item in page.criteria))
        self.assertTrue(any(item[0] == "study_level" and "Master" in item[2] for item in page.criteria))
        self.assertTrue(any(item[0] == "study_level" and "PhD" in item[2] for item in page.criteria))

    def test_extracts_language_requirement_split_across_paragraphs_in_requirements_section(self) -> None:
        html = """
        <html><body><main>
          <h1>Research Fellowship</h1>
          <h2>Requirements</h2>
          <p>Applicants are required to have a very good command</p>
          <p>of the English language.</p>
        </main></body></html>
        """
        criteria = extract_criteria_from_html(html)
        self.assertTrue(any(
            item[0] == "language_requirements"
            and "very good command" in item[2].lower()
            and "english language" in item[2].lower()
            for item in criteria
        ))

    def test_extracts_tabular_requirements_under_scholarship_for_studies(self) -> None:
        html = """
        <html><body><main>
          <h1>Hanns Seidel Foundation Requirements</h1>
          <h4>Scholarship for Studies</h4>
          <table><tr><td>am less than 45 years old</td></tr>
          <tr><td>have proof of German language skills of at least B2 or comparable level</td></tr>
          <tr><td>show above-average performance at school or in my studies</td></tr>
          <tr><td>am actively involved in voluntary work</td></tr>
          <tr><td>am politically interested</td></tr>
          <tr><td>support democracy, rule of law, and human rights</td></tr>
          <tr><td>complete a full-time course of study at a state or state-recognized university in Germany.</td></tr></table>
          <ul><li>Richtlinien Studienförderung</li></ul>
        </main></body></html>
        """
        criteria = extract_criteria_from_html(html)
        texts = [item[2] for item in criteria]
        self.assertTrue(any("less than 45 years old" in text for text in texts))
        self.assertTrue(any("German language skills" in text for text in texts))
        self.assertTrue(any("full-time course of study" in text for text in texts))
        self.assertIn("age_limit", [item[0] for item in criteria])
        self.assertIn("language_requirements", [item[0] for item in criteria])
        self.assertFalse(any("please contact" in text.lower() for text in texts))
        self.assertFalse(any("submit your application directly" in text.lower() for text in texts))


    def test_filters_rosa_lux_apprentice_promotion_and_repairs_age_rule(self) -> None:
        html = """
        <html><body><main>
          <h1>Lux Like Ausbildung</h1>
          <p>Das neue Förderprogramm „Lux Like Ausbildung“ unterstützt Azubis finanziell und mit einem umfangreichen Begleitprogramm.</p>
          <p>Stipendium für die berufliche Ausbildung – das bietet dir „Lux Like Ausbildung“:</p>
          <p>Individuelle Betreuung durch Mentor*innen – egal ob in der Ausbildung oder deinem Aktivismus.</p>
          <h2>Wer kann sich bewerben?</h2>
          <ul>
            <li>Azubis in einer anerkannten Ausbildung (BBiG/HwO, Gesundheitsberufe oder landesrechtlich geregelt).</li>
            <li>Personen unter 45 Jahre (mit Ausnahmen, z.</li>
            <li>B. für Zweitausbildung oder mit Kindern), die kein berufsqualifizierendes Studium abgeschlossen haben.</li>
            <li>Bewerber*innen mit ständigem Wohnsitz in Deutschland oder Aufenthaltstitel (§ 8 BAföG-Gesetz) oder deutscher Staatsangehörigkeit.</li>
            <li>Ausbildungsvertrag / Schulbescheinigung oder Zusage des Betriebes / der Schule.</li>
          </ul>
          <p>Hier kannst du prüfen, ob deine Ausbildung anerkannt ist: https://www.bibb.de/de/65925.php</p>
          <p>Die restlichen, unpersönlicheren Felder füllst du mit deinen Personaldaten.</p>
        </main></body></html>
        """
        criteria = extract_criteria_from_html(html)
        texts = [item[2] for item in criteria]
        age = next(item for item in texts if "unter 45 Jahre" in item)
        self.assertIn("z. B. für Zweitausbildung", age)
        self.assertIn("kein berufsqualifizierendes Studium abgeschlossen", age)
        self.assertTrue(any("anerkannten Ausbildung" in item for item in texts))
        self.assertTrue(any("ständigem Wohnsitz" in item for item in texts))
        self.assertFalse(any("umfangreichen Begleitprogramm" in item for item in texts))
        self.assertFalse(any("Mentor*innen" in item for item in texts))
        self.assertFalse(any("Hier kannst du prüfen" in item for item in texts))
        self.assertFalse(any("unpersönlicheren Felder" in item for item in texts))


    def test_funding_amount_is_not_misclassified_as_eligibility(self) -> None:
        html = """
        <html><body><main>
          <h1>Stipendien für Auszubildende</h1>
          <p>Mit unserem Stipendium für Auszubildende erhalten Auszubildende 300 Euro im Monat.</p>
          <h2>Wer kann sich bewerben?</h2>
          <ol>
            <li>eine Ausbildung in einem anerkannten Ausbildungsberuf absolvieren.</li>
            <li>zu dem in § 8 des Berufsausbildungsgesetzes genannten Personenkreis gehören.</li>
            <li>die Voraussetzungen nach § 10 BAföG entsprechend erfüllen.</li>
          </ol>
        </main></body></html>
        """
        page = parse_scholarship_page(html, "https://example.org/apprentice-scholarship")
        self.assertIsNotNone(page)
        assert page is not None
        self.assertIn("300 Euro im Monat", page.fields["funding_summary"])
        self.assertEqual(len(page.criteria), 3)
        self.assertFalse(any("300 Euro" in item[2] for item in page.criteria))


    def test_hss_apprentice_criteria_exclude_administrative_and_informational_notes(self) -> None:
        html = """
        <html><body><main>
          <h1>Stipendien für Auszubildende</h1>
          <h2>Wer kann sich bewerben?</h2>
          <ol>
            <li>eine Ausbildung in einem anerkannten Ausbildungsberuf auf der Grundlage des Berufsbildungsgesetzes (BBiG) absolvieren.</li>
            <li>zu dem in § 8 des Berufsausbildungsgesetzes (BAföG) genannten Personenkreis gehören.</li>
            <li>die Voraussetzungen nach § 10 BAföG entsprechend erfüllen.</li>
            <li>Für die Entscheidung über den Zugang zur Förderung ist das Verzeichnis der anerkannten Ausbildungsberufe des Bundesinstituts für Berufsbildung (BIBB) in der jeweils geltenden Fassung zugrunde zu legen.</li>
            <li>Im Bereich der bundesrechtlich geregelten Ausbildungsberufe ist dieses Verzeichnis abschließend.</li>
            <li>Zur Auslegung der Fördervoraussetzungen nach Ziffer 1 bis 3 gilt Folgendes: Die Förderfähigkeit beschränkt sich nicht auf das Absolvieren einer Erstausbildung.</li>
            <li>Ein vor der Aufnahme in die Förderung erfolgter Studien- oder Ausbildungsabbruch steht einer Aufnahme in die Förderung nicht entgegen.</li>
          </ol>
        </main></body></html>
        """
        criteria = extract_criteria_from_html(html)
        texts = [item[2] for item in criteria]
        self.assertEqual(len(texts), 5)
        self.assertTrue(any("anerkannten Ausbildungsberuf" in item for item in texts))
        self.assertTrue(any("§ 8 des Berufsausbildungsgesetzes" in item for item in texts))
        self.assertTrue(any("§ 10 BAföG" in item for item in texts))
        self.assertFalse(any("BIBB" in item for item in texts))
        self.assertFalse(any("abschließend" in item for item in texts))
        clarifications = [item for item in criteria if item[0] == "application_requirements"]
        self.assertEqual(len(clarifications), 2)
        self.assertTrue(any("Erstausbildung" in item[2] for item in clarifications))
        self.assertTrue(any("Ausbildungsabbruch" in item[2] for item in clarifications))
        self.assertTrue(all(not _is_mandatory_criterion(item[0], item[2]) for item in clarifications))


    def test_accepts_german_hss_scholarship_landing_page(self) -> None:
        html = """
        <html><body><main>
          <h1>Studieren – Horizonte erweitern – Zukunft gestalten</h1>
          <p>Ein Stipendium ist weit mehr als nur eine finanzielle Hilfe: Es bietet auch viele interessante Veranstaltungen, eine Gemeinschaft Gleichgesinnter und wertvolle Kontakte. Das Beste daran? Die Chancen stehen gut, dass auch Sie alle nötigen Voraussetzungen für die Bewerbung erfüllen.</p>
          <p>Sie erfüllen die Voraussetzungen und finden sich in unserem Programm wieder?
             Dann bewerben Sie sich! Unser Bewerbungsportal ist geöffnet.</p>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html,
            "https://www.hss.de/stipendium/",
            "Hanns Seidel Foundation – Scholarships",
        )
        self.assertIsNotNone(page)
        assert page is not None
        self.assertEqual(page.title, "Studieren – Horizonte erweitern – Zukunft gestalten")


    def test_thousands_separator_is_not_misread_as_a_calendar_date(self) -> None:
        from app.extraction import DATE_PATTERN

        for value in (
            "The monthly scholarship is worth 1.500 Euro.",
            "Applicants receive 3.500 Euro per semester.",
            "Funding amounts range from 1.000 to 2.500 Euro.",
        ):
            with self.subTest(value=value):
                self.assertIsNone(DATE_PATTERN.search(value))

        self.assertIsNotNone(DATE_PATTERN.search("Applications close on 15.04.2027."))
        self.assertIsNotNone(DATE_PATTERN.search("Deadline: 15/04/2027."))


    def test_funding_amount_under_deadline_heading_does_not_create_deadline(self) -> None:
        html = """
        <html><body><main>
          <h1>International Student Scholarship</h1>
          <p>The programme supports eligible students studying in Germany.</p>
          <h2>Our Next Application Deadlines</h2>
          <p>Monthly funding is 1.500 Euro for up to 3.5 years.</p>
          <h2>Funding</h2>
          <p>Recipients receive 1.500 Euro per month.</p>
          <h2>Eligibility</h2>
          <ul><li>Applicants must be enrolled at a German university.</li></ul>
        </main></body></html>
        """
        page = parse_scholarship_page(
            html,
            "https://provider.example/international-student-scholarship",
        )
        self.assertIsNotNone(page)
        assert page is not None
        self.assertNotIn("deadline_text", page.fields)
        self.assertIn("1.500 Euro", page.fields.get("funding_summary", ""))


    def test_selection_and_target_audience_are_informational_not_mandatory(self) -> None:
        from app.extraction import _is_mandatory_criterion

        for kind, wording in (
            ("target_audience", "The programme is aimed at early-career researchers."),
            ("selection_process", "Candidates are shortlisted by an independent panel."),
            ("selection_criteria", "Preference is given to applicants with community involvement."),
        ):
            with self.subTest(kind=kind):
                self.assertFalse(_is_mandatory_criterion(kind, wording))



    def test_provider_priority_and_welcome_language_is_informational(self) -> None:
        html = """
        <html><body><main>
          <h1>International Student Scholarship</h1>
          <p>Priority will be given to international students from DAC countries.</p>
          <p>We particularly welcome applications from students who completed their degree abroad.</p>
          <p>Applicants must be enrolled at a state-recognized university in Germany.</p>
        </main></body></html>
        """
        criteria = extract_criteria_from_html(html)
        preferences = [item for item in criteria if item[0] == "selection_criteria"]
        mandatory = [item for item in criteria if _is_mandatory_criterion(item[0], item[2])]
        self.assertTrue(any("Priority will be given" in item[2] for item in preferences))
        self.assertTrue(any("particularly welcome" in item[2] for item in preferences))
        self.assertFalse(any("Priority will be given" in item[2] for item in mandatory))
        self.assertFalse(any("particularly welcome" in item[2] for item in mandatory))
        self.assertTrue(any("must be enrolled" in item[2] for item in mandatory))


    def test_encouragement_to_apply_despite_formal_criteria_is_not_a_gate(self) -> None:
        html = """
        <html><body><main>
          <h1>International Scholarship</h1>
          <p>We encourage applicants to apply even if they do not meet the formal requirements.
             We decide on these applications on a case-by-case basis.</p>
        </main></body></html>
        """
        criteria = extract_criteria_from_html(html)
        preference = next(
            (item for item in criteria if "encourage applicants" in item[2].lower()),
            None,
        )
        self.assertIsNotNone(preference)
        assert preference is not None
        self.assertEqual(preference[0], "selection_criteria")
        self.assertFalse(_is_mandatory_criterion(preference[0], preference[2]))


    def test_kiel_deutschlandstipendium_separates_eligibility_from_selection_and_documents(self):
        parsed = ExtractedPage(
            title="University of Kiel – Deutschlandstipendium",
            description=None,
            provider_name="Kiel University",
        )
        html = """
        <html><body><main>
          <h1>Information for scholarship recipients</h1>
          <p>All prospective students of Kiel University as well as students of all subjects
             who are already enrolled at Kiel University are eligible to apply.</p>
          <p>Any university entrance qualification that is recognized for university studies
             at the University of Kiel also entitles the holder to apply.</p>
          <p>In addition to a first degree, second or supplementary degree programs as well as
             Master's degree programs are generally eligible for funding.</p>
          <p>Those who already receive merit-based financial support exceeding €30 per month
             will not receive a Germany Scholarship during the funding period.</p>
          <p>The application deadline for the Germany Scholarship 2026/2027 has passed.
             The application deadline for the 2027/2028 scholarship will be published here
             at the beginning of 2027.</p>
          <ul><li>Curriculum vitae</li><li>Letter of motivation</li></ul>
          <p>Applicants who have successfully participated in a Software Challenge and who
             are applying to CAU for Computer Science must submit the scholarship certificate
             and a recommendation letter.</p>
          <p>The following criteria are viewed favorably: special achievements, awards and prizes from the last two years, prior vocational training, internships or voluntary service lasting at least two months.</p>
        </main></body></html>
        """
        result = _augment_kiel_deutschlandstipendium(parsed, html)
        self.assertTrue(any(item[0] == "eligibility" and "preparing to start" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "application_requirements" and "foreign university entrance qualification" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "target_audience" and "second degrees" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "ineligibility" and "exceeding €30" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "application_requirements" and "beginning of 2027" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "required_documents" and "curriculum vitae" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "application_requirements" and "Software Challenge" in item[2] for item in result.criteria))
        self.assertTrue(all(result.criteria_sources[item] == KIEL_DEUTSCHLANDSTIPENDIUM_URL for item in result.criteria))
        self.assertTrue(any(item[0] == "selection_criteria" for item in result.criteria))
        self.assertFalse(any(item[0] == "eligibility" and "social involvement" in item[2].lower() for item in result.criteria))

    def test_kiel_deutschlandstipendium_does_not_invent_a_future_deadline(self):
        parsed = ExtractedPage(
            title="University of Kiel – Deutschlandstipendium",
            description=None,
            provider_name="Kiel University",
        )
        html = """
        <html><body><main>
          <p>The application deadline for 2026/2027 has passed.
             The 2027/2028 deadline will be published at the beginning of 2027.</p>
        </main></body></html>
        """
        result = _augment_kiel_deutschlandstipendium(parsed, html)
        period = next(item[2] for item in result.criteria if item[1] == "Application period")
        self.assertIn("no exact future deadline is confirmed", period)


    def test_haw_kiel_deutschlandstipendium_keeps_entry_and_continuing_student_rules_distinct(self):
        parsed = ExtractedPage(
            title="HAW Kiel Deutschlandstipendium",
            description=None,
            provider_name="HAW Kiel",
        )
        html = """
        <html><body><main>
          <p>Anyone who is studying or intends to study at HAW Kiel within the standard period of study at the beginning of the funding period can apply.</p>
          <p>If you are about to start studying at HAW Kiel or have not yet completed a semester at HAW Kiel, you must have a grade of better than 2.0 in your university entrance qualification.</p>
          <p>All other students must have completed at least half of the ECTS per semester as stipulated in the respective curriculum of the degree program.</p>
          <p>Applicants must not have exceeded the standard period of study for their degree program at the start of the funding period.</p>
          <p>For Bachelor's graduates transferring to a Master's degree course, the grade of the degree qualifying for the Master's degree is decisive. Students must also prove that they are among the top 20% of the respective cohort.</p>
          <p>Applicants with certificates from foreign universities or schools: only the grade converted by uniassist for the German grading system is decisive.</p>
          <p>Applications can only be submitted via the online portal. The applicable application deadline is also stated there.</p>
          <p>Special achievements, awards and prizes from the last two years, previous professional activity, internships or voluntary services of a duration of at least six months.</p>
          <p>Current extracurricular commitment of at least one year.</p>
        </main></body></html>
        """
        result = _augment_haw_kiel_deutschlandstipendium(parsed, html)
        self.assertTrue(any(item[1] == "Study at HAW Kiel" for item in result.criteria))
        self.assertTrue(any(item[1] == "Entry qualification grade" and "better than 2.0" in item[2] for item in result.criteria))
        self.assertTrue(any(item[1] == "Study progress" and "half of the ECTS" in item[2] for item in result.criteria))
        self.assertTrue(any(item[1] == "Academic ranking evidence" and "top 20%" in item[2] for item in result.criteria))
        self.assertTrue(any(item[1] == "Foreign qualification grade conversion" for item in result.criteria))
        self.assertTrue(any(item[1] == "Application deadline" and "stated in that portal" in item[2] for item in result.criteria))
        self.assertTrue(any(item[0] == "selection_criteria" and "six months" in item[2] for item in result.criteria))
        self.assertTrue(all(result.criteria_sources[item] == HAW_KIEL_DEUTSCHLANDSTIPENDIUM_URL for item in result.criteria))

    def test_fu_berlin_deutschlandstipendium_captures_winter_only_and_acceptance_route(self):
        parsed = ExtractedPage(
            title="Freie Universität Berlin Deutschlandstipendium",
            description=None,
            provider_name="Freie Universität Berlin",
        )
        html = """
        <html><body><main>
          <p>The Deutschlandstipendium scholarship allows students at Freie Universität Berlin of all nations and all parts of society to apply.</p>
          <p>Requirements: enrollment at Freie Universität Berlin within the standard time to degree during the funding period or a letter of acceptance to start a degree program at Freie Universität Berlin.</p>
          <p>300 euros per month for a minimum of two semesters starting in October, extensions are possible.</p>
          <p>Scholarships are always awarded for the winter semester. It is not possible to start the scholarship program in the summer semester.</p>
          <p>Application period for the funding year 2026/2027: The application period ended.</p>
        </main></body></html>
        """
        result = _augment_fu_berlin_deutschlandstipendium(parsed, html)
        self.assertTrue(any(item[1] == "Study at Freie Universität Berlin" for item in result.criteria))
        self.assertTrue(any(item[1] == "International applicants" for item in result.criteria))
        self.assertTrue(any(item[1] == "Funding start" for item in result.criteria))
        self.assertTrue(any(item[1] == "Application period" and "next application deadline" in item[2] for item in result.criteria))
        self.assertTrue(any(item[1] == "Funding amount" and "€300 per month" in item[2] for item in result.criteria))
        self.assertTrue(all(result.criteria_sources[item] == FU_BERLIN_DEUTSCHLANDSTIPENDIUM_URL for item in result.criteria))


if __name__ == "__main__":
    unittest.main()
