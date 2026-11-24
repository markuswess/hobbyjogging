"""Path configuration for importers."""

import os
from pathlib import Path

FIT_DIR_ENV = "HOBBYJOGGING_FIT_DIR"
DEFAULT_FIT_DIR = Path("data/fit")

GARMIN_DIR_NAME = "garmin"
GARMIN_API_KEY_ENV = "GARMIN_PERSONAL_API_KEY"
GARMIN_API_KEY_FALLBACK_ENV = "GARMIN_API_KEY"
GARMIN_BASE_URL_ENV = "GARMIN_PERSONAL_API_BASE_URL"
DEFAULT_GARMIN_BASE_URL = "https://personal.connectapi.garmin.com"
GARMIN_TOKEN_CACHE_ENV = "GARMIN_BEARER_TOKEN_CACHE_FILE"
DEFAULT_GARMIN_TOKEN_CACHE = (
    Path("~/.config/garmin/connect-personal-api-bearer-token.json")
)

RUNALYZE_API_KEY_ENV = "RUNALYZE_API_KEY"
RUNALYZE_API_KEY_FALLBACK_ENV = "RUNALYZE_TOKEN"
RUNALYZE_BASE_URL_ENV = "RUNALYZE_API_BASE_URL"
DEFAULT_RUNALYZE_BASE_URL = "https://runalyze.com/api/v1"

INTERVALS_ATHLETE_ID_ENV = "INTERVALS_ATHLETE_ID"
INTERVALS_API_KEY_ENV = "INTERVALS_API_KEY"


def default_fit_dir() -> Path:
    """Return the configured FIT directory, falling back to data/fit."""
    value = os.environ.get(FIT_DIR_ENV)
    return Path(value).expanduser() if value else DEFAULT_FIT_DIR


def default_garmin_dir() -> Path:
    """Return the directory fetched Garmin FITs are written to."""
    return default_fit_dir() / GARMIN_DIR_NAME


def garmin_api_key() -> str | None:
    """Return the Garmin Personal API key from the environment."""
    value = os.environ.get(GARMIN_API_KEY_ENV) or os.environ.get(
        GARMIN_API_KEY_FALLBACK_ENV
    )
    value = (value or "").strip()
    return value or None


def garmin_base_url() -> str:
    """Return the Garmin Personal API base URL."""
    value = os.environ.get(GARMIN_BASE_URL_ENV)
    return (value or DEFAULT_GARMIN_BASE_URL).rstrip("/")


def garmin_token_cache_path() -> Path:
    """Return the bearer-token cache path, shared with Garmin's own client."""
    value = os.environ.get(GARMIN_TOKEN_CACHE_ENV)
    return Path(value).expanduser() if value else DEFAULT_GARMIN_TOKEN_CACHE


def runalyze_api_key() -> str | None:
    """Return the Runalyze personal API token from the environment."""
    value = (
        os.environ.get(RUNALYZE_API_KEY_ENV)
        or os.environ.get(RUNALYZE_API_KEY_FALLBACK_ENV)
    )
    value = (value or "").strip()
    return value or None


def runalyze_base_url() -> str:
    """Return the Runalyze API base URL."""
    value = os.environ.get(RUNALYZE_BASE_URL_ENV)
    return (value or DEFAULT_RUNALYZE_BASE_URL).rstrip("/")


def intervals_credentials() -> tuple[str | None, str | None]:
    """Return ``(athlete_id, api_key)``; either may be missing."""
    athlete_id = (os.environ.get(INTERVALS_ATHLETE_ID_ENV) or "").strip()
    api_key = (os.environ.get(INTERVALS_API_KEY_ENV) or "").strip()
    return athlete_id or None, api_key or None


def resolve_fit_path(value: str | Path) -> Path:
    """Resolve a FIT path, falling back to the configured FIT directory."""
    path = Path(value).expanduser()

    if path.is_file() or path.is_absolute():
        return path

    candidate = default_fit_dir() / path
    return candidate if candidate.is_file() else path
