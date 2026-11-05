from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    """Small environment-based settings object; no secrets are hardcoded."""

    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "ScholarPath AI")
        self.environment = os.getenv("APP_ENV", "development")
        configured_db_path = os.getenv("DATABASE_PATH", "data/scholarpath.db")
        self.database_path = (PROJECT_ROOT / configured_db_path).resolve()


settings = Settings()
