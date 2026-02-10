"""Salesforce ADK Agent Engine Deployment CLI."""

from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

app = typer.Typer(help="Salesforce ADK Agent Engine Deployment Manager")


@app.callback()
def main(
    env_file: Annotated[
        Path | None, typer.Option("--env-file", help="Path to .env file to load")
    ] = None,
):
    """Salesforce ADK Agent Engine Deployment Manager."""
    if env_file:
        if not env_file.exists():
            typer.echo(f"Error: Environment file '{env_file}' not found.", err=True)
            raise typer.Exit(1)
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)


def _parse_labels(raw: list[str] | None) -> dict[str, str] | None:
    """Parse 'key=value' label pairs into a dict. Returns None if empty."""
    if not raw:
        return None
    labels: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            raise typer.BadParameter(
                f"Invalid label format: '{item}'. Expected key=value"
            )
        k, v = item.split("=", 1)
        labels[k] = v
    return labels


@app.command()
def create(
    display_name: Annotated[
        str | None, typer.Option(help="Display name for the agent")
    ] = None,
    description: Annotated[
        str | None, typer.Option(help="Description of the agent")
    ] = None,
    gcs_dir_name: Annotated[
        str | None, typer.Option(help="GCS folder name for staging artifacts")
    ] = None,
    label: Annotated[
        list[str] | None, typer.Option(help="Label in key=value format (repeatable)")
    ] = None,
    min_instances: Annotated[
        int | None, typer.Option(help="Minimum number of instances")
    ] = None,
    max_instances: Annotated[
        int | None, typer.Option(help="Maximum number of instances")
    ] = None,
):
    """Create a new Agent Engine deployment."""
    from deploy import DeploymentManager

    manager = DeploymentManager()
    typer.echo("Creating Agent Engine deployment...")
    remote_agent = manager.create(
        display_name=display_name,
        description=description,
        gcs_dir_name=gcs_dir_name,
        labels=_parse_labels(label),
        min_instances=min_instances,
        max_instances=max_instances,
    )
    typer.echo(f"Created: {remote_agent.api_resource.name}")


@app.command()
def update(
    resource_name: Annotated[
        str | None, typer.Option(help="Agent Engine resource name")
    ] = None,
    display_name: Annotated[str | None, typer.Option(help="New display name")] = None,
    description: Annotated[str | None, typer.Option(help="New description")] = None,
    gcs_dir_name: Annotated[
        str | None, typer.Option(help="GCS folder name for staging artifacts")
    ] = None,
    label: Annotated[
        list[str] | None, typer.Option(help="Label in key=value format (repeatable)")
    ] = None,
    min_instances: Annotated[
        int | None, typer.Option(help="Minimum number of instances")
    ] = None,
    max_instances: Annotated[
        int | None, typer.Option(help="Maximum number of instances")
    ] = None,
):
    """Update an existing Agent Engine deployment."""
    from deploy import DeploymentManager

    manager = DeploymentManager()
    typer.echo("Updating Agent Engine deployment...")
    remote_agent = manager.update(
        resource_name=resource_name,
        display_name=display_name,
        description=description,
        gcs_dir_name=gcs_dir_name,
        labels=_parse_labels(label),
        min_instances=min_instances,
        max_instances=max_instances,
    )
    typer.echo(f"Updated: {remote_agent.api_resource.name}")


@app.command()
def delete(
    resource_name: Annotated[
        str | None, typer.Option(help="Agent Engine resource name")
    ] = None,
    force: Annotated[bool, typer.Option(help="Force deletion")] = True,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip confirmation")] = False,
):
    """Delete an Agent Engine deployment."""
    from deploy import DeploymentManager

    if not yes:
        typer.confirm("Are you sure you want to delete this deployment?", abort=True)

    manager = DeploymentManager()
    typer.echo("Deleting Agent Engine deployment...")
    manager.delete(resource_name=resource_name, force=force)
    typer.echo("Deleted successfully.")


@app.command()
def get(
    resource_name: Annotated[
        str | None, typer.Option(help="Agent Engine resource name")
    ] = None,
):
    """Get Agent Engine deployment details."""
    from deploy import DeploymentManager

    manager = DeploymentManager()
    remote_agent = manager.get(resource_name=resource_name)
    typer.echo(f"Name: {remote_agent.api_resource.name}")
    typer.echo(f"Display Name: {remote_agent.api_resource.display_name}")
    typer.echo(f"State: {remote_agent.api_resource.state}")
    typer.echo(f"Create Time: {remote_agent.api_resource.create_time}")
    typer.echo(f"Update Time: {remote_agent.api_resource.update_time}")


@app.command("list")
def list_agents(
    filter: Annotated[str, typer.Option(help="Filter expression")] = "",
):
    """List Agent Engine deployments."""
    from deploy import DeploymentManager

    manager = DeploymentManager()
    agents = manager.list(filter_str=filter)
    if not agents:
        typer.echo("No deployments found.")
        return
    for agent in agents:
        typer.echo(f"  {agent.api_resource.name} - {agent.api_resource.display_name}")


if __name__ == "__main__":
    app()
