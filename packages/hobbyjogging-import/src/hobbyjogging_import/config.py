"""Path configuration for importers."""

import os
from pathlib import Path

FIT_DIR_ENV = "HOBBYJOGGING_FIT_DIR"
DEFAULT_FIT_DIR = Path("data/fit")


def default_fit_dir() -> Path:
    """Return the configured FIT directory, falling back to data/fit."""
    value = os.environ.get(FIT_DIR_ENV)
    return Path(value).expanduser() if value else DEFAULT_FIT_DIR


def resolve_fit_path(value: str | Path) -> Path:
    """Resolve a FIT path, falling back to the configured FIT directory."""
    path = Path(value).expanduser()

    if path.is_file() or path.is_absolute():
        return path

    candidate = default_fit_dir() / path
    return candidate if candidate.is_file() else path
