"""Validate the inline browser JavaScript in the scholarship page with Node.js."""
from pathlib import Path
import re
import subprocess
import tempfile

html = Path("app/static/index.html").read_text(encoding="utf-8")
scripts = re.findall(r"<script\\b[^>]*>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
if len(scripts) != 1:
    raise SystemExit(f"Expected exactly one inline script, found {len(scripts)}")

with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
    handle.write(scripts[0])
    script_path = Path(handle.name)

try:
    subprocess.run(["node", "--check", str(script_path)], check=True)
finally:
    script_path.unlink(missing_ok=True)
