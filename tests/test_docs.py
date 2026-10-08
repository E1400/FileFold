"""README and landing page: no dead links, and every documented command exists."""
import re
import shlex
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from filefold.cli.main import app

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
LANDING = (ROOT / "docs" / "index.html").read_text()
APP_CSS = (ROOT / "src" / "filefold" / "web" / "static" / "app.css").read_text()


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


# --- the landing page shares the app's design system ------------------------------------------

def _tokens(css: str, selector_start: str) -> dict[str, str]:
    """Custom properties declared in the first block that starts with `selector_start`."""
    start = css.index(selector_start)
    block = css[css.index("{", start) + 1: css.index("}", start)]
    return {m.group(1): m.group(2).strip().lower() for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", block)}


SHARED = ["--bg", "--surface", "--surface2", "--border", "--hairline", "--text", "--muted", "--accent",
          "--accent-ink", "--cat-mesh", "--cat-material", "--cat-step", "--cat-loads", "--cat-contact",
          "--cat-output", "--cat-model", "--cat-section", "--cat-constraint", "--cat-initial",
          "--radius", "--mono", "--sans"]


def test_landing_uses_the_apps_exact_design_tokens_in_light_and_dark():
    for selector in (":root {", ':root[data-theme="dark"]'):
        app, landing = _tokens(APP_CSS, selector), _tokens(LANDING, selector)
        for name in SHARED:
            if name in app:
                assert landing.get(name) == app[name], f"{selector}: {name} differs ({landing.get(name)!r} vs {app[name]!r})"
    # the dark theme must also apply from the system setting, as in the app
    assert 'prefers-color-scheme: dark' in LANDING and ':root:not([data-theme="light"])' in LANDING


def test_landing_follows_the_apps_type_rules():
    """The app uses weights 400 and 600 only, and the same system font stacks; so does the landing page."""
    weights = set(re.findall(r"font-weight\s*:\s*(\d+)", LANDING))
    assert weights <= {"400", "600"}, weights
    assert "Helvetica Neue" in LANDING and "ui-monospace" in LANDING


def test_landing_is_self_contained_and_private():
    assert not re.search(r'<link[^>]+rel=["\']stylesheet', LANDING), "no external stylesheet"
    assert "fonts.googleapis" not in LANDING and "<script src=" not in LANDING
    assert not re.search(r"https?://[^\"' ]*(analytics|gtag|segment|hotjar)", LANDING, flags=re.I)


def test_landing_screenshots_exist_and_are_described():
    imgs = re.findall(r'<img[^>]+>', LANDING)
    assert len(imgs) >= 4, "two screens in light and dark"
    for tag in imgs:
        src = re.search(r'src="([^"]+)"', tag).group(1)
        assert (ROOT / "docs" / src).is_file(), src
        assert re.search(r'alt="[^"]{20,}"', tag), f"{src} needs a real description"
        assert 'width="' in tag and 'height="' in tag, f"{src} needs dimensions (no layout shift)"


def test_the_figure_on_the_landing_page_is_what_filefold_really_does():
    """The 'one deck in, a workspace out' figure is computed from the Job-1 sample, not invented."""
    from filefold import service
    from filefold.api import server

    base = Path(tempfile.mkdtemp())
    old, server.WORKSPACE_BASE = server.WORKSPACE_BASE, base
    try:
        deck = ROOT / "src" / "filefold" / "web" / "static" / "samples" / "Job-1.inp"
        cats = ["mesh", "constraint", "material", "step"]
        service.create_workspace("fig", deck.name, deck, [{"category": c, "filename": f"{c}.inp", "sub_selections": []} for c in cats])
        files = {f["filename"]: f["line_count"] for f in service.get_workspace("fig")["files"]}
        mother = (base / "fig" / "Job-1.inp").read_text(encoding="utf-8")
    finally:
        server.WORKSPACE_BASE = old

    fig = re.search(r'<figure[^>]*id="fig-split".*?</figure>', LANDING, flags=re.S).group(0)
    claimed = {m.group(1): int(m.group(2)) for m in re.finditer(r'data-file="([^"]+)" data-lines="(\d+)"', fig)}
    assert claimed == {"Job-1.inp": files["Job-1.inp"], **{f"{c}.inp": files[f"{c}.inp"] for c in cats}}
    assert int(re.search(r'data-original-lines="(\d+)"', fig).group(1)) == deck.read_bytes().count(b"\n")
    # every real line quoted from the mother file is really in the mother file
    import html
    snippet = re.search(r'<pre[^>]*data-fig="mother">(.*?)</pre>', fig, flags=re.S).group(1)
    for line in html.unescape(re.sub(r"<[^>]+>", "", snippet)).splitlines():
        if line.strip() and line.strip() != "…":
            assert line.strip() in mother, f"figure quotes a line the mother file does not contain: {line!r}"


# --- the landing page's "Supported" breakdown is tied to the code, so it cannot go stale ----------------

def _supported() -> str:
    return re.search(r'<section class="sec" id="supported".*?</section>', LANDING, flags=re.S).group(0)


def test_landing_lists_every_category_the_parser_has():
    from filefold.core.keywords import Category
    section = _supported()
    for cat in Category:
        assert f'data-cat="{cat.value}"' in section, f"landing 'Supported' never lists the {cat.value!r} category"


def test_landing_lists_every_fixed_split_option_and_the_name_based_ones():
    from filefold.core.keywords import CATEGORY_SUB_OPTIONS
    text = re.sub(r"<[^>]+>", " ", _supported()).lower()
    for options in CATEGORY_SUB_OPTIONS.values():
        for opt in options:
            assert opt["label"].split(" (")[0].lower() in text, f"landing never mentions the split '{opt['label']}'"
    for phrase in ("one file per material", "one file per step", "one file per part"):
        assert phrase in text


def test_landing_keyword_count_is_the_real_one():
    from filefold.core.keyword_reference import FACTS
    claimed = int(re.search(r'data-keyword-count="(\d+)"', _supported()).group(1))
    assert claimed == len(FACTS), f"landing says {claimed} keywords, the reference table has {len(FACTS)}"


def test_landing_names_every_command_line_command():
    from typer.main import get_command
    root = get_command(app)
    names = set(root.commands) - {"workspace"}
    names |= {f"workspace {c}" for c in root.commands["workspace"].commands}
    text = re.sub(r"<[^>]+>", " ", LANDING)
    missing = sorted(n for n in names if f"filefold {n}" not in text and not (n.startswith("workspace ") and n.split()[1] in text))
    assert not missing, f"landing page never mentions CLI commands: {missing}"


def test_landing_states_the_in_browser_size_limit_the_app_enforces():
    js = (ROOT / "src" / "filefold" / "web" / "static" / "create.js").read_text()
    limit = int(re.search(r"STATIC_MAX_TESTED_BYTES = (\d+) \* 1024 \* 1024", js).group(1))
    assert f"{limit} MB" in _supported() and f"{limit} MB" in LANDING


def test_landing_names_the_three_sample_decks_and_admits_what_it_cannot_do():
    section = _supported()
    for deck in ("Job-1", "mmxmn", "fempy_example"):
        assert deck in LANDING
    assert 'id="not-supported"' in section and "Not supported yet" in section


def test_every_example_keyword_on_the_landing_page_is_in_the_category_shown_beside_it():
    from filefold.core.keywords import Category, categorize
    section = re.search(r'id="support-categories".*?</dl>', LANDING, flags=re.S).group(0)
    checked = 0
    for row in re.finditer(r'<dt>.*?data-cat="(\w+)".*?</dt>\s*<dd>(.*?)</dd>', section, flags=re.S):
        category, body = row.group(1), row.group(2)
        for kw in re.findall(r"<code>(\*[^<]+)</code>", body):
            assert categorize(kw) is Category(category), f"{kw} is shown under {category!r} but the parser says {categorize(kw).value!r}"
            checked += 1
    assert checked >= 40


def test_every_category_chip_on_the_landing_page_has_its_colour():
    from filefold.core.keywords import Category
    for cat in Category:
        assert f'[data-cat="{cat.value}"] {{ --c: var(--cat-{cat.value}); }}' in LANDING, f"no chip colour for {cat.value}"
