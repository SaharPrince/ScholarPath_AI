"""One-time, lossless import of the local SQLite database into Supabase PostgreSQL.

Run this BEFORE the first Vercel request initializes/seeds the production database.
The target must be empty; this script refuses to merge into or overwrite existing data.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import psycopg
from psycopg import sql

from app.config import settings
from app.database import init_db


TABLES = (
    "sources",
    "scholarships",
    "eligibility_criteria",
    "scholarship_evidence",
    "discovery_candidates",
    "extraction_attempts",
)


def validate_sqlite(source_path: Path) -> tuple[sqlite3.Connection, dict[str, int]]:
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")

    source = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row

    integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        source.close()
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")

    foreign_key_errors = source.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        source.close()
        raise RuntimeError(
            f"SQLite contains {len(foreign_key_errors)} foreign-key violation(s); import stopped."
        )

    counts = {
        table: source.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in TABLES
    }
    return source, counts


def import_database(source_path: Path) -> dict[str, int]:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it privately in your local .env file; "
            "never commit or share that file."
        )

    source, source_counts = validate_sqlite(source_path)
    try:
        # Create the PostgreSQL schema, but do not seed it. The source database
        # already contains the curated source catalogue and its original IDs.
        init_db()

        with psycopg.connect(
            settings.database_url,
            prepare_threshold=None,  # Supabase transaction-pooler compatibility.
        ) as target:
            with target.cursor() as cursor:
                target_counts = {}
                for table in TABLES:
                    cursor.execute(
                        sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
                    )
                    target_counts[table] = cursor.fetchone()[0]

                nonempty = {name: count for name, count in target_counts.items() if count}
                if nonempty:
                    raise RuntimeError(
                        "Supabase tables are not empty. No data was imported. "
                        f"Existing row counts: {nonempty}. Stop and review before retrying."
                    )

                for table in TABLES:
                    columns = [
                        row["name"]
                        for row in source.execute(f"PRAGMA table_info({table})").fetchall()
                    ]
                    rows = source.execute(
                        f"SELECT * FROM {table} ORDER BY id"
                    ).fetchall()
                    if not rows:
                        continue

                    insert_statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                        sql.Identifier(table),
                        sql.SQL(", ").join(map(sql.Identifier, columns)),
                        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                    )
                    cursor.executemany(
                        insert_statement,
                        [tuple(row[column] for column in columns) for row in rows],
                    )

                # Explicit IDs are retained, so advance every BIGSERIAL sequence
                # to the imported maximum before the application inserts new rows.
                for table in TABLES:
                    cursor.execute(
                        sql.SQL(
                            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                            "GREATEST(COALESCE((SELECT MAX(id) FROM {}), 1), 1), "
                            "EXISTS(SELECT 1 FROM {}))"
                        ).format(sql.Identifier(table), sql.Identifier(table)),
                        (table,),
                    )

                imported_counts = {}
                for table in TABLES:
                    cursor.execute(
                        sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
                    )
                    imported_counts[table] = cursor.fetchone()[0]

                if imported_counts != source_counts:
                    raise RuntimeError(
                        "Post-import row-count verification failed; transaction will roll back. "
                        f"Source={source_counts}; target={imported_counts}"
                    )

        return source_counts
    finally:
        source.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=settings.database_path,
        help="Path to the existing SQLite database (defaults to DATABASE_PATH).",
    )
    args = parser.parse_args()

    try:
        counts = import_database(args.source)
    except Exception as exc:
        print(f"Migration stopped: {exc}", file=sys.stderr)
        return 1

    print("Supabase migration completed and verified:")
    for table, count in counts.items():
        print(f"  {table}: {count}")
    print("All original IDs and foreign-key relationships were preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
