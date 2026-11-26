import tomllib
import unittest
from pathlib import Path

from app.main import app
from index import app as vercel_app


ROOT = Path(__file__).resolve().parents[1]


class VercelDeploymentConfigurationTests(unittest.TestCase):
    def test_vercel_entrypoint_targets_the_existing_fastapi_application(self):
        with (ROOT / "pyproject.toml").open("rb") as config_file:
            config = tomllib.load(config_file)
        self.assertEqual(config["tool"]["vercel"]["entrypoint"], "app.main:app")
        self.assertEqual(config["project"]["requires-python"], ">=3.12")
        self.assertIs(vercel_app, app)

    def test_python_runtime_is_pinned_to_the_ci_minor_version(self):
        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.12")

    def test_frontend_entry_file_is_available_to_the_fastapi_route(self):
        self.assertTrue((ROOT / "app" / "static" / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
