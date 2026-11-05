import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import settings


SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_scholarships_status
    ON scholarships(status);
CREATE INDEX IF NOT EXISTS idx_scholarships_country
    ON scholarships(country);
CREATE INDEX IF NOT EXISTS idx_criteria_scholarship
    ON eligibility_criteria(scholarship_id);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with foreign-key checks enabled."""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create the initial schema if it does not already exist."""
    with get_connection() as connection:
        connection.executescript(SCHEMA)


def database_is_ready() -> bool:
    """Return whether SQLite can answer a basic query."""
    with get_connection() as connection:
        row = connection.execute("SELECT 1 AS ready").fetchone()
        return bool(row and row["ready"] == 1)
