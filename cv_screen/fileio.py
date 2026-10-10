"""Owner-only files for personal data: folders 0700, files 0600, whatever the umask.

Modes are set explicitly after creation (the umask can only remove bits, and an existing file
or folder keeps its old mode), and files are opened without following a symlink, so a link
planted in a shared output folder cannot redirect a write.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO

DIR_MODE = 0o700
FILE_MODE = 0o600


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    os.chmod(path, DIR_MODE)
    return path


def open_private(path: Path) -> IO[str]:
    """Open `path` for writing text (no newline translation, as the csv module expects)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, FILE_MODE)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, FILE_MODE)
        return os.fdopen(fd, "w", encoding="utf-8", newline="")
    except BaseException:
        os.close(fd)
        raise


def write_private(path: Path, text: str) -> None:
    with open_private(path) as fh:
        fh.write(text)
