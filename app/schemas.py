from pydantic import BaseModel, ConfigDict


class SourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    official_url: str
    source_type: str
    country: str | None = None
    is_active: bool


class EligibilityCriterion(BaseModel):
    id: int
    criterion_type: str
    criterion_label: str
    requirement_text: str
    is_mandatory: bool
    evidence_url: str | None = None


class ScholarshipSummary(BaseModel):
    id: int
    title: str
    provider_name: str | None = None
    country: str | None = None
    study_destination: str | None = None
    funding_summary: str | None = None
    application_url: str | None = None
    deadline_text: str | None = None
    deadline_date: str | None = None
    status: str
    source_name: str
    source_url: str


class ScholarshipDetail(ScholarshipSummary):
    criteria: list[EligibilityCriterion]


class HealthResponse(BaseModel):
    status: str
    database: str
