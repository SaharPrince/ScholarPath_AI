import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import settings


SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    official_url TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'official',
    country TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scholarships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    provider_name TEXT,
    country TEXT,
    study_destination TEXT,
    funding_summary TEXT,
    application_url TEXT,
    deadline_text TEXT,
    deadline_date TEXT,
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'unverified', 'verified', 'expired', 'rejected')),
    source_record_url TEXT NOT NULL,
    last_checked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    application_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK (application_status IN ('open', 'upcoming', 'closed', 'discontinued', 'shortlisted_only', 'unknown')),
    applicant_category TEXT NOT NULL DEFAULT 'unknown'
        CHECK (applicant_category IN ('student', 'graduate', 'professional', 'faculty', 'institution', 'unknown')),
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE RESTRICT,
    UNIQUE (source_id, source_record_url)
);
CREATE TABLE IF NOT EXISTS eligibility_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scholarship_id INTEGER NOT NULL,
    criterion_type TEXT NOT NULL,
    criterion_label TEXT NOT NULL,
    requirement_text TEXT NOT NULL,
    is_mandatory INTEGER NOT NULL DEFAULT 1 CHECK (is_mandatory IN (0, 1)),
    evidence_url TEXT,
    FOREIGN KEY (scholarship_id) REFERENCES scholarships(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS discovery_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    candidate_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'reviewed', 'rejected', 'promoted')),
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE RESTRICT,
    UNIQUE (source_id, candidate_url)
);
CREATE TABLE IF NOT EXISTS scholarship_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scholarship_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    evidence_text TEXT NOT NULL,
    evidence_url TEXT NOT NULL,
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scholarship_id) REFERENCES scholarships(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS extraction_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('extracted', 'insufficient_evidence', 'failed', 'skipped')),
    message TEXT,
    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id) REFERENCES discovery_candidates(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_discovery_candidates_status ON discovery_candidates(status);
CREATE INDEX IF NOT EXISTS idx_extraction_attempts_candidate ON extraction_attempts(candidate_id);
CREATE INDEX IF NOT EXISTS idx_scholarships_status ON scholarships(status);
CREATE INDEX IF NOT EXISTS idx_scholarships_country ON scholarships(country);
CREATE INDEX IF NOT EXISTS idx_criteria_scholarship ON eligibility_criteria(scholarship_id);
"""

POSTGRES_SCHEMA = re.sub(
    r"INTEGER PRIMARY KEY AUTOINCREMENT",
    "BIGSERIAL PRIMARY KEY",
    SQLITE_SCHEMA.replace("PRAGMA foreign_keys = ON;", ""),
    flags=re.IGNORECASE,
)
# PostgreSQL foreign-key columns must match the BIGSERIAL primary-key type.
POSTGRES_SCHEMA = re.sub(r"\\bINTEGER\\b", "BIGINT", POSTGRES_SCHEMA, flags=re.IGNORECASE)


class PostgresConnection:
    """Small compatibility wrapper for the parameterized SQL used by the app."""

    def __init__(self, connection):
        self._connection = connection
        self._total_changes = 0

    @property
    def total_changes(self) -> int:
        return self._total_changes

    def execute(self, sql: str, parameters=()):
        # All application SQL uses positional qmark parameters. Translate only
        # placeholders, not question marks inside quoted SQL strings.
        translated = []
        in_single = False
        in_double = False
        i = 0
        while i < len(sql):
            char = sql[i]
            if char == "'" and not in_double:
                in_single = not in_single
            elif char == '"' and not in_single:
                in_double = not in_double
            if char == "?" and not in_single and not in_double:
                translated.append("%s")
            else:
                translated.append(char)
            i += 1
        statement = "".join(translated)
        if re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\b", statement, re.IGNORECASE):
            statement = re.sub(
                r"^(\s*)INSERT\s+OR\s+IGNORE\s+INTO\b",
                r"\1INSERT INTO",
                statement,
                flags=re.IGNORECASE,
            )
            statement = statement.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        cursor = self._connection.execute(statement, parameters)
        if cursor.rowcount and cursor.rowcount > 0:
            self._total_changes += cursor.rowcount
        return cursor

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


@contextmanager
def get_connection():
    """Yield a PostgreSQL connection in deployment, or SQLite locally/tests."""
    if settings.database_url:
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(settings.database_url, row_factory=dict_row)
        connection = PostgresConnection(raw)
    else:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(settings.database_path)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        connection = raw
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create schema idempotently; keep SQLite migrations for existing local DBs."""
    with get_connection() as connection:
        if settings.database_url:
            for statement in POSTGRES_SCHEMA.split(";"):
                if statement.strip():
                    connection.execute(statement)
        else:
            connection.executescript(SQLITE_SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(scholarships)")
            }
            if "application_status" not in columns:
                connection.execute(
                    """ALTER TABLE scholarships ADD COLUMN application_status TEXT NOT NULL
                       DEFAULT 'unknown' CHECK (application_status IN
                       ('open', 'upcoming', 'closed', 'discontinued', 'shortlisted_only', 'unknown'))"""
                )
            if "applicant_category" not in columns:
                connection.execute(
                    """ALTER TABLE scholarships ADD COLUMN applicant_category TEXT NOT NULL
                       DEFAULT 'unknown' CHECK (applicant_category IN
                       ('student', 'graduate', 'professional', 'faculty', 'institution', 'unknown'))"""
                )


def database_is_ready() -> bool:
    """Return whether the configured database can answer a basic query."""
    with get_connection() as connection:
        row = connection.execute("SELECT 1 AS ready").fetchone()
        return bool(row and row["ready"] == 1)
