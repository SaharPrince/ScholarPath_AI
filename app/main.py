import secrets
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.live_discovery import discover_live_scholarships
from app.matching import match_profile_to_scholarships
from app.source_catalog import GERMANY_SOURCES


app = FastAPI(
    title=settings.app_name,
    description="Live official-source scholarship discovery and eligibility matching.",
    version="0.7.0",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
def scholarship_home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Health check without requiring a scholarship database."""
    return {"status": "ok", "discovery": "live", "scholarship_storage": "disabled"}


@app.get("/api/sources", tags=["sources"])
def list_sources() -> list[dict]:
    """Return the static official German source registry."""
    return [
        {
            "id": index,
            "name": source["name"],
            "official_url": source["official_url"],
            "source_type": source["source_type"],
            "country": source["country"],
            "is_active": True,
        }
        for index, source in enumerate(GERMANY_SOURCES, start=1)
    ]


async def _live_results() -> list[dict]:
    try:
        return await discover_live_scholarships()
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Official-source discovery took too long. Please try again.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Live discovery could not reach the official sources. Please try again.",
        ) from exc


@app.get("/api/scholarships", tags=["scholarships"])
async def list_scholarships(
    country: str | None = Query(default=None, min_length=2, max_length=100),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Fetch and extract current opportunities on every request; never persist them."""
    if status not in (None, "all", "unverified", "verified", "expired", "candidate", "rejected"):
        raise HTTPException(status_code=422, detail="Unsupported scholarship status")
    rows = await _live_results()
    if country and country.strip().casefold() not in {"germany", "de"}:
        return []
    if status not in (None, "all"):
        rows = [row for row in rows if row["status"] == status]
    return rows[offset:offset + limit]


@app.get("/api/scholarships/{scholarship_id}", tags=["scholarships"])
async def get_scholarship(scholarship_id: int) -> dict:
    """Refresh official sources and return the matching live opportunity."""
    rows = await _live_results()
    for row in rows:
        if row["id"] == scholarship_id:
            return row
    raise HTTPException(status_code=404, detail="This opportunity was not found in the current live source scan.")


@app.post("/api/match", tags=["matching"])
async def match_profile(profile: dict) -> dict:
    """Match the submitted student profile against freshly fetched source criteria."""
    allowed = {
        "nationality", "residence_country", "dual_national", "age",
        "regular_government_employee", "public_university_faculty",
        "approved_rd_researcher", "receiving_other_scholarship", "has_phd",
        "target_study_level", "current_education_level", "academic_percentage",
        "education_field", "domicile_region", "years_of_education", "latest_degree_division",
        "hat_score", "hat_category", "gre_score", "university_qs_rank", "admission_confirmed",
    }
    unknown_fields = set(profile) - allowed
    if unknown_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported profile fields: {', '.join(sorted(unknown_fields))}",
        )
    required_fields = {
        "nationality": "nationality",
        "current_education_level": "highest education completed",
        "target_study_level": "next study level",
    }
    missing_fields = [
        label for field, label in required_fields.items()
        if not str(profile.get(field) or "").strip()
    ]
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail="Please provide the required profile details: " + ", ".join(missing_fields),
        )

    scholarships = await _live_results()
    criteria_by_id = {row["id"]: row.get("criteria", []) for row in scholarships}
    results = match_profile_to_scholarships(scholarships, criteria_by_id, profile)
    visible_results = [item for item in results if item["match_status"] != "not_eligible"]
    return {
        "total": len(results),
        "likely_eligible": sum(item["match_status"] == "likely_eligible" for item in results),
        "needs_more_information": sum(item["match_status"] == "needs_more_information" for item in results),
        "not_eligible": sum(item["match_status"] == "not_eligible" for item in results),
        "results": visible_results,
        "notice": "Live preliminary matching only. Unknown or unsupported requirements are not assumed satisfied. Confirm current details with the official provider.",
    }


@app.get("/api/cron/discover", tags=["discovery"])
async def scheduled_discovery(authorization: str | None = Header(default=None)) -> dict:
    """Legacy endpoint disabled: scheduled jobs must not create stored scholarships."""
    if not settings.cron_secret:
        raise HTTPException(status_code=410, detail="Scheduled database discovery has been retired.")
    expected = f"Bearer {settings.cron_secret}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    raise HTTPException(
        status_code=410,
        detail="Scholarships are discovered live when students search; no records are stored.",
    )
