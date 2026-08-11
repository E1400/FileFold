from pathlib import Path

import typer
from rich.console import Console
from rich.tree import Tree

from filefold.core.block import Block
from filefold.core.parser import parse
from filefold.core.keywords import Category
from filefold.core.splitter import SplitSelection, read_raw, split as split_blocks, split_with_includes
from filefold.core.workspace import Workspace

app = typer.Typer(help="FileFold — Abaqus .inp file organizer", no_args_is_help=True)
console = Console()


@app.callback()
def _root() -> None:
    """FileFold — Abaqus .inp file organizer."""


def _add_block(parent: Tree, block: Block) -> None:
    label = (
        f"[bold cyan]{block.keyword}[/bold cyan]"
        f"  [dim]{block.category.value}[/dim]"
        f"  [yellow]lines {block.line_start}–{block.line_end}[/yellow]"
    )
    node = parent.add(label)
    for child in block.children:
        _add_block(node, child)


@app.command()
def inspect(file: Path = typer.Argument(..., help="Path to the .inp file")) -> None:
    """Print a categorized tree of blocks in an Abaqus .inp file."""
    if not file.exists():
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(1)

    blocks = parse(file)

    tree = Tree(f"[bold]{file.name}[/bold]  [dim]{len(blocks)} top-level blocks[/dim]")
    for block in blocks:
        _add_block(tree, block)

    console.print(tree)


@app.command()
def split(
    file: Path = typer.Argument(..., help="Path to the .inp file"),
    output_dir: Path = typer.Argument(..., help="Directory to write split files into"),
) -> None:
    """Split an Abaqus .inp file into categorized part files."""
    if not file.exists():
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(1)

    blocks = parse(file)
    written = split_blocks(blocks, file, output_dir)

    console.print(f"\n[bold green]Split complete[/bold green] — {len(written)} files written to [cyan]{output_dir}[/cyan]\n")
    for path in written:
        console.print(f"  [dim]{path.relative_to(output_dir)}[/dim]")


# Valid category names for the split-partial command
_CATEGORY_MAP: dict[str, Category] = {c.value: c for c in Category}


@app.command(name="split-partial")
def split_partial(
    file: Path = typer.Argument(..., help="Path to the .inp file"),
    output_dir: Path = typer.Argument(..., help="Directory to write output files into"),
    extract: list[str] = typer.Option(
        ..., "--extract", "-e",
        help="Category to extract (repeatable). E.g. -e mesh -e material",
    ),
) -> None:
    """Extract selected categories into child files with *INCLUDE pointers in the mother."""
    if not file.exists():
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(1)

    selections: list[SplitSelection] = []
    for name in extract:
        cat = _CATEGORY_MAP.get(name.lower())
        if cat is None:
            valid = ", ".join(_CATEGORY_MAP)
            console.print(f"[red]Unknown category:[/red] {name!r}. Valid: {valid}")
            raise typer.Exit(1)
        selections.append(SplitSelection(category=cat, filename=f"{name.lower()}.inp"))

    blocks = parse(file)
    result = split_with_includes(blocks, file, output_dir, selections)

    console.print(f"\n[bold green]Split complete[/bold green] → [cyan]{output_dir}[/cyan]\n")
    console.print(f"  [bold]{result.mother_path.name}[/bold]  [dim](mother with *INCLUDE lines)[/dim]")
    for child in result.children:
        console.print(f"  [cyan]{child.filename}[/cyan]  [dim]{child.category.value}[/dim]  [dim]sha256:{child.sha256[:12]}…[/dim]")


# ---------------------------------------------------------------------------
# Workspace commands
# ---------------------------------------------------------------------------

ws_app = typer.Typer(help="Manage FileFold workspaces.", no_args_is_help=True)
app.add_typer(ws_app, name="workspace")


@ws_app.callback()
def _ws_root() -> None:
    """Manage FileFold workspaces."""


@ws_app.command("create")
def workspace_create(
    directory: Path = typer.Argument(..., help="Workspace directory to create"),
    source: Path = typer.Argument(..., help="Mother .inp file"),
    extract: list[str] = typer.Option(
        ..., "--extract", "-e",
        help="Category to extract (repeatable). E.g. -e mesh -e material",
    ),
) -> None:
    """Create a new workspace and run the initial split."""
    if not source.exists():
        console.print(f"[red]File not found:[/red] {source}")
        raise typer.Exit(1)

    selections: list[SplitSelection] = []
    for name in extract:
        cat = _CATEGORY_MAP.get(name.lower())
        if cat is None:
            console.print(f"[red]Unknown category:[/red] {name!r}. Valid: {', '.join(_CATEGORY_MAP)}")
            raise typer.Exit(1)
        selections.append(SplitSelection(category=cat, filename=f"{name.lower()}.inp"))

    ws = Workspace.create(directory, source, selections)
    console.print(f"\n[bold green]Workspace created[/bold green] → [cyan]{directory}[/cyan]\n")
    console.print(f"  [bold]{ws.source_name}[/bold]  [dim]mother (with *INCLUDE lines)[/dim]")
    for rec_name, rec in ws.file_records.items():
        if rec.role == "child":
            console.print(f"  [cyan]{rec_name}[/cyan]  [dim]{rec.category}[/dim]")


@ws_app.command("status")
def workspace_status(
    directory: Path = typer.Argument(..., help="Workspace directory"),
) -> None:
    """Show workspace files and their current state (hash match / manually edited)."""
    try:
        ws = Workspace.load(directory)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]{ws.name}[/bold]  [dim]source: {ws.source_name}[/dim]")
    console.print(f"[dim]updated: {ws.updated_at}[/dim]\n")

    for filename, rec in ws.file_records.items():
        current_path = directory / filename
        if not current_path.exists():
            status = "[red]missing[/red]"
        else:
            current_hash = __import__("hashlib").sha256(
                current_path.read_bytes()
            ).hexdigest()
            on_disk_hash = __import__("hashlib").sha256(
                read_raw(current_path)
                .encode("utf-8", errors="surrogateescape")
            ).hexdigest()
            if on_disk_hash == rec.sha256:
                status = "[green]unchanged[/green]"
            else:
                status = "[yellow]manually edited[/yellow]"
        label = f"[dim]{rec.category or rec.role}[/dim]"
        console.print(f"  {filename:<30} {label:<20} {status}")


@app.command()
def launch() -> None:
    """Launch the FileFold desktop app (requires the desktop extra: pip install filefold[desktop])."""
    try:
        from filefold.desktop.app import main as _main
    except ImportError:
        console.print("[red]PySide6 is not installed.[/red]")
        console.print("[dim]Install the desktop extra:  pip install filefold[desktop][/dim]")
        raise typer.Exit(1)
    _main()


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


@ws_app.command("reimport")
def workspace_reimport(
    directory: Path = typer.Argument(..., help="Workspace directory"),
    new_source: Path = typer.Argument(..., help="New version of the mother .inp file"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite manually edited files too"),
) -> None:
    """Import a new mother file into an existing workspace."""
    if not new_source.exists():
        console.print(f"[red]File not found:[/red] {new_source}")
        raise typer.Exit(1)
    try:
        ws = Workspace.load(directory)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    preview = ws.reimport_preview(new_source)

    console.print(f"\n[bold]Reimport preview[/bold] — {new_source.name} → {directory.name}\n")

    if preview.unchanged:
        for s in preview.unchanged:
            console.print(f"  [dim]·  {s.filename}  no change[/dim]")

    if preview.safe_to_update:
        for s in preview.safe_to_update:
            console.print(f"  [green]↑  {s.filename}  will update[/green]")

    if preview.needs_attention:
        for s in preview.needs_attention:
            console.print(f"  [yellow]⚠  {s.filename}  changed in new file BUT manually edited — skipped[/yellow]")
        if not force:
            console.print("\n[dim]Use --force to overwrite manually edited files.[/dim]")

    to_update = {s.filename for s in preview.safe_to_update}
    if force:
        to_update |= {s.filename for s in preview.needs_attention}

    if not to_update and not preview.safe_to_update:
        console.print("\n[dim]Nothing to update.[/dim]")
        return

    ws.reimport_apply(new_source, preview, to_update)
    console.print(f"\n[bold green]Done.[/bold green] {len(to_update)} child(ren) updated.")
