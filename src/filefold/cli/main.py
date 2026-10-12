"""FileFold command line.

A thin layer over `filefold.service`, the same module the web app and the in-browser build
use, so the command line can do everything the app can. `OPERATION_COMMANDS` maps each
service operation to its command and a test fails if one is missing.

Workspaces live in ~/.filefold/workspaces (or $FILEFOLD_WORKSPACE_DIR / --workspaces), the
same place the web app uses, so a workspace made here shows up in the app and vice versa.
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from filefold import service
from filefold.api import server
from filefold.core.block import Block
from filefold.core.keywords import Category
from filefold.core.parser import parse
from filefold.core.splitter import SplitSelection, SubSplitSelection, split as split_blocks, split_with_includes
from filefold.service import NON_EXTRACTABLE, ServiceError, UnsafeName

app = typer.Typer(help="FileFold — Abaqus .inp file organizer", no_args_is_help=True)
ws_app = typer.Typer(help="Manage FileFold workspaces.", no_args_is_help=True)
app.add_typer(ws_app, name="workspace")
console = Console(soft_wrap=True)

# service operation -> the command that exposes it (checked by tests/test_cli.py)
OPERATION_COMMANDS = {
    "inspect": "inspect",
    "static_sub_options": "options",
    "list_all_workspaces": "workspace list",
    "create_workspace": "workspace create",
    "get_workspace": "workspace status",
    "rename_workspace": "workspace rename",
    "delete_workspace": "workspace delete",
    "extract_splits": "workspace extract",
    "resplit_child": "workspace resplit",
    "rename_file": "workspace rename-file",
    "recombine": "workspace recombine",
    "reimport_preview": "workspace reimport",
    "reimport_apply": "workspace reimport",
    "export_zip": "workspace export",
    "read_file": "workspace cat",
    "write_file": "workspace put",
}


@app.callback()
def _root(
    workspaces: Path = typer.Option(
        None, "--workspaces", help="Folder that holds workspaces (default: ~/.filefold/workspaces or $FILEFOLD_WORKSPACE_DIR)",
    ),
) -> None:
    """FileFold — Abaqus .inp file organizer."""
    if workspaces is not None:
        server.WORKSPACE_BASE = workspaces


@ws_app.callback()
def _ws_root() -> None:
    """Manage FileFold workspaces."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fail(message: str) -> typer.Exit:
    console.print(f"[red]{message}[/red]")
    return typer.Exit(1)


def _call(fn, *args, **kwargs):
    """Run a service operation, turning its errors into a clean message and exit code 1."""
    try:
        return fn(*args, **kwargs)
    except ServiceError as e:
        raise _fail(e.detail)
    except UnsafeName as e:
        raise _fail(str(e))


def _need_file(path: Path) -> None:
    if not path.is_file():
        raise _fail(f"File not found: {path}")


def _workspace_name(arg: str) -> str:
    """A workspace name, or (as the old CLI took) a path to its folder."""
    if "/" in arg or "\\" in arg or arg.startswith("."):
        path = Path(arg).expanduser()
        server.WORKSPACE_BASE = path.resolve().parent
        return path.resolve().name
    return arg


def _valid_categories() -> str:
    return ", ".join(c.value for c in Category if c.value not in NON_EXTRACTABLE)


def _options_for_deck(file: Path) -> dict[str, list[dict]]:
    return service.sub_split_info(parse(file, keep_lines=False))[0]


def _build_selections(extract: list[str], subs: list[str], options: dict[str, list[dict]]) -> list[dict]:
    """Turn -e/--extract and -s/--sub arguments into the selection payload the service takes.

    -e CATEGORY[=filename]          extract a category into its own file
    -s CATEGORY:KEY[=filename]      also split it further (keys come from `inspect --options`);
                                    this implies extracting the category itself
    """
    selections: dict[str, dict] = {}

    def category(name: str) -> str:
        name = name.lower()
        if name not in {c.value for c in Category}:
            raise _fail(f"Unknown category {name!r}. Valid: {_valid_categories()}")
        return name

    for item in extract:
        name, _, filename = item.partition("=")
        name = category(name)
        selections[name] = {"category": name, "filename": filename or f"{name}.inp", "sub_selections": []}

    for item in subs:
        spec, _, filename = item.partition("=")
        name, sep, key = spec.partition(":")
        if not sep or not key:
            raise _fail(f"--sub must look like CATEGORY:KEY (got {item!r}); see `inspect --options`")
        name = category(name)
        match = next((o for o in options.get(name, []) if o["sub_category"] == key), None)
        if match is None:
            valid = ", ".join(f"{name}:{o['sub_category']}" for o in options.get(name, [])) or "none for this category"
            raise _fail(f"{name}:{key} is not a split option here. Valid: {valid}")
        parent = selections.setdefault(
            name, {"category": name, "filename": f"{name}.inp", "sub_selections": []}
        )
        parent["sub_selections"].append(
            {"sub_category": key, "filename": filename or match["default_filename"]}
        )
    return list(selections.values())


EXTRACT_HELP = "Category to extract (repeatable), optionally with its filename: -e mesh -e material=mats.inp"
SUB_HELP = "Finer split (repeatable): CATEGORY:KEY, e.g. -s mesh:nodes -s material:material.steel. See `inspect --options`."


def _print_options(options: dict[str, list[dict]]) -> None:
    for cat, opts in options.items():
        console.print(f"[bold]{cat}[/bold]")
        for o in opts:
            console.print(f"  {cat}:{o['sub_category']}  [dim]{o['label']} → {o['default_filename']}[/dim]")


# ---------------------------------------------------------------------------
# files and decks
# ---------------------------------------------------------------------------

def _add_block(parent: Tree, block: Block) -> None:
    label = (
        f"[bold cyan]{block.keyword}[/bold cyan]"
        f"  [dim]{block.category.value}{' (inherited)' if block.inherited else ''}[/dim]"
        f"  [yellow]lines {block.line_start}–{block.line_end}[/yellow]"
    )
    node = parent.add(label)
    for child in block.children:
        _add_block(node, child)


@app.command()
def inspect(
    file: Path = typer.Argument(..., help="Path to the .inp file"),
    options: bool = typer.Option(False, "--options", help="Also list the finer splits available for this deck"),
) -> None:
    """Print a categorized tree of blocks in an Abaqus .inp file."""
    _need_file(file)
    blocks = parse(file, keep_lines=False)
    tree = Tree(f"[bold]{file.name}[/bold]  [dim]{len(blocks)} top-level blocks[/dim]")
    for block in blocks:
        _add_block(tree, block)
    console.print(tree)
    if options:
        console.print("\n[bold]Split options in this deck[/bold]  [dim](use with -s CATEGORY:KEY)[/dim]\n")
        _print_options(service.sub_split_info(blocks)[0])


@app.command()
def options() -> None:
    """List the fixed split options (keyword groups). Per-material, per-step and per-part
    options depend on the deck: use `inspect FILE --options`."""
    _print_options(service.static_sub_options())


@app.command()
def split(
    file: Path = typer.Argument(..., help="Path to the .inp file"),
    output_dir: Path = typer.Argument(..., help="Directory to write split files into"),
) -> None:
    """Split an Abaqus .inp file completely into per-category files (one folder, no *INCLUDEs)."""
    _need_file(file)
    written = split_blocks(parse(file), file, output_dir)
    console.print(f"\n[bold green]Split complete[/bold green] — {len(written)} files written to [cyan]{output_dir}[/cyan]\n")
    for path in written:
        console.print(f"  [dim]{path.relative_to(output_dir)}[/dim]")


@app.command(name="split-partial")
def split_partial(
    file: Path = typer.Argument(..., help="Path to the .inp file"),
    output_dir: Path = typer.Argument(..., help="Directory to write output files into"),
    extract: list[str] = typer.Option([], "--extract", "-e", help=EXTRACT_HELP),
    sub: list[str] = typer.Option([], "--sub", "-s", help=SUB_HELP),
) -> None:
    """Extract chosen categories into child files, leaving *INCLUDE pointers in the mother."""
    _need_file(file)
    selections = _build_selections(extract, sub, _options_for_deck(file))
    if not selections:
        raise _fail("Nothing to extract: pass -e CATEGORY and/or -s CATEGORY:KEY")
    sels = [
        SplitSelection(Category(s["category"]), s["filename"],
                       [SubSplitSelection(x["sub_category"], x["filename"]) for x in s["sub_selections"]])
        for s in selections
    ]
    result = _call(split_with_includes, parse(file), file, output_dir, sels)
    console.print(f"\n[bold green]Split complete[/bold green] → [cyan]{output_dir}[/cyan]\n")
    console.print(f"  [bold]{result.mother_path.name}[/bold]  [dim](mother with *INCLUDE lines)[/dim]")
    for child in result.children:
        where = f"  [dim]inside {child.parent}[/dim]" if child.parent else ""
        console.print(f"  [cyan]{child.filename}[/cyan]  [dim]{child.category.value}[/dim]{where}")


# ---------------------------------------------------------------------------
# workspaces
# ---------------------------------------------------------------------------

@ws_app.command("list")
def workspace_list() -> None:
    """List workspaces."""
    data = service.list_all_workspaces()
    if not data["workspaces"]:
        console.print("[dim]No workspaces yet. Create one with `filefold workspace create`.[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("workspace", "source", "files", "size"):
        table.add_column(col)
    for s in data["summaries"]:
        if s.get("broken"):
            table.add_row(s["name"], "[red]manifest unreadable[/red]", "", "")
        else:
            table.add_row(s["name"], s["source_name"], str(s["file_count"]), f"{s['bytes'] / 1048576:.1f} MB")
    console.print(table)


@ws_app.command("create")
def workspace_create(
    name: str = typer.Argument(..., help="Workspace name (or, as before, a folder path)"),
    source: Path = typer.Argument(..., help="Mother .inp file"),
    extract: list[str] = typer.Option([], "--extract", "-e", help=EXTRACT_HELP),
    sub: list[str] = typer.Option([], "--sub", "-s", help=SUB_HELP),
) -> None:
    """Create a workspace from a mother file and run the initial split."""
    _need_file(source)
    selections = _build_selections(extract, sub, _options_for_deck(source))
    result = _call(service.create_workspace, _workspace_name(name), source.name, source, selections)
    console.print(f"\n[bold green]Workspace created[/bold green] → [cyan]{result['workspace']}[/cyan]\n")
    for filename in result["files"]:
        console.print(f"  {filename}")


@ws_app.command("status")
def workspace_status(name: str = typer.Argument(..., help="Workspace name (or folder path)")) -> None:
    """Show a workspace's files and whether any were changed since FileFold wrote them."""
    data = _call(service.get_workspace, _workspace_name(name))
    console.print(f"\n[bold]{data['name']}[/bold]  [dim]source: {data['source_name']}   updated: {data['updated_at']}[/dim]\n")
    table = Table(show_header=True, header_style="bold")
    for col in ("file", "role", "category", "lines", "state"):
        table.add_column(col)
    for f in data["files"]:
        state = ("[red]missing[/red]" if not f["exists"]
                 else "[yellow]edited[/yellow]" if f["manually_edited"] else "[green]clean[/green]")
        table.add_row(f["filename"], f["role"], f["category"] or "", "" if f["line_count"] is None else f"{f['line_count']:,}", state)
    console.print(table)


@ws_app.command("options")
def workspace_options(name: str = typer.Argument(..., help="Workspace name (or folder path)")) -> None:
    """List the categories and finer splits still available in a workspace."""
    data = _call(service.get_workspace, _workspace_name(name))
    extracted = {s["category"] for s in data["selections"]}
    console.print("[bold]Categories[/bold]  [dim](extracted ones marked)[/dim]")
    for cat in data["available_categories"]:
        console.print(f"  {cat}{'  [green]extracted[/green]' if cat in extracted else ''}")
    console.print("\n[bold]Finer splits[/bold]  [dim](use with -s CATEGORY:KEY)[/dim]\n")
    _print_options(data["sub_options"])


@ws_app.command("extract")
def workspace_extract(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"),
    extract: list[str] = typer.Option([], "--extract", "-e", help=EXTRACT_HELP),
    sub: list[str] = typer.Option([], "--sub", "-s", help=SUB_HELP),
) -> None:
    """Extract more categories from the workspace's mother file."""
    name = _workspace_name(name)
    options = _call(service.get_workspace, name)["sub_options"]
    selections = _build_selections(extract, sub, options)
    if not selections:
        raise _fail("Nothing to extract: pass -e CATEGORY and/or -s CATEGORY:KEY")
    result = _call(service.extract_splits, name, selections)
    console.print(f"\n[bold green]Extracted[/bold green] {', '.join(result['extracted']) or 'nothing new'}")


@ws_app.command("resplit")
def workspace_resplit(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"),
    category: str = typer.Argument(..., help="An already-extracted category"),
    sub: list[str] = typer.Option([], "--sub", "-s", help=SUB_HELP + " With none given, every sub-file is folded back."),
) -> None:
    """Change the finer splits inside an extracted category (it is recombined, then re-split)."""
    name = _workspace_name(name)
    category = category.lower()
    options = _call(service.get_workspace, name)["sub_options"]
    chosen = _build_selections([], sub, options)
    wrong = [s["category"] for s in chosen if s["category"] != category]
    if wrong:
        raise _fail(f"All --sub options must be for {category!r}, got {wrong[0]!r}")
    subs = chosen[0]["sub_selections"] if chosen else []
    result = _call(service.resplit_child, name, category, subs)
    shown = ", ".join(result["sub_extracted"]) or "none (all folded back)"
    console.print(f"\n[bold green]{category} re-split[/bold green]: {shown}")


@ws_app.command("rename-file")
def workspace_rename_file(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"),
    old: str = typer.Argument(...), new: str = typer.Argument(...),
) -> None:
    """Rename a child file (the *INCLUDE in its parent is updated)."""
    result = _call(service.rename_file, _workspace_name(name), old, new)
    console.print(f"[bold green]Renamed[/bold green] → {result['renamed']}")


@ws_app.command("recombine")
def workspace_recombine(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"),
    files: list[str] = typer.Argument(..., help="Child or sub-child files to fold back into their parent"),
) -> None:
    """Fold files back into their parent file (the reverse of a split)."""
    result = _call(service.recombine, _workspace_name(name), files)
    console.print(f"[bold green]Recombined[/bold green] {', '.join(result['recombined'])}")


@ws_app.command("rename")
def workspace_rename(
    name: str = typer.Argument(..., help="Workspace name"), new_name: str = typer.Argument(...),
) -> None:
    """Rename a workspace."""
    result = _call(service.rename_workspace, name, new_name)
    console.print(f"[bold green]Renamed[/bold green] → {result['workspace']}")


@ws_app.command("delete")
def workspace_delete(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation"),
) -> None:
    """Delete a workspace and all its files."""
    name = _workspace_name(name)
    if not yes:
        typer.confirm(f"Delete workspace {name!r}? This cannot be undone.", abort=True)
    _call(service.delete_workspace, name)
    console.print(f"[bold green]Deleted[/bold green] {name}")


@ws_app.command("export")
def workspace_export(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"),
    output: Path = typer.Option(None, "--output", "-o", help="Zip file to write (default: NAME.zip)"),
) -> None:
    """Export every file of a workspace as a ZIP archive."""
    name = _workspace_name(name)
    data = _call(service.export_zip, name)
    target = output or Path(f"{name}.zip")
    target.write_bytes(data)
    console.print(f"[bold green]Exported[/bold green] → {target}  [dim]({len(data) / 1048576:.1f} MB)[/dim]")


@ws_app.command("cat")
def workspace_cat(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"), file: str = typer.Argument(...),
) -> None:
    """Print a workspace file exactly as stored (bytes unchanged, so it can be piped)."""
    sys.stdout.buffer.write(_call(service.read_file, _workspace_name(name), file))
    sys.stdout.buffer.flush()


@ws_app.command("put")
def workspace_put(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"),
    file: str = typer.Argument(..., help="Workspace file to overwrite"),
    source: str = typer.Argument(..., help="Local file with the new content, or - for standard input"),
) -> None:
    """Replace a workspace file's content (line endings are kept as given)."""
    data = sys.stdin.buffer.read() if source == "-" else Path(source).read_bytes()
    result = _call(service.write_file, _workspace_name(name), file, data)
    console.print(f"[bold green]Saved[/bold green] {result['saved']}")


@ws_app.command("reimport")
def workspace_reimport(
    name: str = typer.Argument(..., help="Workspace name (or folder path)"),
    new_source: Path = typer.Argument(..., help="New version of the mother .inp file"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite manually edited files too"),
    extract: list[str] = typer.Option([], "--extract", "-e", help="Also extract a category that is new in this file"),
) -> None:
    """Import a new mother file into an existing workspace."""
    _need_file(new_source)
    name = _workspace_name(name)
    preview = _call(service.reimport_preview, name, new_source.name, new_source)
    console.print(f"\n[bold]Reimport preview[/bold] — {new_source.name} → {name}\n")
    for s in preview["unchanged"]:
        console.print(f"  [dim]·  {s['filename']}  no change[/dim]")
    for s in preview["safe_to_update"]:
        console.print(f"  [green]↑  {s['filename']}  will update[/green]")
    for s in preview["needs_attention"]:
        verb = "will be overwritten" if force else "skipped"
        console.print(f"  [yellow]⚠  {s['filename']}  changed in the new file BUT manually edited — {verb}[/yellow]")
    if preview["needs_attention"] and not force:
        console.print("\n[dim]Use --force to overwrite manually edited files too.[/dim]")

    to_update = [s["filename"] for s in preview["safe_to_update"]]
    if force:
        to_update += [s["filename"] for s in preview["needs_attention"]]
    added = _build_selections(extract, [], {})
    _call(service.reimport_apply, name, new_source.name, new_source, to_update, added)
    console.print(f"\n[bold green]Done.[/bold green] {len(to_update)} child(ren) updated"
                  + (f", extracted {', '.join(a['category'] for a in added)}" if added else "") + ".")


# ---------------------------------------------------------------------------
# apps
# ---------------------------------------------------------------------------

@app.command()
def launch() -> None:
    """Launch the FileFold desktop app (requires the desktop extra: pip install filefold[desktop])."""
    try:
        from filefold.desktop.app import main as _main
    except ImportError:
        console.print("[red]PySide6 is not installed.[/red]")
        console.print("[dim]Install the desktop extra:  pip install filefold[desktop][/dim]")
        raise typer.Exit(1)
    _main([])


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", envvar="FILEFOLD_HOST", help="Bind address"),
    port: int = typer.Option(8000, "--port", "-p", envvar="PORT", help="Port number"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (dev mode)"),
) -> None:
    """Start the FileFold web server."""
    import uvicorn
    console.print(f"\n[bold green]FileFold[/bold green] web UI → [cyan]http://{host}:{port}[/cyan]\n")
    uvicorn.run("filefold.api.main:app", host=host, port=port, reload=reload)
