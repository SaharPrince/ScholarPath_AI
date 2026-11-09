import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import database
from app.config import settings


class DatabaseSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = settings.database_path
        settings.database_path = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self) -> None:
        settings.database_path = self.original_path
        self.temp_dir.cleanup()

    def test_database_is_ready(self) -> None:
        self.assertTrue(database.database_is_ready())

    def test_initial_tables_exist(self) -> None:
        expected = {"sources", "scholarships", "eligibility_criteria"}
        with database.get_connection() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        actual = {row["name"] for row in rows}
        self.assertTrue(expected.issubset(actual))

    def test_new_classification_columns_default_to_unknown(self) -> None:
        with database.get_connection() as connection:
            connection.execute(
                "INSERT INTO sources (name, official_url) VALUES (?, ?)",
                ("Example source", "https://example.org"),
            )
            connection.execute(
                "INSERT INTO scholarships (source_id, title, source_record_url) VALUES (1, ?, ?)",
                ("Example scholarship", "https://example.org/scholarship"),
            )
            row = connection.execute(
                "SELECT application_status, applicant_category FROM scholarships WHERE id = 1"
            ).fetchone()
        self.assertEqual(row["application_status"], "unknown")
        self.assertEqual(row["applicant_category"], "unknown")

    def test_legacy_database_is_upgraded_without_losing_records(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        previous_path = settings.database_path
        settings.database_path = legacy_path
        try:
            connection = sqlite3.connect(legacy_path)
            connection.executescript("""
                CREATE TABLE sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    official_url TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL DEFAULT 'official',
                    country TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE scholarships (
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
                    status TEXT NOT NULL DEFAULT 'candidate',
                    source_record_url TEXT NOT NULL,
                    last_checked_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES sources(id),
                    UNIQUE (source_id, source_record_url)
                );
                INSERT INTO sources (name, official_url)
                VALUES ('Legacy source', 'https://legacy.example.org');
                INSERT INTO scholarships (source_id, title, source_record_url)
                VALUES (1, 'Legacy scholarship', 'https://legacy.example.org/scholarship');
            """)
            connection.commit()
            connection.close()

            database.init_db()
            with database.get_connection() as migrated:
                row = migrated.execute(
                    "SELECT title, application_status, applicant_category FROM scholarships WHERE id = 1"
                ).fetchone()
            self.assertEqual(row["title"], "Legacy scholarship")
            self.assertEqual(row["application_status"], "unknown")
            self.assertEqual(row["applicant_category"], "unknown")
        finally:
            settings.database_path = previous_path


    def test_official_source_seeding_is_idempotent(self) -> None:
        from app.source_catalog import LEGACY_HEC_URL, OFFICIAL_SOURCES, seed_official_sources

        with database.get_connection() as connection:
            connection.execute(
                "INSERT INTO sources (name, official_url) VALUES (?, ?)",
                ("Legacy HEC source", LEGACY_HEC_URL),
            )

        first_inserted = seed_official_sources()
        second_inserted = seed_official_sources()

        with database.get_connection() as connection:
            rows = connection.execute(
                "SELECT official_url, is_active FROM sources"
            ).fetchall()
        by_url = {row["official_url"]: row["is_active"] for row in rows}

        self.assertEqual(first_inserted, len(OFFICIAL_SOURCES))
        self.assertEqual(second_inserted, 0)
        self.assertEqual(len(by_url), len(OFFICIAL_SOURCES) + 1)
        self.assertEqual(by_url[LEGACY_HEC_URL], 0)
        for source in OFFICIAL_SOURCES:
            self.assertEqual(by_url[source["official_url"]], 1)

    def test_scholarship_requires_a_source(self) -> None:
        with self.assertRaises(Exception):
            with database.get_connection() as connection:
                connection.execute(
                    """INSERT INTO scholarships
                       (source_id, title, source_record_url)
                       VALUES (999, 'Example', 'https://example.org/scholarship')"""
                )


if __name__ == "__main__":
    unittest.main()
