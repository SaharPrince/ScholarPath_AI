from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.database import database_is_ready, get_connection, init_db
from app.source_catalog import seed_official_sources
from app.matching import match_profile_to_scholarships
from app.schemas import (
    EligibilityCriterion,
    HealthResponse,
    ScholarshipDetail,
    ScholarshipSummary,
    SourceSummary,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_official_sources()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Official-source scholarship discovery and eligibility matching.",
    version="0.5.0",
    lifespan=lifespan,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
def scholarship_home() -> FileResponse:
    """Serve the responsive scholarship discovery interface."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health_check() -> dict[str, str]:
    """Basic service and database readiness check."""
    if not database_is_ready():
        return {"status": "degraded", "database": "unavailable"}
    return {"status": "ok", "database": "ready"}


@app.get("/api/sources", response_model=list[SourceSummary], tags=["sources"])
def list_sources() -> list[dict]:
    """List active configured scholarship sources; no sources are seeded."""
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT id, name, official_url, source_type, country, is_active
               FROM sources WHERE is_active = 1 ORDER BY name COLLATE NOCASE"""
        ).fetchall()
    return [dict(row) for row in rows]


@app.get(
    "/api/scholarships",
    response_model=list[ScholarshipSummary],
    tags=["scholarships"],
)
def list_scholarships(
    country: str | None = Query(default=None, min_length=2, max_length=100),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """List stored scholarships with optional country/status filters.

    Use status=all for an audit view that includes every stored status.
    """
    allowed_statuses = {"candidate", "unverified", "verified", "expired", "rejected"}
    if status is not None and status not in allowed_statuses | {"all"}:
        raise HTTPException(status_code=422, detail="Unsupported scholarship status")

    clauses: list[str] = []
    parameters: list[object] = []
    if status is None:
        # Keep rejected informational pages and unreviewed candidates out of
        # the normal scholarship feed; they remain accessible with status filters.
        clauses.extend(["s.status <> 'rejected'", "s.status <> 'candidate'"])
    if country:
        clauses.append("LOWER(s.country) = LOWER(?)")
        parameters.append(country.strip())
    if status and status != "all":
        clauses.append("s.status = ?")
        parameters.append(status)

    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    query = f"""SELECT s.id, s.title, s.provider_name, s.country,
                      s.study_destination, s.funding_summary, s.application_url,
                      s.deadline_text, s.deadline_date, s.status,
                      s.application_status, s.applicant_category,
                      src.name AS source_name, s.source_record_url AS source_url
               FROM scholarships AS s
               JOIN sources AS src ON src.id = s.source_id
               {where_sql}
               ORDER BY CASE s.status
                   WHEN 'verified' THEN 0 WHEN 'unverified' THEN 1
                   WHEN 'candidate' THEN 2 WHEN 'expired' THEN 3 ELSE 4 END,
                   s.deadline_date IS NULL, s.deadline_date, s.title COLLATE NOCASE
               LIMIT ? OFFSET ?"""
    parameters.extend([limit, offset])
    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


@app.get(
    "/api/scholarships/{scholarship_id}",
    response_model=ScholarshipDetail,
    tags=["scholarships"],
)
def get_scholarship(scholarship_id: int) -> dict:
    """Return one scholarship and its recorded eligibility criteria."""
    with get_connection() as connection:
        row = connection.execute(
            """SELECT s.id, s.title, s.provider_name, s.country,
                      s.study_destination, s.funding_summary, s.application_url,
                      s.deadline_text, s.deadline_date, s.status,
                      s.application_status, s.applicant_category,
                      src.name AS source_name, s.source_record_url AS source_url
               FROM scholarships AS s
               JOIN sources AS src ON src.id = s.source_id
               WHERE s.id = ?""",
            (scholarship_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Scholarship not found")
        criteria = connection.execute(
            """SELECT id, criterion_type, criterion_label, requirement_text,
                      is_mandatory, evidence_url
               FROM eligibility_criteria WHERE scholarship_id = ? ORDER BY id""",
            (scholarship_id,),
        ).fetchall()

    result = dict(row)
    result["criteria"] = [
        {**dict(item), "is_mandatory": bool(item["is_mandatory"])}
        for item in criteria
    ]
    return result



@app.post("/api/match", tags=["matching"])
def match_profile(profile: dict) -> dict:
    """Match an in-memory student profile against all stored scholarship criteria."""
    allowed = {
        "nationality", "residence_country", "dual_national", "age",
        "regular_government_employee", "public_university_faculty",
        "approved_rd_researcher", "receiving_other_scholarship", "has_phd",
        "target_study_level", "years_of_education", "latest_degree_division",
        "hat_score", "hat_category", "gre_score", "university_qs_rank", "admission_confirmed",
    }
    unknown_fields = set(profile) - allowed
    if unknown_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported profile fields: {', '.join(sorted(unknown_fields))}",
        )
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT s.id, s.title, s.provider_name, s.country,
                      s.study_destination, s.funding_summary, s.application_url,
                      s.deadline_text, s.deadline_date, s.status,
                      s.application_status, src.name AS source_name,
                      s.source_record_url AS source_url
               FROM scholarships s JOIN sources src ON src.id = s.source_id
               WHERE s.status <> 'candidate' AND s.status <> 'rejected'"""
        ).fetchall()
        scholarships = [dict(row) for row in rows]
        criteria_by_id = {}
        for row in scholarships:
            criteria = connection.execute(
                """SELECT id, criterion_type, criterion_label, requirement_text,
                          is_mandatory, evidence_url
                   FROM eligibility_criteria WHERE scholarship_id = ? ORDER BY id""",
                (row["id"],),
            ).fetchall()
            criteria_by_id[row["id"]] = [
                {**dict(item), "is_mandatory": bool(item["is_mandatory"])}
                for item in criteria
            ]
    results = match_profile_to_scholarships(scholarships, criteria_by_id, profile)
    return {
        "total": len(results),
        "likely_eligible": sum(x["match_status"] == "likely_eligible" for x in results),
        "needs_more_information": sum(x["match_status"] == "needs_more_information" for x in results),
        "not_eligible": sum(x["match_status"] == "not_eligible" for x in results),
        "results": results,
        "notice": "Preliminary matching only. Unknown or unsupported requirements are not assumed satisfied. Confirm all details with the official source.",
    }


@app.get("/api/discovery/candidates", tags=["discovery"])
def list_discovery_candidates(
    status: str = Query(default="candidate"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """List candidate links found on configured sources; candidates are not scholarships."""
    allowed_statuses = {"candidate", "reviewed", "rejected", "promoted", "all"}
    if status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Unsupported candidate status")

    where_sql = "" if status == "all" else "WHERE c.status = ?"
    parameters: list[object] = [] if status == "all" else [status]
    parameters.extend([limit, offset])
    query = f"""SELECT c.id, c.title, c.candidate_url, c.status,
                       c.first_seen_at, c.last_seen_at,
                       s.name AS source_name, s.official_url AS source_homepage
                FROM discovery_candidates AS c
                JOIN sources AS s ON s.id = c.source_id
                {where_sql}
                ORDER BY c.first_seen_at DESC, c.id DESC
                LIMIT ? OFFSET ?"""
    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/scholarships/{scholarship_id}/evidence", tags=["scholarships"])
def get_scholarship_evidence(scholarship_id: int) -> list[dict]:
    """Return captured source snippets supporting extracted scholarship details."""
    with get_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM scholarships WHERE id = ?", (scholarship_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Scholarship not found")
        rows = connection.execute(
            """SELECT field_name, evidence_text, evidence_url, captured_at
               FROM scholarship_evidence
               WHERE scholarship_id = ?
               ORDER BY id""",
            (scholarship_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/discovery/extraction-attempts", tags=["discovery"])
def list_extraction_attempts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Show extraction outcomes, including pages needing manual review."""
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT a.id, a.candidate_id, c.title AS candidate_title,
                      c.candidate_url, a.status, a.message, a.attempted_at
               FROM extraction_attempts a
               JOIN discovery_candidates c ON c.id = a.candidate_id
               ORDER BY a.attempted_at DESC, a.id DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]
