"""CLI wrapper for the Business Card Extractor API."""

from __future__ import annotations

import json
import sys

import click
import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


@click.group()
@click.option("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
@click.pass_context
def cli(ctx: click.Context, base_url: str) -> None:
    """Business Card Extractor CLI."""
    ctx.ensure_object(dict)
    ctx.obj["base_url"] = base_url.rstrip("/")


@cli.command()
@click.option("--drive-folder-id", default=None, help="Google Drive folder ID")
@click.option("--local-folder", default=None, help="Path to local image folder")
@click.option("--sheet-id", default=None, help="Google Sheets spreadsheet ID")
@click.option("--sheet-name", default=None, help="Sheet tab name")
@click.option("--model", default=None, help="OpenRouter model override")
@click.option("--max-files", type=int, default=200, help="Max files to process")
@click.option("--concurrency", type=int, default=3, help="Parallel workers")
@click.option("--dry-run", is_flag=True, help="Skip Sheets append")
@click.pass_context
def batch(ctx: click.Context, **kwargs: object) -> None:
    """Run batch extraction."""
    base = ctx.obj["base_url"]

    payload = {}
    if kwargs.get("drive_folder_id"):
        payload["driveFolderId"] = kwargs["drive_folder_id"]
    if kwargs.get("local_folder"):
        payload["localFolderPath"] = kwargs["local_folder"]
    if kwargs.get("sheet_id"):
        payload["sheetId"] = kwargs["sheet_id"]
    if kwargs.get("sheet_name"):
        payload["sheetName"] = kwargs["sheet_name"]
    if kwargs.get("model"):
        payload["model"] = kwargs["model"]
    payload["maxFiles"] = kwargs.get("max_files", 200)
    payload["concurrency"] = kwargs.get("concurrency", 3)
    payload["dryRun"] = bool(kwargs.get("dry_run"))

    click.echo(f"→ POST {base}/batch/folder")
    try:
        resp = httpx.post(f"{base}/batch/folder", json=payload, timeout=600.0)
        resp.raise_for_status()
        data = resp.json()
        click.echo(json.dumps(data, indent=2))
    except httpx.HTTPStatusError as exc:
        click.echo(f"Error {exc.response.status_code}: {exc.response.text}", err=True)
        sys.exit(1)
    except httpx.RequestError as exc:
        click.echo(f"Connection error: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def models(ctx: click.Context) -> None:
    """List available OpenRouter models."""
    base = ctx.obj["base_url"]
    try:
        resp = httpx.get(f"{base}/models", timeout=10.0)
        resp.raise_for_status()
        click.echo(json.dumps(resp.json(), indent=2))
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
