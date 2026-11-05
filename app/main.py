from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from app.config import settings
from app.database import database_is_ready, get_connection, init_db
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
    yield


app = FastAPI(
    title=settings.app_name,
    description="Official-source scholarship discovery and eligibility matching.",
    version="0.1.0",
    lifespan=lifespan,
)


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
    """List stored scholarships with optional country/status filters."""
    allowed_statuses = {"candidate", "unverified", "verified", "expired", "rejected"}
    if status is not None and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Unsupported scholarship status")

    clauses: list[str] = []
    parameters: list[object] = []
    if country:
        clauses.append("LOWER(s.country) = LOWER(?)")
        parameters.append(country.strip())
    if status:
        clauses.append("s.status = ?")
        parameters.append(status)

    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    query = f"""SELECT s.id, s.title, s.provider_name, s.country,
                      s.study_destination, s.funding_summary, s.application_url,
                      s.deadline_text, s.deadline_date, s.status,
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
