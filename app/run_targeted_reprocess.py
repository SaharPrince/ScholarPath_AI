import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

from app.config import settings
from app.database import init_db, get_connection
from app.extraction import extract_candidate_details


def inspect_candidates(candidate_ids: list[int]) -> list[dict]:
    """Read-only preview of exactly which candidate records would be retried."""
    db_uri = settings.database_path.as_uri() + "?mode=ro"
    with sqlite3.connect(db_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in candidate_ids)
        rows = connection.execute(
            f"""SELECT c.id AS candidate_id, c.title, c.candidate_url,
                       s.name AS source_name, c.status AS candidate_status,
                       a.status AS previous_attempt,
                       sh.id AS scholarship_id, sh.status AS scholarship_status
                FROM discovery_candidates c
                JOIN sources s ON s.id = c.source_id
                LEFT JOIN extraction_attempts a ON a.candidate_id = c.id
                LEFT JOIN scholarships sh
                  ON sh.source_id = c.source_id
                 AND sh.source_record_url = c.candidate_url
                WHERE c.id IN ({placeholders})
                ORDER BY c.id""",
            candidate_ids,
        ).fetchall()
    return [dict(row) for row in rows]


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely reprocess only explicitly selected scholarship candidates."
    )
    parser.add_argument("candidate_ids", nargs="+", type=int)
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually retry these candidates. Without this flag, only a read-only preview is shown."
    )
    args = parser.parse_args()
    candidate_ids = sorted(set(args.candidate_ids))

    preview = inspect_candidates(candidate_ids)
    found_ids = {row["candidate_id"] for row in preview}
    missing_ids = sorted(set(candidate_ids) - found_ids)
    print("Preview:")
    print(json.dumps(preview, indent=2))
    if missing_ids:
        raise SystemExit(f"Unknown candidate IDs: {missing_ids}")
    if not args.apply:
        print("\nDRY RUN ONLY. No database records were changed.")
        print("Review the preview, then rerun with --apply to perform the targeted retry.")
        return

    init_db()
    with get_connection() as connection:
        placeholders = ",".join("?" for _ in candidate_ids)
        connection.execute(
            f"DELETE FROM extraction_attempts WHERE candidate_id IN ({placeholders})",
            candidate_ids,
        )
        connection.execute(
            f"""UPDATE discovery_candidates SET status = 'candidate'
                WHERE id IN ({placeholders})""",
            candidate_ids,
        )

    results = await extract_candidate_details(candidate_ids=candidate_ids)
    print("\nResults:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
