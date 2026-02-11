"""TUI command for Haven CLI.

This module provides the `haven tui` command for launching
the Terminal User Interface.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from haven_cli.cli.exit_codes import ExitCode

app = typer.Typer(help="Launch the Terminal User Interface.")
console = Console()


@app.callback(invoke_without_command=True)
def tui(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to TUI configuration file.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    """Launch the Haven Terminal User Interface.
    
    The TUI provides a visual interface for monitoring and controlling
the Haven video pipeline. It displays real-time progress, speeds,
    and status information for all videos in the pipeline.
    
    Examples:
        Launch TUI with default settings:
            $ haven tui
        
        Launch TUI with custom configuration:
            $ haven tui --config ~/.config/haven/tui.toml
    """
    # Avoid running if a subcommand was invoked
    if ctx.invoked_subcommand is not None:
        return
    
    # Check if TUI dependencies are available
    try:
        from textual.app import App  # noqa: F401
    except ImportError:
        console.print(
            "[red]Error: TUI dependencies not installed.[/red]\n"
            "Install with: [cyan]pip install 'haven-cli[tui]'[/cyan]"
        )
        raise typer.Exit(code=ExitCode.MISSING_DEPENDENCY)
    
    # Import and launch the TUI
    from haven_tui.app import HavenTUIApp
    
    try:
        tui_app = HavenTUIApp(config_path=str(config) if config else None)
        tui_app.run()
    except Exception as e:
        console.print(f"[red]Error launching TUI: {e}[/red]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=ExitCode.RUNTIME_ERROR)
