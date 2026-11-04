"""System clipboard access with generic tool fallback.

No Python clipboard dependency: try the usual command-line tools and give
up gracefully (the URL is always echoed, so the user can still copy it).
"""

from __future__ import annotations

import shutil
import subprocess

_TOOLS = (
    ("wl-copy", []),
    ("xclip", ["-selection", "clipboard"]),
    ("xsel", ["--clipboard", "--input"]),
    ("pbcopy", []),
)


def copy_text(text: str) -> str | None:
    """Copy text to the system clipboard; return the tool name or None."""
    for tool, args in _TOOLS:
        executable = shutil.which(tool)
        if executable is None:
            continue

        try:
            subprocess.run(
                [executable, *args],
                input=text.encode("utf-8"),
                check=True,
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            continue

        return tool

    return None
