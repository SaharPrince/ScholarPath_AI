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
