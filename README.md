# ScholarPath AI

ScholarPath AI helps students discover scholarship opportunities from trustworthy official sources and understand whether they meet each opportunity's eligibility requirements.

## Project scope

- Discover scholarships in Pakistan and internationally.
- Gather the eligibility criteria published by each scholarship provider.
- Compare a student's answers with every applicable requirement.
- Explain why a student appears eligible, ineligible, or needs more information.
- Display the official source, application link, deadline, funding details, and verification status whenever those details are available.

## Accuracy and trust

- Do not invent scholarships, providers, deadlines, funding amounts, eligibility rules, or application links.
- Prefer official scholarship-provider and government/university sources.
- Treat newly discovered opportunities as unverified until their authenticity and current status have been checked.
- A webpage being reachable does not, by itself, prove that a scholarship is genuine or currently open.
- Clearly distinguish confirmed facts from missing or uncertain information.

## Planned technology

- Python
- FastAPI
- SQLite
- HTTPX and Beautiful Soup for source retrieval and parsing
- HTML, CSS, and JavaScript for the interface

## Initial development focus

Build a reliable foundation for source discovery, scholarship records, eligibility data, and transparent matching. Keep the product limited to scholarship discovery and eligibility matching; do not add unrelated features.


## Run locally

1. Use Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` if you want to customize local settings.
5. Start the API with `uvicorn app.main:app --reload`.
6. Open `http://127.0.0.1:8000/docs` for the API documentation.

The database is created automatically at the path configured by `DATABASE_PATH` (default: `data/scholarpath.db`). The `/api/health` endpoint reports basic API and database readiness.

## Initial tests

Run the standard-library test suite with `python -m unittest discover -s tests`.

The current foundation creates source, scholarship, and eligibility-criteria tables. It does not yet perform live scholarship discovery or claim that any scholarship is verified.


## Initial API endpoints

- `GET /api/health` — API/database readiness.
- `GET /api/sources` — active configured sources.
- `GET /api/scholarships` — stored scholarships, with optional `country`, `status`, `limit`, and `offset` filters.
- `GET /api/scholarships/{id}` — one scholarship and its recorded eligibility criteria.

The API is read-only for scholarship data at this stage. No example scholarships or sources are inserted automatically, so an empty database returns empty lists rather than fabricated opportunities. A record's `candidate` or `unverified` status must not be presented as verified.


## Official-source discovery foundation

The initial curated source catalog contains official indexes from:

- Higher Education Commission Pakistan
- Ministry of Federal Education and Professional Training
- United States Educational Foundation in Pakistan (USEFP)
- DAAD Pakistan

The catalog stores source homepages/indexes, not scholarship claims. These sources are based on the providers' own official scholarship/funding pages and Pakistan's federal education ministry scholarship directory. The catalog must be reviewed and maintained as providers change their websites.

At application startup, the catalog is inserted without overwriting existing source records. To run a discovery pass locally:

```bash
python -m app.run_discovery
```

The first discovery pass only looks for scholarship-related links on each configured source homepage. It saves same-host HTTPS links as review candidates. It does not yet extract full scholarship details, follow external application links, create scholarship records, or decide eligibility. Candidate links are not verified scholarships.

New endpoint:

- `GET /api/discovery/candidates` — list candidate links, with optional `status`, `limit`, and `offset`.

Discovery requests have time and response-size limits, do not follow redirects, and only retain links on the configured source's host.

## Scholarship detail extraction (v0.2)

After running homepage discovery, extract visible details from each unprocessed
candidate page:

```powershell
python -m app.run_extraction
```

The extractor conservatively captures page title, description, provider label,
and clearly labelled deadline, funding, and eligibility-related text. It stores
source snippets in `scholarship_evidence` and structured eligibility text in
`eligibility_criteria`. Records created by extraction are always `unverified`;
this process does not decide whether an application is open or whether a student
qualifies.

Useful endpoints:

- `GET /api/discovery/extraction-attempts`
- `GET /api/scholarships/{id}/evidence`

Extraction is deliberately limited to candidate pages on their original HTTPS
host. It does not follow redirects, fetch external application forms, infer
missing facts, or treat an informational page as proof of an open scholarship.


## Evidence-based opportunity classification (v0.4)

Each extracted record now has two separate classifications:

- `status` remains the trust/verification state (`unverified` is not a verified scholarship).
- `application_status` describes the specific application cycle: `open`, `upcoming`, `closed`, `discontinued`, `shortlisted_only`, or `unknown`.
- `applicant_category` identifies a clearly signalled audience: `student`, `graduate`, `professional`, `faculty`, `institution`, or `unknown`.

A past explicit deadline marks that cycle `closed`; a future deadline alone does not prove that applications are open. Rolling applications or explicit open/upcoming/discontinued/shortlist wording can support the corresponding state. Pages that provide only a deadline and no meaningful programme facts are not promoted as scholarship records. Unknown is used whenever the page does not provide enough evidence.

Existing SQLite databases are upgraded additively when the API or extraction command starts. Existing records receive `unknown` classifications until they are reprocessed. To refresh the stored classifications from official source pages:

```powershell
python -m app.run_extraction --reprocess
```

The new fields are returned by both scholarship list and detail endpoints. Reprocessing does not make records verified.
