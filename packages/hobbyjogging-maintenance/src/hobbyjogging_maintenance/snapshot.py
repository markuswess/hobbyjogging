"""Timestamped database snapshots taken before a real maintenance run.

``VACUUM INTO`` gives a compact, consistent copy beside the live database. It
protects the minutes around one task, not the machine: the periodic backup is
still the durable copy. A dry run writes nothing, not even a snapshot.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_PREFIX = ".bak-"
KEEP_SNAPSHOTS = 5


def database_path(connection: sqlite3.Connection) -> Path | None:
    """Return the on-disk path of the main database, or ``None`` in memory."""
    for row in connection.execute("PRAGMA database_list").fetchall():
        if row[1] == "main" and row[2]:
            return Path(row[2])
    return None


def create_snapshot(connection: sqlite3.Connection) -> Path | None:
    """Write one pre-run snapshot and prune to the last five.

    Returns ``None`` for an in-memory database (nothing to copy). A snapshot
    failure raises, so a real run cannot silently proceed without its restore
    point.
    """
    source = database_path(connection)
    if source is None:
        return None

    path = _next_path(source)
    # Use a separate connection so an open transaction on the live connection
    # neither blocks the copy nor has to be committed first.
    copy = sqlite3.connect(source, timeout=5.0)
    try:
        copy.execute("VACUUM INTO ?", (str(path),))
    finally:
        copy.close()

    _prune(source)
    return path


def _next_path(source: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = Path(f"{source}{SNAPSHOT_PREFIX}{stamp}")
    if not candidate.exists():
        return candidate
    for index in range(1, 100):
        candidate = Path(
            f"{source}{SNAPSHOT_PREFIX}{stamp}-{index:02d}"
        )
        if not candidate.exists():
            return candidate
    raise OSError(f"cannot find a free snapshot name for {source}")


def _prune(source: Path) -> None:
    pattern = f"{source.name}{SNAPSHOT_PREFIX}*"
    snapshots = sorted(
        path for path in source.parent.glob(pattern) if path.is_file()
    )
    for old in snapshots[:-KEEP_SNAPSHOTS]:
        try:
            old.unlink()
        except OSError:
            # A snapshot we cannot remove is not a reason to fail the task.
            continue
