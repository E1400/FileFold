"""README and landing page: no dead links, and every documented command exists."""
import re
import shlex
from pathlib import Path

from typer.testing import CliRunner

from filefold.cli.main import app

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
LANDING = (ROOT / "docs" / "index.html").read_text()


def test_no_link_to_the_retired_railway_deployment():
    for name, text in (("README.md", README), ("docs/index.html", LANDING)):
        assert "up.railway.app" not in text, f"{name} still links to the Railway deployment"


def test_online_links_point_at_the_github_pages_app():
    assert "https://e1400.github.io/FileFold/app/" in README
    assert LANDING.count('href="app/"') >= 2          # hero button and the "Open FileFold online" card


def test_every_command_in_the_readme_exists_in_the_cli():
    block = re.search(r"## CLI.*?```bash\n(.*?)```", README, flags=re.S).group(1)
    commands = [l for l in block.splitlines() if l.strip().startswith("uv run filefold")]
    assert len(commands) >= 15
    runner = CliRunner()
    for line in commands:
        tokens = shlex.split(line.split("#")[0].split(">")[0])[3:]       # drop "uv run filefold", comments, redirects
        path = tokens[:2] if tokens[0] == "workspace" else tokens[:1]
        result = runner.invoke(app, [*path, "--help"])
        assert result.exit_code == 0, f"README documents `{line.strip()}` but the CLI has no `{' '.join(path)}`"


def test_landing_page_describes_current_features():
    for phrase in ("Split as deep as you need", "Private by design", "Command line included", "100 MB"):
        assert phrase in LANDING
