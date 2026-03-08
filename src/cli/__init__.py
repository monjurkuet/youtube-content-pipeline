"""Main CLI entry point for Transcription Pipeline."""

from pathlib import Path

import typer

from src.core.logging_config import get_logger, setup_logging
from src.cli.commands.cookie import cookie_app
from src.cli.commands.channel import channel_app
from src.cli.commands.transcription import transcription_app, transcribe, batch
from src.cli.commands.utils import utils_app, check_dependencies

app = typer.Typer(help="Transcription Pipeline - Get transcripts and save to DB")

# Add sub-command apps
app.add_typer(channel_app, name="channel")
app.add_typer(cookie_app, name="cookie")
app.add_typer(transcription_app, name="transcript")
app.add_typer(utils_app, name="utils")

# Add core commands directly to main app for convenience
app.command(name="transcribe")(transcribe)
app.command(name="batch")(batch)
app.command(name="check-dependencies")(check_dependencies)

log = get_logger("cli")


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Enable verbose logging"),
    log_file: Path | None = typer.Option(None, help="Log file path"),
):
    """
    Transcription Pipeline - Get transcripts and save to DB.

    Set up logging configuration before running commands.
    """
    setup_logging(level="DEBUG" if verbose else "INFO", log_file=log_file)


if __name__ == "__main__":
    app()
