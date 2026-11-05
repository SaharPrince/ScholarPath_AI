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
