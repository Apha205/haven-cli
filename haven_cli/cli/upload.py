"""Haven upload command - Upload file to Filecoin."""

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="""Upload files to Filecoin network.
    
Creates Arkiv entities with standardized data format compatible with
haven-player (Gold Standard) and haven-dapp.

Key Fields:
  • filecoin_root_cid - CID on Filecoin (private payload)
  • is_encrypted - Encryption status
  • cid_hash - SHA256 hash for duplicate detection
  • vlm_json_cid - VLM analysis CID

For format details: haven-cli/docs/ARKIV_FORMAT.md
""",
    no_args_is_help=True,
)
console = Console()


@app.command(name="file")
def upload(
    file_path: Path = typer.Argument(
        ...,
        help="Path to the file to upload.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    encrypt: bool = typer.Option(
        False,
        "--encrypt",
        "-e",
        help="Encrypt file with Lit Protocol before upload.",
    ),
    skip_vlm: bool = typer.Option(
        False,
        "--no-vlm",
        help="Skip VLM analysis step.",
    ),
    dataset_id: Optional[int] = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Dataset ID for Filecoin upload.",
    ),
    skip_arkiv: bool = typer.Option(
        False,
        "--no-arkiv",
        help="Skip Arkiv blockchain sync.",
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file.",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        "-t",
        help="Video title (defaults to filename).",
    ),
    creator: Optional[str] = typer.Option(
        None,
        "--creator",
        help="Creator handle/channel identifier (e.g., @username).",
    ),
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help="Original source URL for provenance tracking.",
    ),
) -> None:
    """Upload a file to Filecoin network.
    
    This command processes a single file through the pipeline:
    1. Ingest - Calculate pHash, create database entry
    2. Analyze - VLM analysis (optional, skip with --no-vlm)
    3. Encrypt - Lit Protocol encryption (optional, enable with --encrypt)
    4. Upload - Upload to Filecoin network
    5. Sync - Sync metadata to Arkiv blockchain (optional, skip with --no-arkiv)
    
    The created Arkiv entity uses the Haven Cross-Application Data Format v1.0.0,
    ensuring compatibility with haven-player (Gold Standard) and haven-dapp.
    
    Key entity fields:
    • filecoin_root_cid - CID of video on Filecoin (private payload)
    • is_encrypted - Encryption status (boolean in payload, 0/1 in attributes)
    • cid_hash - SHA256 hash for duplicate detection (payload & attributes)
    • vlm_json_cid - CID of VLM analysis JSON (private payload)
    • lit_encryption_metadata - Lit Protocol metadata (private payload)
    
    Example:
        haven upload file video.mp4
        haven upload file video.mp4 --encrypt --dataset 123
        haven upload file video.mp4 --no-vlm --no-arkiv
        haven upload file video.mp4 --title "My Video" --creator "@user" --source "https://example.com"
    """
    import asyncio

    from haven_cli.config import load_config
    from haven_cli.pipeline.context import PipelineContext
    from haven_cli.pipeline.manager import create_default_pipeline

    config = load_config(config_file)
    
    console.print(f"[bold]Uploading:[/bold] {file_path.name}")
    
    # Get pipeline config values (PipelineConfig object uses attributes)
    pipeline_config = config.pipeline if config else None
    
    # Build pipeline options - CLI flags override config file settings
    # For conditional steps, we check both CLI flags and config settings
    def get_config_value(name, default):
        if pipeline_config is None:
            return default
        return getattr(pipeline_config, name, default)
    
    vlm_enabled = get_config_value("vlm_enabled", False) and not skip_vlm
    encryption_enabled = get_config_value("encryption_enabled", False) or encrypt
    upload_enabled = get_config_value("upload_enabled", True)
    sync_enabled = get_config_value("sync_enabled", False) and not skip_arkiv
    cleanup_enabled = get_config_value("cleanup_enabled", False)
    
    options = {
        "encrypt": encryption_enabled,
        "vlm_enabled": vlm_enabled,
        "upload_enabled": upload_enabled,
        "arkiv_sync_enabled": sync_enabled,
        "cleanup_enabled": cleanup_enabled,
        "dataset_id": dataset_id,
        "title": title,
        "creator_handle": creator,
        "source_uri": source,
    }
    
    # Create pipeline context
    context = PipelineContext(
        source_path=file_path,
        options=options,
    )
    
    # Initialize pipeline manager with all default steps
    pipeline_manager = create_default_pipeline(config=config.__dict__ if config else None)
    
    async def run_pipeline() -> None:
        from haven_cli.js_runtime.manager import JSBridgeManager
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing...", total=None)
            
            try:
                # Process through pipeline
                result = await pipeline_manager.process(context)
                
                progress.update(task, completed=True)
                
                if result.success:
                    console.print(f"[green]✓[/green] Upload complete: {result.cid or 'N/A'}")
                else:
                    console.print(f"[red]✗[/red] Upload failed: {result.error}")
                    raise typer.Exit(code=1)
            finally:
                # CRITICAL: Shutdown JS Bridge Manager to prevent hang
                # The background health check task keeps the event loop alive
                logger.debug("Shutting down JS Bridge Manager...")
                await JSBridgeManager.get_instance().shutdown()
    
    # Run the async pipeline
    asyncio.run(run_pipeline())
