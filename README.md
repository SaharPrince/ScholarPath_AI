# ScholarPath AI

ScholarPath AI helps students discover Germany-focused scholarship opportunities from official sources and understand the requirements published by each provider.

## Product scope

The product is deliberately limited to two jobs:

1. Discover individual scholarship opportunities from official German scholarship providers, foundations, universities, and government sources.
2. Compare a student's profile with the opportunity's published eligibility requirements and explain what is met, not met, or still unknown.

## Live-only scholarship data

**Scholarship opportunities are not stored in a database.**

- Every scholarship search fetches current pages from the configured official sources.
- Results and their extracted criteria are assembled in memory for that request.
- The source registry is configuration in `app/source_catalog.py`; it is not a stored scholarship catalogue.
- Live scholarship endpoints do not read or write persisted scholarship records.
- A URL-derived identifier is used to refer to a result within a response. It is not a database record.
- Operational source configuration and legacy database helpers are separate from the live scholarship result path.

A new search fetches the sources again. Results can change when a provider updates a page, blocks automated requests, or publishes a new application cycle.

## Official-source and evidence rules

- The source registry contains curated official German provider, foundation, government, and university pages.
- Broad directories and provider indexes are not treated as individual scholarships.
- When a source links to a specific programme or eligibility page, discovery follows same-host official links where possible.
- Each extracted requirement retains the official URL that supports it.
- Generic directory descriptions, incomplete statements, and application instructions are not presented as applicant eligibility rules.
- Explicit requirements are distinguished from preferences such as “priority is given to”.
- Missing facts remain unknown. The application never invents deadlines, funding amounts, providers, nationality rules, or eligibility thresholds.
- An official source is evidence of what that provider published; it does not automatically prove that an application cycle is currently open or that the opportunity has been independently verified.

Some providers restrict automated requests or return HTTP 403. Those sources may be temporarily unavailable; the application must not fill the gap with guessed scholarship data.

## Eligibility matching

The matcher evaluates only criteria supported by the official source:

- **Pass:** the supplied profile satisfies the published condition.
- **Fail:** the supplied profile conflicts with a mandatory condition.
- **Unknown / more information needed:** the source or profile does not provide enough information to decide.

Unknown must never be treated as eligible. Master's and PhD conditions are distinguished from undergraduate study so a Bachelor's applicant is not shown a graduate-only award as a match.

## Trust and application status

These are separate concepts:

- `status` is the verification state. Newly discovered records remain `unverified`.
- `application_status` describes the application cycle when the source provides enough evidence: `open`, `upcoming`, `closed`, `discontinued`, `shortlisted_only`, or `unknown`.

A reachable page, an official provider name, or a future deadline alone does not prove that applications are open.

## API

- `GET /api/health` — live-discovery service health.
- `GET /api/sources` — configured official source registry.
- `GET /api/scholarships` — fetch current opportunities from official sources; supports the available status filter.
- `GET /api/scholarships/{id}` — resolve a result by its URL-derived identifier using fresh source data.
- `POST /api/match` — match a student profile against freshly discovered criteria.
- `GET /api/cron/discover` — retired legacy database-discovery route; returns HTTP 410.

The scholarship list and detail endpoints do not read from a persisted scholarship catalogue.

## Run locally

1. Use Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Start the API:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Open `http://127.0.0.1:8000`.

## Tests

Run the complete test suite:

```bash
python -m unittest discover -s tests -v
```

The tests cover extraction, evidence retention, directory-page filtering, official-source constraints, live discovery, and eligibility matching.

## Deployment and review

Changes are developed on `feature/germany-scholarship-catalogue` and reviewed through pull request #16. Preview deployments are for testing. Production is not changed until the pull request is explicitly approved and merged.
