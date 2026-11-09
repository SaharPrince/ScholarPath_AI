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

    if not criterion.get("is_mandatory", True):
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
            return _result("pass", "Your nationality and the supplied residency details meet the published rule.")
        return _result("unknown", "This nationality rule needs a specific check against the official wording.")

    if kind == "age_limit":
        if "no upper age limit" in lower or "no age limit" in lower:
            return _result("informational", "The source explicitly states there is no upper age limit.")
        age = _number(profile.get("age"))
        if age is None:
            return _result("unknown", "Add your age to check the published age limit.")
        limits = [int(x) for x in re.findall(r"\b(\d{2})\s*(?:years?|yrs?)\b", lower)]
        if not limits:
            return _result("unknown", "The age wording needs manual review; no numeric limit was safely identified.")
        limit = min(limits)
        qualified = any(profile.get(k) is True for k in (
            "regular_government_employee", "public_university_faculty", "approved_rd_researcher"
        ))
        if "all other cases" in lower and qualified:
            return _result("informational", "This lower age limit applies to other applicants; your profile indicates a specified public-sector category.")
        if "all other cases" in lower and not qualified:
            flags = ("regular_government_employee", "public_university_faculty", "approved_rd_researcher")
            if all(profile.get(k) is None for k in flags):
                return _result("unknown", "Confirm whether you belong to one of the specified public-sector employment categories before applying the general age limit.")
        if "regular government" in lower or "public sector" in lower or "approved r&d" in lower:
            if not qualified:
                flags = ("regular_government_employee", "public_university_faculty", "approved_rd_researcher")
                if all(profile.get(k) is not False for k in flags):
                    return _result("unknown", "Confirm whether you are a regular government employee, public university faculty member, or approved R&D researcher.")
                return _result("informational", "The higher public-sector age limit does not apply to the employment category you selected.")
        if age <= limit:
            return _result("pass", f"Your age ({int(age)}) is within the published maximum of {limit}.")
        return _result("fail", f"Your age ({int(age)}) is above the published maximum of {limit}.")

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

    if kind in {"academic_requirements", "category_i_eligibility", "category_ii_eligibility"}:
        target = (profile.get("target_study_level") or "").lower()
        if "for master" in lower or "master scholarship" in lower:
            if not target:
                return _result("unknown", "Choose your intended study level to check this Master's-specific requirement.")
            if target in {"bachelors", "bachelor", "undergraduate"}:
                return _result("fail", "This scholarship criterion is for Master's applicants, not undergraduate study.")
            if target not in {"master", "masters", "master's"}:
                return _result("informational", "This rule applies to Master's applicants, not your selected study level.")
        if "for phd" in lower or "phd scholarship" in lower:
            if not target:
                return _result("unknown", "Choose your intended study level to check this PhD-specific requirement.")
            if target in {"bachelors", "bachelor", "undergraduate"}:
                return _result("fail", "This scholarship criterion is for PhD applicants, not undergraduate study.")
            if target not in {"phd", "doctoral"}:
                return _result("informational", "This rule applies to PhD applicants, not your selected study level.")

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
        for item in category_checks:
            if item["status"] == "fail":
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


def match_profile_to_scholarships(rows: list[dict[str, Any]], criteria_by_id: dict[int, list[dict[str, Any]]],
                                  profile: dict[str, Any]) -> list[dict[str, Any]]:
    results = [
        match_scholarship(row, criteria_by_id.get(row["id"], []), profile)
        for row in rows
    ]
    priority = {"likely_eligible": 0, "needs_more_information": 1, "not_eligible": 2}
    return sorted(results, key=lambda x: (
        x["application_status"] == "closed",
        priority[x["match_status"]],
        x["deadline_date"] is None,
        x["deadline_date"] or "9999-12-31",
        x["title"].lower(),
    ))
