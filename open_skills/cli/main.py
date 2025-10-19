"""
CLI tool for open-skills.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from open_skills.core.packing import (
    parse_skill_bundle,
    validate_skill_bundle,
    create_skill_template,
)
from open_skills.core.executor import SkillExecutor
from open_skills.db.models import SkillVersion
from open_skills import __version__

console = Console()


@click.group()
@click.version_option(version=__version__)
def cli():
    """open-skills - A modular Skills subsystem for agent frameworks."""
    pass


@cli.command()
@click.argument("name")
@click.argument("output_path", type=click.Path(), required=False)
def init(name: str, output_path: Optional[str]):
    """
    Initialize a new skill bundle template.

    Args:
        name: Skill name
        output_path: Output directory (defaults to ./<name>)
    """
    try:
        if not output_path:
            output_path = f"./{name}"

        output = Path(output_path)

        console.print(f"[bold]Creating skill template:[/bold] {name}")
        console.print(f"[dim]Output path:[/dim] {output.absolute()}")

        create_skill_template(output, name)

        console.print(f"\n[green]✓[/green] Skill template created successfully!")
        console.print("\n[bold]Next steps:[/bold]")
        console.print(f"  1. cd {output}")
        console.print("  2. Edit SKILL.md and scripts/main.py")
        console.print("  3. open-skills validate .")
        console.print("  4. open-skills publish .")

    except FileExistsError as e:
        console.print(f"[red]Error:[/red] {e}", style="bold red")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Failed to create skill template:[/red] {e}")
        raise click.Abort()


@cli.command()
@click.argument("bundle_path", type=click.Path(exists=True))
def validate(bundle_path: str):
    """
    Validate a skill bundle.

    Args:
        bundle_path: Path to skill bundle directory
    """
    try:
        path = Path(bundle_path)
        console.print(f"[bold]Validating skill bundle:[/bold] {path.absolute()}")

        bundle = parse_skill_bundle(path)

        # Display results
        console.print("\n[green]✓ Skill bundle is valid![/green]\n")

        # Show metadata
        table = Table(title="Skill Metadata")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Name", bundle.metadata.get("name", "N/A"))
        table.add_row("Version", bundle.metadata.get("version", "N/A"))
        table.add_row("Entrypoint", bundle.metadata.get("entrypoint", "N/A"))
        table.add_row("Tags", ", ".join(bundle.metadata.get("tags", [])))
        table.add_row("Allow Network", str(bundle.metadata.get("allow_network", False)))

        console.print(table)

        if bundle.description_md:
            console.print(f"\n[bold]Description:[/bold]")
            console.print(Panel(bundle.description_md[:200] + "..." if len(bundle.description_md) > 200 else bundle.description_md))

    except Exception as e:
        console.print(f"\n[red]✗ Validation failed:[/red] {e}")
        raise click.Abort()


@cli.command()
@click.argument("bundle_path", type=click.Path(exists=True))
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--timeout", type=int, default=60, help="Execution timeout in seconds")
def run_local(bundle_path: str, input_file: str, timeout: int):
    """
    Run a skill locally without uploading to server.

    Args:
        bundle_path: Path to skill bundle directory
        input_file: Path to JSON file with input data
        timeout: Execution timeout in seconds
    """
    async def _run():
        try:
            bundle = parse_skill_bundle(Path(bundle_path))
            console.print(f"[bold]Running skill:[/bold] {bundle.metadata.get('name')}")

            # Load input
            with open(input_file, "r") as f:
                input_data = json.load(f)

            console.print(f"[dim]Input:[/dim] {json.dumps(input_data, indent=2)}")

            # Create a mock SkillVersion for local execution
            from open_skills.db.base import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                # Create mock version
                version = SkillVersion(
                    id="00000000-0000-0000-0000-000000000000",  # Mock ID
                    skill_id="00000000-0000-0000-0000-000000000000",  # Mock ID
                    version=bundle.metadata.get("version", "0.0.0"),
                    entrypoint=bundle.metadata.get("entrypoint"),
                    description=bundle.metadata.get("description"),
                    metadata_yaml=bundle.metadata,
                    bundle_path=str(Path(bundle_path).absolute()),
                    is_published=False,
                )

                executor = SkillExecutor(db)

                console.print("\n[yellow]Executing...[/yellow]\n")

                result = await executor.execute_one(
                    version,
                    input_data,
                    timeout_seconds=timeout,
                )

                # Display results
                console.print("[green]✓ Execution completed![/green]\n")

                console.print(f"[bold]Status:[/bold] {result['status']}")
                console.print(f"[bold]Duration:[/bold] {result['duration_ms']}ms")

                if result.get("outputs"):
                    console.print("\n[bold]Outputs:[/bold]")
                    console.print(json.dumps(result["outputs"], indent=2))

                if result.get("artifacts"):
                    console.print("\n[bold]Artifacts:[/bold]")
                    for artifact in result["artifacts"]:
                        console.print(f"  - {artifact.get('filename', 'unknown')}")

                if result.get("logs"):
                    console.print("\n[bold]Logs:[/bold]")
                    console.print(Panel(result["logs"]))

        except Exception as e:
            console.print(f"\n[red]✗ Execution failed:[/red] {e}")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise click.Abort()

    asyncio.run(_run())


@cli.command()
@click.option("--host", default="0.0.0.0", help="Server host")
@click.option("--port", default=8000, help="Server port")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def serve(host: str, port: int, reload: bool):
    """
    Start the open-skills API server.

    Args:
        host: Server host
        port: Server port
        reload: Enable auto-reload for development
    """
    import uvicorn

    console.print("[bold]Starting open-skills server...[/bold]")
    console.print(f"[dim]Host:[/dim] {host}")
    console.print(f"[dim]Port:[/dim] {port}")
    console.print(f"[dim]Reload:[/dim] {reload}")
    console.print(f"\n[green]Server running at:[/green] http://{host}:{port}")
    console.print(f"[green]API docs:[/green] http://{host}:{port}/docs\n")

    uvicorn.run(
        "open_skills.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@cli.command()
@click.argument("bundle_path", type=click.Path(exists=True))
@click.option("--server", default="http://localhost:8000", help="Server URL")
@click.option("--skill-id", help="Skill ID (if updating existing skill)")
def publish(bundle_path: str, server: str, skill_id: Optional[str]):
    """
    Publish a skill bundle to the server (stub - requires server integration).

    Args:
        bundle_path: Path to skill bundle directory
        server: Server URL
        skill_id: Optional skill ID for updates
    """
    console.print("[yellow]Note:[/yellow] This command is a stub.")
    console.print("To publish a skill:")
    console.print(f"  1. Validate: open-skills validate {bundle_path}")
    console.print(f"  2. Create a zip: zip -r skill.zip {bundle_path}")
    console.print(f"  3. Upload via API: POST {server}/api/skills/{{id}}/versions")
    console.print("\nSee documentation for full publishing workflow.")


if __name__ == "__main__":
    cli()
