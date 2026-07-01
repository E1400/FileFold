from pathlib import Path

import typer
from rich.console import Console
from rich.tree import Tree

from filefold.core.block import Block
from filefold.core.parser import parse
from filefold.core.splitter import split as split_blocks

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
