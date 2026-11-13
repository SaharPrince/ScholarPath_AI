"""Conservative, evidence-linked matching of a student profile to scholarships.

Profile data is evaluated in memory and is never written to the scholarship database.
Unknown or unsupported criteria are surfaced as needing review, never guessed.
"""
from __future__ import annotations

import re
from typing import Any


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result(state: str, explanation: str) -> dict[str, str]:
    return {"status": state, "explanation": explanation}


def evaluate_criterion(criterion: dict[str, Any], profile: dict[str, Any]) -> dict[str, str]:
    """Return pass/fail/unknown for one mandatory criterion."""
    kind = (criterion.get("criterion_type") or "").strip().lower()
    label = (criterion.get("criterion_label") or "").strip()
    text = re.sub(r"\s+", " ", criterion.get("requirement_text") or "").strip()
    lower = f"{label} {text}".lower()

    # Germany-specific residence and apprenticeship conditions. These checks
    # work across source-specific criterion labels while preserving unknowns.
    if not criterion.get("is_mandatory", True):
        return _result("informational", "This is selection or programme information, not a mandatory eligibility check.")

    # Sensitive circumstances are not collected or inferred by this matcher.
    if re.search(
        r"(?i)financial(?:ly)?\s+(?:need|needy|disadvantaged|hardship)|"
        r"financial\s+(?:circumstances|situation|hardship)|household\s+income|"
        r"parent(?:s|al)?\s+income|baf[oö]g|income\s+assessment",
        lower,
    ):
        return _result(
            "unknown",
            "The provider assesses financial need separately. This matcher does not ask for income, family finances, or financial documents; review the official provider's confidential process.",
        )

    if re.search(
        r"(?i)\b(?:refugee|asylum\s+seeker|disabilit(?:y|ies)|disabled|"
        r"chronic\s+illness|religion|religious|denomination|muslim|christian|political\s+engagement|politisch(?:es|er|e)?\s+engagement|"
        r"protestant|catholic|gender|women|woman|female|single\s+parent|"
        r"minor\s+child(?:ren)?|caregiv(?:er|ing)|care\s+responsibilit(?:y|ies)|"
        r"family\s+responsibilit(?:y|ies)|social\s+democra(?:cy|tic)|political\s+(?:beliefs?|ideolog(?:y|ies)|alignment)|gesellschaftspolitisch|werte[n]?\s+der\s+sozialen\s+demokratie)\b",
        lower,
    ):
        return _result(
            "unknown",
            "The provider lists a personal, political, or sensitive circumstance for this opportunity. This matcher does not ask you to disclose it; review the official condition privately with the provider.",
        )

    # Named-university enrolment is distinct from enrolment in a country.
    source_text = f"{label} {text}"
    institution_match = re.search(
        r"(?:enrolled|registered|matriculated|students?)\s+(?:at|in)\s+(?:the\s+)?"
        r"([A-Z][A-Za-zÀ-ÿ0-9&.'-]*(?:\s+(?:of|the|and|[A-Z][A-Za-zÀ-ÿ0-9&.'-]*)){0,5})",
        source_text,
    )
    if not institution_match:
        institution_match = re.search(
            r"eingeschrieben\s+an\s+der\s+"
            r"([A-Z][A-Za-zÀ-ÿ0-9&.'-]*(?:\s+(?:of|the|and|[A-Z][A-Za-zÀ-ÿ0-9&.'-]*)){0,5})",
            source_text,
        )
    if institution_match:
        required_institution = institution_match.group(1).strip(" .,:;")
        if not re.fullmatch(
            r"(?i)(?:a|any|recognized|german|public|national)\s+(?:recognized\s+)?university(?:\s+in\s+germany)?",
            required_institution,
        ):
            def canonical_institution(value: str) -> str:
                normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
                aliases = {
                    "tu berlin": "technical university of berlin",
                    "technical university berlin": "technical university of berlin",
                    "university of wurzburg": "julius maximilians university of wurzburg",
                    "julius maximilians universitat wurzburg": "julius maximilians university of wurzburg",
                    "julius maximilians university wurzburg": "julius maximilians university of wurzburg",
                }
                return aliases.get(normalized, normalized)

            applicant_institution = canonical_institution(
                str(profile.get("current_university_name") or "")
            )
            required_normalized = canonical_institution(required_institution)
            enrolled_here = profile.get("currently_enrolled_at_current_university")
            if not applicant_institution:
                return _result("unknown", "If you wish, enter the name of your current university to check this institution-specific condition.")
            if enrolled_here is None:
                return _result("unknown", "Confirm whether you are currently enrolled at the university you entered.")
            if not enrolled_here:
                return _result("fail", "This opportunity requires current enrolment at the named university.")
            if required_normalized not in applicant_institution and applicant_institution not in required_normalized:
                return _result("fail", f"The published condition requires enrolment at {required_institution}.")
            return _result("pass", f"You confirmed current enrolment at {required_institution}.")


    if re.search(r"(?:not have been in germany for more than|have not been in germany for more than|not been in germany for more than|no more than)\s*15\s*months?|(?:nicht länger als|nicht mehr als|höchstens)\s*15\s*monate?", lower):
        months = _number(profile.get("months_in_germany"))
        if months is None:
            return _result("unknown", "Add how many months you have been in Germany to check this residence-duration rule.")
        if months <= 15:
            return _result("pass", f"You reported {months:g} months in Germany; the published maximum is 15 months.")
        if re.search(r"\b(?:unless|exception|except|already studied|previously studied|prepar\w*|ausnahme|bereits in deutschland studiert|studienvorbereitung)\b", lower):
            exception = profile.get("residence_duration_exception")
            if exception == "none":
                return _result("fail", "You reported more than 15 months in Germany and indicated that neither published exception applies.")
            if exception not in {"prior_study", "study_preparation"}:
                return _result("unknown", "You reported more than 15 months in Germany. Check whether the provider's prior-study or study-preparation exception applies.")
            return _result("pass", "You reported a provider-listed exception to the 15-month residence rule; confirm the evidence directly with the foundation.")
        return _result("fail", f"You reported {months:g} months in Germany; the published maximum is 15 months and no exception is stated in this criterion.")

    if ("residence permit" in lower or "aufenthaltserlaubnis" in lower) and re.search(r"(?:study|studies|studying|studienzweck|studium)", lower):
        permit = profile.get("german_residence_permit")
        if permit not in {"study", "other", "none"}:
            return _result("unknown", "Select whether your German residence permit is for study purposes.")
        return _result("pass" if permit == "study" else "fail",
                       "Your German residence permit is for study purposes." if permit == "study"
                       else "This programme requires a German residence permit for study purposes.")

    if re.search(r"(?:already (?:be )?studying in germany|currently enrolled.*germany|an einer deutschen hochschule eingeschrieben|bereits an einer deutschen hochschule studieren)", lower):
        enrolled = profile.get("currently_enrolled_in_germany")
        if enrolled is None:
            return _result("unknown", "Confirm whether you are currently enrolled at a German university.")
        return _result("pass" if enrolled else "fail",
                       "You confirmed current enrolment in Germany." if enrolled
                       else "This programme requires current enrolment at a German university.")

    timing_matched = False
    semester_minimum = re.search(
        r"\b(?:at least|minimum of)\s*(\d+|one|two|three|four|five|six)\s+(?:full\s+)?semesters?\b.{0,100}\b(?:remaining|left)\b|"
        r"\b(\d+|one|two|three|four|five|six)\s+(?:full\s+)?(?:remaining\s+)?semesters?\b.{0,100}\b(?:remaining|left|before|until|prior to|complete|completion|finish|end)\b|"
        r"\b(?:remaining|left)\s+(?:at least\s+)?(\d+|one|two|three|four|five|six)\s+semesters?\b|"
        r"mindestens\s+(\d+|ein|eine|zwei|drei|vier|fünf|sechs)\s+(?:volle\s+)?semester?(?:\s+der\s+regelstudienzeit)?\s+(?:müssen\s+)?verbleib",
        lower,
    )
    if semester_minimum:
        raw_minimum = next(group for group in semester_minimum.groups() if group is not None)
        semester_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "ein": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6,
        }
        minimum_semesters = int(raw_minimum) if raw_minimum.isdigit() else semester_words[raw_minimum]
        remaining = _number(profile.get("remaining_semesters_in_program"))
        if remaining is None:
            return _result("unknown", "Add how many semesters remain in your current study programme to check this requirement.")
        if remaining < minimum_semesters:
            return _result("fail", f"You reported {remaining:g} semesters remaining; at least {minimum_semesters} are required.")
        timing_matched = True

    if re.search(
        r"\b(?:at least|minimum of)\s+(?:half|50\s*%)\s+(?:of\s+)?(?:the\s+)?(?:standard|regular)\s+(?:study\s+)?(?:period|duration)\s+(?:must\s+)?remain|"
        r"mindestens\s+die\s+h[aä]lfte\s+der\s+regelstudienzeit\s+(?:muss\s+)?verbleib",
        lower,
    ):
        remaining = _number(profile.get("remaining_semesters_in_program"))
        standard = _number(profile.get("standard_programme_semesters"))
        if remaining is None or standard is None or standard <= 0:
            return _result("unknown", "Add the standard total and remaining semesters of your programme to check the half-duration rule.")
        minimum = standard / 2
        if remaining < minimum:
            return _result("fail", f"You reported {remaining:g} of {standard:g} standard semesters remaining; at least half ({minimum:g}) must remain.")
        timing_matched = True

    if re.search(
        r"\b(?:three|3)\s+semesters?\s+before\s+(?:the\s+)?(?:end|completion)\s+of\s+(?:the\s+)?(?:standard|regular)\s+(?:study\s+)?(?:period|duration)|"
        r"\b(?:until|up to|no later than)\s+(?:three|3)\s+semesters?\s+before\s+(?:the\s+)?(?:end|completion)\b|"
        r"\bbis\s+drei\s+semester\s+vor\s+ende\s+der\s+regelstudienzeit\b",
        lower,
    ):
        remaining = _number(profile.get("remaining_semesters_in_program"))
        if remaining is None:
            return _result("unknown", "Add how many semesters remain in your standard study period to check this application window.")
        if remaining < 3:
            return _result("fail", f"You reported {remaining:g} semesters remaining; this application window requires at least 3 semesters before the standard end.")
        timing_matched = True

    semester = _number(profile.get("current_semester_in_program"))
    if re.search(r"\bafter\s+(?:the\s+)?first\s+semester\b|\bnach\s+dem\s+ersten\s+semester\b", lower):
        if semester is None:
            return _result("unknown", "Add your current semester to check whether you have completed the first semester.")
        if semester < 2:
            return _result("fail", "This application window opens after completion of the first semester.")
        timing_matched = True
    if re.search(
        r"\b(?:before|prior to)\s+(?:or\s+at\s+)?(?:the\s+)?(?:beginning|start)\s+of\s+(?:the\s+)?first\s+semester\b|"
        r"\bby\s+the\s+beginning\s+of\s+the\s+first\s+semester\b|"
        r"\bvor\s+oder\s+zu\s+beginn\s+des\s+ersten\s+(?:hochschul)?semesters\b",
        lower,
    ):
        stage = profile.get("first_semester_timing")
        if stage not in {"not_started", "at_beginning", "after_beginning", "later_semester"}:
            return _result("unknown", "Confirm whether the Master's programme has not started, is at the beginning of semester 1, or is already underway.")
        if stage in {"after_beginning", "later_semester"}:
            return _result("fail", "This application window is limited to before or the beginning of the first semester.")
        timing_matched = True
    if re.search(r"\bafter\s+(?:the\s+)?fourth\s+semester\b|\bnach\s+dem\s+vierten\s+semester\b", lower) and re.search(
        r"\b(?:until|through|by)\s+(?:the\s+)?end\s+of\s+(?:the\s+)?sixth\s+semester\b|\bbis\s+(?:zum\s+)?ende\s+des\s+sechsten\s+semesters\b",
        lower,
    ):
        if semester is None:
            return _result("unknown", "Add your current semester to check the medical-study application window.")
        if not 5 <= semester <= 6:
            return _result("fail", "This medical-study application window is after semester 4 and through the end of semester 6.")
        timing_matched = True

    if timing_matched:
        return _result("pass", "Your reported study timing meets the published application window.")

    if re.search(r"(?:at least|minimum of|mindestens)\s*(?:6|six|sechs)\s*months?.{0,80}(?:remaining|left|rest|verbleib)", lower):
        remaining = _number(profile.get("months_remaining_in_program"))
        if remaining is None:
            return _result("unknown", "Add how many months remain in your current study programme.")
        return _result("pass" if remaining >= 6 else "fail",
                       f"You reported {remaining:g} months remaining; at least 6 are required.")

    if re.search(
        r"(?:at the beginning of the first and no later than the beginning of the second|"
        r"first and.*second year|spätestens am anfang des zweiten|"
        r"am anfang des ersten.*ausbildungsjahr)",
        lower,
    ):
        year = _number(profile.get("apprenticeship_year"))
        if year is None:
            return _result("unknown", "Add your current apprenticeship year to check this application window.")
        if year < 1 or year > 2:
            return _result("fail", "This FES application window closes at the beginning of the second apprenticeship year.")
        if year == 1:
            return _result("pass", "You reported that you are in the first apprenticeship year, within the published application window.")
        stage = profile.get("apprenticeship_second_year_stage")
        if stage == "beginning":
            return _result("pass", "You reported that you are at the beginning of the second apprenticeship year.")
        if stage == "later":
            return _result("fail", "The FES application window closes at the beginning of the second apprenticeship year.")
        return _result("unknown", "You reported the second apprenticeship year. Confirm whether you are still at its beginning.")

    if re.search(
        r"(?:state[- ]recognized|state recognized|staatlich anerkannt|anerkannt(?:e|en|er)?\s+(?:durch|nach)\s+(?:das?\s+)?(?:bbig|hwo)|"
        r"bbig|hwo|bundesgesetzlich geregelt.{0,80}gesundheitswesen|landesrechtlich geregelt)",
        lower,
    ) and re.search(r"(?:training|occupation|ausbildung|ausbildungsberuf|berufsausbildung|bbig|hwo)", lower):
        recognized = profile.get("recognized_apprenticeship")
        if recognized is None:
            return _result("unknown", "Confirm whether your apprenticeship is recognised under the training framework listed by the provider.")
        return _result("pass" if recognized else "fail",
                       "Your apprenticeship is marked as recognised under the provider's listed framework." if recognized
                       else "This award requires an apprenticeship recognised under the provider's listed framework.")

    if re.search(r"(?:training contract|contract for training|ausbildungsvertrag|written confirmation.*training place)", lower):
        contract = profile.get("has_training_contract")
        if contract is None:
            return _result("unknown", "Confirm whether you have an apprenticeship contract or written training-place offer.")
        return _result("pass" if contract else "fail",
                       "You have a training contract or written offer." if contract
                       else "This award requires an apprenticeship contract or written offer.")

        return _result("informational", "This is selection or programme information, not a mandatory eligibility check.")

    if kind == "nationality":
        required_pakistani = any(x in lower for x in ("pakistani", "pakistan", "ajk", "azad jammu"))
        if required_pakistani:
            nationality = (profile.get("nationality") or "").lower()
            residence = (profile.get("residence_country") or "").lower()
            if not nationality:
                return _result("unknown", "Add your nationality to check this requirement.")
            if nationality not in {"pakistani", "pakistan", "pakistani national"}:
                return _result("fail", "The published requirement is limited to Pakistani/AJ&K applicants.")
            if any(x in lower for x in ("permanent resident", "permanent residency", "resident of")):
                if not residence:
                    return _result("unknown", "Add your country of permanent residence.")
                if residence not in {"pakistan", "pakistani"}:
                    return _result("fail", "The published requirement also requires permanent residence in Pakistan/AJ&K.")
            if "dual national" in lower or "dual nationals" in lower:
                dual = profile.get("dual_national")
                if dual is None:
                    return _result("unknown", "Tell us whether you hold another nationality.")
                if dual:
                    return _result("fail", "The official criteria exclude dual nationals.")
            if "domicile" in lower or "local certificate" in lower or "province" in lower:
                region_aliases = {
                    "Punjab": ("punjab",),
                    "Sindh": ("sindh",),
                    "Khyber Pakhtunkhwa": ("khyber pakhtunkhwa", "kpk", "k.p."),
                    "Balochistan": ("balochistan",),
                    "Islamabad Capital Territory": ("islamabad", "ict"),
                    "Azad Jammu and Kashmir": ("azad jammu", "ajk"),
                    "Gilgit-Baltistan": ("gilgit-baltistan", "gilgit baltistan", "gb"),
                }
                required_regions = [name for name, aliases in region_aliases.items()
                                    if any(alias in lower for alias in aliases)]
                domicile = (profile.get("domicile_region") or "").strip().lower()
                if len(required_regions) != 1:
                    return _result("unknown", "The official domicile rule lists multiple or unclear regions; it needs a closer check.")
                if not domicile:
                    return _result("unknown", "Choose your province or region of domicile to check this scholarship.")
                if domicile != required_regions[0].lower():
                    return _result("fail", f"This scholarship requires domicile in {required_regions[0]}.")
            return _result("pass", "Your nationality and any supplied domicile details meet the published rule.")
        if "domicile" in lower or "local certificate" in lower or "province" in lower:
            region_aliases = {
                "Punjab": ("punjab",),
                "Sindh": ("sindh",),
                "Khyber Pakhtunkhwa": ("khyber pakhtunkhwa", "kpk", "k.p."),
                "Balochistan": ("balochistan",),
                "Islamabad Capital Territory": ("islamabad", "ict"),
                "Azad Jammu and Kashmir": ("azad jammu", "ajk"),
                "Gilgit-Baltistan": ("gilgit-baltistan", "gilgit baltistan", "gb"),
            }
            required_regions = [name for name, aliases in region_aliases.items()
                                if any(alias in lower for alias in aliases)]
            domicile = (profile.get("domicile_region") or "").strip().lower()
            if len(required_regions) != 1:
                return _result("unknown", "The official domicile rule lists multiple or unclear regions; it needs a closer check.")
            if not domicile:
                return _result("unknown", "Choose your province or region of domicile to check this scholarship.")
            if domicile != required_regions[0].lower():
                return _result("fail", f"This scholarship requires domicile in {required_regions[0]}.")
            return _result("pass", f"Your domicile in {required_regions[0]} meets the published regional rule.")
        return _result("unknown", "This nationality rule needs a specific check against the official wording.")

    if kind == "language_requirements":
        language = (profile.get("german_language_level") or "").strip().upper()
        levels = {"NONE": 0, "A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
        required = re.search(r"\b(A1|A2|B1|B2|C1|C2)\b", text, re.IGNORECASE)
        if not language or language not in levels:
            return _result("unknown", "Select your German language level to check this requirement.")
        if not required:
            if any(term in lower for term in (
                "german language", "german-language", "deutschkenntnisse",
                "deutsche sprachkenntnisse", "gute deutsche sprachkenntnisse",
            )):
                return _result("unknown", "The source requires German skills but does not state a measurable minimum level; confirm the provider's standard.")
            return _result("unknown", "The required language or proficiency level needs manual review.")
        minimum = levels[required.group(1).upper()]
        return _result("pass" if levels[language] >= minimum else "fail",
                       f"Your German level ({language}) {'meets' if levels[language] >= minimum else 'is below'} the published minimum ({required.group(1).upper()}).")

    if kind == "age_limit":
        if "no upper age limit" in lower or "no age limit" in lower:
            return _result("informational", "The source explicitly states there is no upper age limit.")
        if re.search(r"(?i)\b(?:older than|over)\s+\d+\b", lower) and re.search(
            r"(?i)\b(?:special|additional)\s+(?:application|request|form)\b", lower
        ):
            return _result(
                "informational",
                "The age condition calls for an additional application or special request; it is not an automatic age-based rejection. Review the provider's instructions.",
            )
        if re.search(r"(?i)\b(?:older than|over)\s+\d+\b", lower) and re.search(
            r"(?i)\b(?:can|may)\s+i\s+apply\b.{0,180}\b(?:yes|you can|you may)\b|\b(?:can|may)\s+apply\b|\beligible to apply\b", lower
        ):
            return _result(
                "informational",
                "The provider explicitly allows applicants above the stated age to apply in the described circumstances. Review the provider's explanation requirements; do not treat this wording as an automatic age-based rejection.",
            )
        age = _number(profile.get("age"))
        if age is None:
            return _result("unknown", "Add your age to check the published age limit.")
        if re.search(r"(?i)\b(?:exceptions?|ausnahmen?)\b", lower):
            limits = [int(x) for x in re.findall(r"\b(\d{2})\s*(?:years?|yrs?|jahre?)\b", lower)]
            if limits and age >= min(limits):
                return _result(
                    "unknown",
                    "You are at or above the stated age guideline, but the provider describes exceptions. Review those exceptions privately with the provider; no family or personal-circumstance details are requested here.",
                )
        range_match = re.search(r"\b(\d{2})\s*(?:-|–|to)\s*(\d{2})\s*(?:years?|yrs?)?\b", lower)
        if range_match:
            minimum, maximum = (int(range_match.group(1)), int(range_match.group(2)))
            if minimum <= age <= maximum:
                return _result("pass", f"Your age ({int(age)}) is within the published range of {minimum}–{maximum}.")
            return _result("fail", f"Your age ({int(age)}) is outside the published range of {minimum}–{maximum}.")

        limits = [int(x) for x in re.findall(r"\b(\d{2})\s*(?:years?|yrs?)\b", lower)]
        if not limits:
            return _result("unknown", "The age wording needs manual review; no numeric limit was safely identified.")
        limit = min(limits) if len(limits) == 1 else min(limits)
        if any(word in lower for word in ("minimum age", "at least", "not younger than", "minimum of")):
            ok = age >= limit
            return _result("pass" if ok else "fail",
                           f"Your age ({int(age)}) {'meets' if ok else 'is below'} the published minimum of {limit}.")
        qualified = any(profile.get(k) is True for k in (
            "regular_government_employee", "public_university_faculty", "approved_rd_researcher"
        ))
        flags = ("regular_government_employee", "public_university_faculty", "approved_rd_researcher")
        if "all other cases" in lower and qualified:
            return _result("informational", "This lower age limit applies to other applicants; your profile indicates a specified public-sector category.")
        if "all other cases" in lower and not qualified and all(profile.get(k) is None for k in flags):
            return _result("unknown", "Confirm whether you belong to one of the specified public-sector employment categories before applying the general age limit.")
        if "regular government" in lower or "public sector" in lower or "approved r&d" in lower:
            if not qualified:
                if all(profile.get(k) is not False for k in flags):
                    return _result("unknown", "Confirm whether you are a regular government employee, public university faculty member, or approved R&D researcher.")
                return _result("informational", "The higher public-sector age limit does not apply to the employment category you selected.")
        ok = age <= limit
        return _result("pass" if ok else "fail",
                       f"Your age ({int(age)}) is within the published maximum of {limit}." if ok
                       else f"Your age ({int(age)}) is above the published maximum of {limit}.")

    if kind == "ineligibility":
        if "other scholarship" in lower or "other scholarship" in text.lower():
            value = profile.get("receiving_other_scholarship")
            if value is None:
                return _result("unknown", "Tell us whether you are currently receiving another scholarship.")
            return _result("fail" if value else "pass",
                           "The source excludes applicants receiving another scholarship." if value
                           else "You indicated that you are not receiving another scholarship.")
        if "phd" in lower and ("having phd" in lower or "already hold" in lower or "phd degree" in lower):
            value = profile.get("has_phd")
            if value is None:
                return _result("unknown", "Tell us whether you already hold a PhD.")
            return _result("fail" if value else "pass",
                           "The source excludes applicants who already hold a PhD." if value
                           else "You indicated that you do not already hold a PhD.")
        return _result("unknown", "This exclusion needs a specific answer or manual review.")

    if re.search(r"(?:doctoral|phd|promotion|promovierende|promotionsstudium)", lower) and re.search(r"(?:admission|admitted|zulassung|zugelassen)", lower):
        admitted = profile.get("doctoral_admission_confirmed")
        if admitted is None:
            return _result("unknown", "Confirm whether you have formal admission to the doctoral programme.")
        return _result("pass" if admitted else "fail",
                       "You confirmed formal admission to doctoral studies." if admitted
                       else "This programme requires formal admission to doctoral studies.")

    if kind == "doctoral_admission":
        admitted = profile.get("doctoral_admission_confirmed")
        if admitted is None:
            return _result("unknown", "Confirm whether a university or doctoral committee has formally admitted you to doctoral studies.")
        return _result(
            "pass" if admitted else "fail",
            "You confirmed formal admission to doctoral studies." if admitted
            else "This scholarship requires formal admission to doctoral studies before applying.",
        )

    if kind == "doctoral_project_stage":
        final_phase = profile.get("doctoral_project_final_phase")
        if final_phase is None:
            return _result("unknown", "Confirm whether your doctoral project is already in its final phase.")
        return _result(
            "fail" if final_phase else "pass",
            "The provider excludes doctoral projects already in their final phase." if final_phase
            else "You indicated that your doctoral project is not yet in its final phase.",
        )

    if kind in {"academic_requirements", "study_level", "category_i_eligibility", "category_ii_eligibility"}:
        target = (profile.get("target_study_level") or "").lower()
        if re.search(r"\b(?:for|starting|admission to|completed their)\s+(?:a\s+)?master(?:'s)?\b", lower) or "master scholarship" in lower:
            if not target:
                return _result("unknown", "Choose your intended study level to check this Master's-specific requirement.")
            if target in {"bachelors", "bachelor", "undergraduate"}:
                return _result("fail", "This scholarship criterion is for Master's applicants, not undergraduate study.")
            if target not in {"master", "masters", "master's"}:
                return _result("informational", "This rule applies to Master's applicants, not your selected study level.")
        if re.search(r"\b(?:for|starting|admission to|completed their)\s+(?:a\s+)?(?:phd|doctoral)\b", lower) or "phd scholarship" in lower:
            if not target:
                return _result("unknown", "Choose your intended study level to check this PhD-specific requirement.")
            if target in {"bachelors", "bachelor", "undergraduate"}:
                return _result("fail", "This scholarship criterion is for PhD applicants, not undergraduate study.")
            if target not in {"phd", "doctoral"}:
                return _result("informational", "This rule applies to PhD applicants, not your selected study level.")

        if re.search(r"\b(?:not eligible|not funded|cannot be funded|excluded|not supported)\b", lower):
            excluded_level = None
            if re.search(r"\b(?:bachelor(?:'s)?|undergraduate|grundstudium)\b", lower):
                excluded_level = "bachelors"
            elif re.search(r"\b(?:master(?:'s)?|postgraduate)\b", lower):
                excluded_level = "master"
            if excluded_level:
                if not target:
                    return _result("unknown", "Choose your intended study level to check this programme-level exclusion.")
                aliases = {
                    "bachelors": {"bachelors", "bachelor", "undergraduate"},
                    "master": {"master", "masters", "master's", "postgraduate"},
                }
                if target in aliases[excluded_level]:
                    return _result("fail", f"This programme explicitly excludes {excluded_level} study.")
                return _result("informational", f"The exclusion applies to {excluded_level} study, not your selected study level.")

        if re.search(r"\b(?:completed|finished)\s+(?:a\s+)?bachelor(?:'s)?\s+degree\b|\b(?:abgeschlossen(?:e[snr]?)?\s+)?bachelor(?:-?studium|-?abschluss)\b", lower):
            current_level = (profile.get("current_education_level") or "").lower()
            if current_level not in {"bachelors", "masters", "phd"}:
                if not current_level:
                    return _result("unknown", "Choose your highest completed education level to check the completed-Bachelor requirement.")
                return _result("fail", "This programme requires a completed Bachelor's degree.")
            return _result("pass", "Your reported completed education level includes a Bachelor's degree.")

        if "university degree" in lower or "university qualification" in lower:
            current_level = (profile.get("current_education_level") or "").lower()
            level_ranks = {"below_matric": 0, "matric": 1, "intermediate": 2, "bachelors": 3, "masters": 4, "phd": 5}
            rank = level_ranks.get(current_level)
            if rank is None:
                return _result("unknown", "Choose your highest completed education level to check the university-degree requirement.")
            if rank < level_ranks["bachelors"]:
                return _result("fail", "This requirement needs a completed university degree.")
            if "professional experience" in lower or "work experience" in lower:
                years = _number(profile.get("professional_experience_years"))
                if years is None:
                    return _result("unknown", "Add your relevant professional experience in years to check this requirement.")
                if years <= 0:
                    return _result("fail", "The source requires professional experience after your university degree.")
            return _result("pass", "Your completed university degree meets this qualification requirement.")

        if "professional experience" in lower or "work experience" in lower:
            years = _number(profile.get("professional_experience_years"))
            if years is None:
                return _result("unknown", "Add your relevant professional experience in years to check this requirement.")
            minimum_match = re.search(r"(?:at least|minimum of|minimum)\s*(\d+(?:\.\d+)?)\s*years?", lower)
            minimum = float(minimum_match.group(1)) if minimum_match else 0.01
            return _result("pass" if years >= minimum else "fail",
                           f"You reported {years:g} years of experience; the published minimum is {minimum:g}."
                           if minimum_match else
                           ("Your reported professional experience meets the source's experience condition."
                            if years > 0 else "The source requires professional experience."))

        # Match school and college entry requirements against the student's latest completed level.
        current_level = (profile.get("current_education_level") or "").lower()
        level_ranks = {"below_matric": 0, "matric": 1, "intermediate": 2, "bachelors": 3, "masters": 4, "phd": 5}
        current_rank = level_ranks.get(current_level)
        target = (profile.get("target_study_level") or "").lower()
        target_aliases = {
            "matric": {"matric", "ssc", "secondary"},
            "intermediate": {"intermediate", "hssc", "college", "fa", "f.a.", "fsc", "f.sc.", "ics", "i.com"},
            "bachelors": {"bachelor", "bachelors", "undergraduate", "undergraduate degree"},
            "master": {"master", "masters", "postgraduate", "ms", "mphil"},
            "phd": {"phd", "doctoral", "doctorate"},
        }
        target_key = next((key for key, aliases in target_aliases.items()
                           if target in aliases), target)
        required_level = None
        completed_qualification = re.search(r"\b(pass(?:ed)?|complet(?:e|ed)|qualification|certificate|marks in)\b", lower)
        if completed_qualification and re.search(r"\b(matric(?:ulation)?|ssc|secondary school certificate)\b", lower):
            required_level = "matric"
        elif completed_qualification and re.search(r"\b(intermediate|hssc|higher secondary|f\.?a\.?|f\.?sc\.?|i\.?cs|i\.?com)\b", lower):
            required_level = "intermediate"
        if required_level:
            if current_rank is None:
                return _result("unknown", "Choose the highest education level you have completed (Matric, Intermediate, Bachelor's or higher).")
            required_rank = level_ranks[required_level]
            if current_rank < required_rank:
                return _result("fail", f"This opportunity requires {required_level.title()} to be completed; your highest completed level is {current_level.replace('_', ' ').title()}.")
            if not any(term in lower for term in ("marks", "aggregate", "percentage", "percent")):
                return _result("pass", f"Your completed {required_level.title()} qualification meets this education-level requirement.")
        if re.search(r"\b(for|admission to|apply for)\s+intermediate\b", lower):
            if not target:
                return _result("unknown", "Choose what you plan to study next to check this Intermediate opportunity.")
            if target_key != "intermediate":
                return _result("informational", "This opportunity is for Intermediate study, not your selected next study level.")
        if re.search(r"\b(for|admission to|apply for)\s+(?:matric|ssc)\b", lower):
            if not target:
                return _result("unknown", "Choose what you plan to study next to check this Matric opportunity.")
            if target_key != "matric":
                return _result("informational", "This opportunity is for Matric study, not your selected next study level.")

        # Compare clearly stated academic marks thresholds without treating GPA,
        # division, entry-test scores, or unrelated percentages as equivalent.
        if ("hat" not in lower and "gre" not in lower
                and any(term in lower for term in ("marks", "aggregate", "percentage", "percent"))):
            percentage_match = re.search(
                r"(?:minimum|at least|not less than|above|aggregate of|score of)\s*(\d{1,3}(?:\.\d+)?)\s*%?",
                lower
            )
            if percentage_match and ("%" in lower or "percent" in lower or "marks" in lower):
                percentage = _number(profile.get("academic_percentage"))
                minimum_percentage = float(percentage_match.group(1))
                if percentage is None:
                    return _result("unknown", "Add the percentage marks from your latest completed class to check this academic requirement.")
                if percentage < minimum_percentage:
                    return _result("fail", f"Your reported marks ({percentage:g}%) are below the published minimum of {minimum_percentage:g}%.")
                return _result("pass", f"Your reported marks ({percentage:g}%) meet the published minimum of {minimum_percentage:g}%.")

        if "relevant field" in lower or "relevant subject" in lower:
            return _result("unknown", "Your degree subject must match the scholarship's approved field of study; compare it with the official subject list.")

        if "accepted hat categories" in label.lower() or ("hat-i" in lower and "hat-iv" in lower):
            category = (profile.get("hat_category") or "").upper()
            if not category:
                return _result("unknown", "Select your HAT category (I, II, III or IV).")
            if category not in {"HAT-I", "HAT-II", "HAT-III", "HAT-IV"}:
                return _result("fail", "The source accepts only HAT-I, HAT-II, HAT-III or HAT-IV.")
            return _result("pass", "Your HAT category is one of the categories accepted by the source.")

        if "hat" in lower and "gre" in lower and (" or " in lower or "/" in lower):
            hat = _number(profile.get("hat_score"))
            gre = _number(profile.get("gre_score"))
            hat_ok = hat is not None and hat >= 60
            gre_ok = gre is not None and gre >= 300
            if hat_ok or gre_ok:
                return _result("pass", "At least one accepted test score meets the published GRE 300 / HEC-HAT 60% alternative.")
            if hat is None and gre is None:
                return _result("unknown", "Add your GRE or HEC-HAT score to check this alternative requirement.")
            return _result("fail", "Neither supplied test score meets the published GRE 300 / HEC-HAT 60% alternative.")

        if "hat" in lower and re.search(r"\b(?:minimum|min(?:imum)? score|score of)\s*(?:of\s*)?\d{1,3}", lower):
            score = _number(profile.get("hat_score"))
            if score is None:
                return _result("unknown", "Add your HAT score to check this requirement.")
            match = re.search(r"\b(?:minimum|min(?:imum)? score|score of)\s*(?:of\s*)?(\d{1,3})", lower)
            minimum = float(match.group(1)) if match else 60.0
            return _result("pass" if score >= minimum else "fail",
                           f"Your HAT score is {score:g}; the stated minimum is {minimum:g}.")

        if "gre" in lower and re.search(r"\b300\b", lower):
            score = _number(profile.get("gre_score"))
            if score is None:
                return _result("unknown", "Add your GRE score to check this requirement.")
            return _result("pass" if score >= 300 else "fail",
                           f"Your GRE score is {score:g}; the stated minimum is 300.")

        years_match = re.search(r"\b(16|17|18)\s*(?:/\s*(17|18)\s*)?years?\b", lower)
        if years_match and ("degree" in lower or "education" in lower or "bachelor" in lower or "master" in lower):
            years = _number(profile.get("years_of_education"))
            if years is None:
                return _result("unknown", "Add the total years of completed higher education.")
            required = [int(x) for x in years_match.groups() if x]
            minimum = min(required)
            return _result("pass" if years >= minimum else "fail",
                           f"You reported {years:g} years of education; this criterion requires {minimum} or more.")

        if "first division" in lower or "second division" in lower or "third division" in lower:
            division = (profile.get("latest_degree_division") or "").lower()
            if not division:
                return _result("unknown", "Select the division/class of your latest completed degree.")
            if division in {"other", "gpa", "cgpa", "percentage", "unknown"}:
                return _result("unknown", "Your grading system needs comparison with the scholarship's official division-equivalence rules.")
            if "not have a second/third" in lower or "not have second" in lower:
                if division in {"second", "third", "2nd", "3rd"}:
                    return _result("fail", "The source excludes a Second/Third Division in the latest degree.")
                ok = division in {"first", "1st"}
            elif "first division" in lower:
                ok = division in {"first", "1st"}
            else:
                return _result("unknown", "This academic division rule needs manual review.")
            return _result("pass" if ok else "fail",
                           "Your reported degree division meets this rule." if ok
                           else "Your reported degree division does not meet this rule.")

        if "top 50" in lower or "qs 1–50" in lower or "qs 1-50" in lower:
            rank = _number(profile.get("university_qs_rank"))
            admitted = profile.get("admission_confirmed")
            if rank is None or admitted is None:
                return _result("unknown", "Add your university's QS rank and confirm whether you have admission.")
            ok = rank <= 50 and admitted
            return _result("pass" if ok else "fail",
                           "Your admission and university rank meet the top-50 rule." if ok
                           else "This category requires confirmed admission to a QS top-50 university.")
        if "top 51-100" in lower or "top 51–100" in lower or "51-100" in lower or "51–100" in lower:
            rank = _number(profile.get("university_qs_rank"))
            admitted = profile.get("admission_confirmed")
            if rank is None or admitted is None:
                return _result("unknown", "Add your university's QS rank and confirm whether you have admission.")
            ok = 51 <= rank <= 100 and admitted
            return _result("pass" if ok else "fail",
                           "Your admission and university rank meet the QS 51–100 rule." if ok
                           else "This category requires confirmed admission to a QS 51–100 university.")

        if "phd" in lower and ("already hold" in lower or "phd degree" in lower):
            value = profile.get("has_phd")
            if value is None:
                return _result("unknown", "Tell us whether you already hold a PhD.")
            return _result("fail" if value else "pass",
                           "You already hold a PhD." if value else "You do not already hold a PhD.")

        return _result("unknown", "This academic requirement is shown for transparency but needs a specific check.")

    if kind in {"required_documents", "application_requirements"}:
        return _result("informational", "Application preparation item: review this requirement before applying. It is not treated as an applicant-eligibility failure.")

    return _result("unknown", "This requirement is preserved from the source but is not yet safe to automate.")


def match_scholarship(scholarship: dict[str, Any], criteria: list[dict[str, Any]],
                      profile: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for criterion in criteria:
        outcome = evaluate_criterion(criterion, profile)
        checks.append({
            "criterion_id": criterion.get("id"),
            "criterion_type": criterion.get("criterion_type"),
            "criterion_label": criterion.get("criterion_label"),
            "requirement_text": criterion.get("requirement_text"),
            "evidence_url": criterion.get("evidence_url"),
            **outcome,
        })

    # Category I and II are alternative routes, not simultaneous conditions.
    category_checks = [c for c in checks if c["criterion_type"] in {
        "category_i_eligibility", "category_ii_eligibility"
    }]
    if any(c["status"] == "pass" for c in category_checks):
        # Category I and II are alternative eligibility routes. Once one route
        # is positively satisfied, an unknown or failed check in the other
        # route must not block the overall result.
        for item in category_checks:
            if item["status"] != "pass":
                item["status"] = "informational"
                item["explanation"] = "This is an alternative scholarship category; another category's admission rule is met."

    mandatory = [c for c in checks if c["status"] != "informational"]
    if not mandatory:
        checks.append({
            "criterion_id": None,
            "criterion_type": "review",
            "criterion_label": "Eligibility criteria unavailable",
            "requirement_text": "No mandatory structured criteria are recorded for this scholarship.",
            "evidence_url": scholarship.get("source_url"),
            "status": "unknown",
            "explanation": "We cannot safely mark this scholarship as eligible without structured mandatory criteria.",
        })
        mandatory = [checks[-1]]
    failed = [c for c in mandatory if c["status"] == "fail"]
    unknown = [c for c in mandatory if c["status"] == "unknown"]
    if failed:
        status = "not_eligible"
    elif unknown:
        status = "needs_more_information"
    else:
        status = "likely_eligible"

    return {
        "id": scholarship["id"],
        "title": scholarship["title"],
        "provider_name": scholarship.get("provider_name"),
        "study_destination": scholarship.get("study_destination") or scholarship.get("country"),
        "funding_summary": scholarship.get("funding_summary"),
        "deadline_text": scholarship.get("deadline_text"),
        "deadline_date": scholarship.get("deadline_date"),
        "application_status": scholarship.get("application_status", "unknown"),
        "verification_status": scholarship.get("status", "unverified"),
        "source_name": scholarship.get("source_name"),
        "source_url": scholarship.get("source_url"),
        "application_url": scholarship.get("application_url"),
        "match_status": status,
        "checks_passed": sum(c["status"] == "pass" for c in checks),
        "checks_failed": len(failed),
        "checks_unknown": len(unknown),
        "checks": checks,
    }


def _target_level_mismatch(scholarship: dict[str, Any], criteria: list[dict[str, Any]], profile: dict[str, Any]) -> str | None:
    """Return a clear mismatch reason when an award is explicitly for another study level.

    This deliberately filters only explicit level-specific opportunities. Generic
    awards and unclear criteria remain visible as 'needs more information'.
    """
    target_raw = (profile.get("target_study_level") or "").strip().lower()
    target = re.sub(r"[^a-z0-9]+", " ", target_raw).strip()
    target_aliases = {
        "matric": {"matric", "ssc", "secondary"},
        "intermediate": {"intermediate", "hssc", "college", "fa", "f.a.", "fsc", "f.sc.", "ics", "i.com"},
        "bachelors": {"bachelor", "bachelors", "bachelor's", "undergraduate", "undergraduate degree", "bs", "b.s."},
        "master": {"master", "masters", "master's", "postgraduate", "ms", "mphil", "m.phil"},
        "phd": {"phd", "doctoral", "doctorate"},
        "vocational_training": {"vocational training", "ausbildung", "apprenticeship", "vocational"},
    }
    target_key = next(
        (
            key for key, aliases in target_aliases.items()
            if any(
                re.search(rf"\b{re.escape(re.sub(r'[^a-z0-9]+', ' ', alias).strip())}\b", target)
                for alias in aliases
            )
        ),
        target,
    )
    if target_key not in {"matric", "intermediate", "bachelors", "master", "phd", "vocational_training"}:
        return None

    title = (scholarship.get("title") or "").lower()
    criteria_text = " ".join(
        f"{item.get('criterion_label') or ''} {item.get('requirement_text') or ''}"
        for item in criteria
        if item.get("is_mandatory", True)
    ).lower()
    text = re.sub(r"[^a-z0-9]+", " ", f"{title} {criteria_text}").strip()
    if target_key in {"matric", "intermediate", "bachelors"} and re.search(
        r"\b(?:graduate|postgraduate)\s+(?:students?|applicants?|degree|scholarships?)\b|"
        r"\b(?:graduates?|postgraduates?)\s+and\s+(?:phd|doctoral)\b",
        text,
    ):
        target_names = {
            "matric": "Matric", "intermediate": "Intermediate",
            "bachelors": "Bachelor's / undergraduate",
        }
        return (
            "This opportunity is for graduate/postgraduate applicants, not "
            f"{target_names[target_key]} study."
        )

    # Require explicit programme/applicant wording; a mention of a degree as
    # a prerequisite (e.g. 16 years of education) is not enough to classify.
    level_patterns = {
        "matric": r"\b(?:matric|ssc|secondary school)\s+(?:scholarship|programme|program|applicants?|admission|study)\b|\bfor\s+(?:matric|ssc)\b",
        "intermediate": r"\b(?:intermediate|hssc|higher secondary)\s+(?:scholarship|programme|program|applicants?|admission|study)\b|\bfor\s+(?:intermediate|hssc)\b",
        "bachelors": r"\b(?:bachelor|bachelors|undergraduate)\s+(?:scholarship|programme|program|applicants?|admission|study)\b|\bfor\s+(?:bachelor|bachelors|undergraduate)\b",
        "master": r"\b(?:master|masters|postgraduate|ms|mphil)\s+(?:scholarship|programme|program|applicants?|admission|study)\b|\bfor\s+(?:a\s+)?(?:master|masters|postgraduate|ms|mphil)\b",
        "phd": r"\b(?:phd|doctoral|doctorate)\s+(?:scholarship|programme|program|applicants?|admission|study)\b|\bfor\s+(?:a\s+)?(?:phd|doctoral|doctorate)\b",
        "vocational_training": r"\b(?:ausbildung|auszubildende|apprenticeship|vocational training)\b",
    }
    explicit_levels = {level for level, pattern in level_patterns.items() if re.search(pattern, text)}
    if (re.search(r"\b(?:promotionsstipendium|promotionsförderung|promovierende|doktorand(?:innen|en)?|doctoral|phd)\b", text)
            or re.search(r"promotions[-\s]*f[oö]rderung", title)):
        explicit_levels.add("phd")
        explicit_levels.add("phd")
    if re.search(r"\b(?:ausbildung|auszubildende|ausbildungsvertrag|apprenticeship)\b", text):
        explicit_levels.add("vocational_training")
    if not explicit_levels or target_key in explicit_levels:
        return None

    # Multi-level awards (e.g. Master's and PhD) are valid for either named level.
    if target_key in {"master", "phd"} and len(explicit_levels) > 1 and explicit_levels <= {"master", "phd"}:
        return None
    target_names = {
        "matric": "Matric", "intermediate": "Intermediate",
        "bachelors": "Bachelor's / undergraduate", "master": "Master's",
        "phd": "PhD",
        "vocational_training": "vocational training / Ausbildung",
    }
    available = ", ".join(target_names[level] for level in sorted(explicit_levels))
    return f"This opportunity is explicitly for {available} study, not {target_names[target_key]} study."


def match_profile_to_scholarships(rows: list[dict[str, Any]], criteria_by_id: dict[int, list[dict[str, Any]]],
                                  profile: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for row in rows:
        criteria = criteria_by_id.get(row["id"], [])
        mismatch = _target_level_mismatch(row, criteria, profile)
        if mismatch:
            continue
        results.append(match_scholarship(row, criteria, profile))
    priority = {"likely_eligible": 0, "needs_more_information": 1, "not_eligible": 2}
    return sorted(results, key=lambda x: (
        x["application_status"] == "closed",
        priority[x["match_status"]],
        x["deadline_date"] is None,
        x["deadline_date"] or "9999-12-31",
        x["title"].lower(),
    ))
