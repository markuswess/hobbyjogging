"""SQLite connections and database-path configuration."""

import os
import sqlite3
from pathlib import Path

from .migrations import migrate

DATABASE_PATH_ENV = "HOBBYJOGGING_DB"
DEFAULT_DATABASE_PATH = (
    Path.home() / "projects/laufen_private/data/db/hobbyjogging.db"
)


def default_database_path() -> Path:
    value = os.environ.get(DATABASE_PATH_ENV)
    return Path(value).expanduser() if value else DEFAULT_DATABASE_PATH


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a SQLite connection with the project's standard pragmas."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def open_database(path: str | Path | None = None) -> sqlite3.Connection:
    """Open and migrate a database, creating its parent directory if needed."""
    if path is None:
        path = default_database_path()

    if str(path) == ":memory:":
        conn = connect(":memory:")
    else:
        database_path = Path(path).expanduser()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(database_path)

    migrate(conn)
    return conn
