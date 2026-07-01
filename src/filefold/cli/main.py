from pathlib import Path

import typer
from rich.console import Console
from rich.tree import Tree

from filefold.core.block import Block
from filefold.core.parser import parse

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
