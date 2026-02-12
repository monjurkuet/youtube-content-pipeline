"""Entry point for running the package as a module."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.cli import app

if __name__ == "__main__":
    app()
