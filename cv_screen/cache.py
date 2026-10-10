"""Local cache of validated extraction results, so re-runs only pay for CVs not seen before.

An entry is the extractor's output for one CV (skills, roles, languages, education, each with
a quote from the redacted CV text), stored as JSON. Only results that passed schema validation
are stored; failures are never cached. Evidence checks and matching run again on every run, so
rule changes apply to cached CVs too.

The key covers everything that decides the result: the file's SHA-256, the redacted text sent,
and the extractor's identity (model, prompt, schema and the job part of the prompt). Files are
owner-only, written atomically, ignored if invalid, and deleted after `ttl_days`.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from cv_screen.fileio import private_dir, write_private
from cv_screen.schema import Extraction

CACHE_FORMAT = 1
DEFAULT_TTL_DAYS = 30


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ExtractionCache:
    def __init__(self, directory: Path, ttl_days: float = DEFAULT_TTL_DAYS):
        self.dir = directory
        self.ttl_seconds = ttl_days * 86400

    @staticmethod
    def key(file_sha256: str, sent_text: str, extractor_identity: str) -> str:
        return _sha256(json.dumps({
            "format": CACHE_FORMAT, "file_sha256": file_sha256,
            "text_sha256": _sha256(sent_text), "extractor": extractor_identity,
        }, sort_keys=True))

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def _expired(self, st: os.stat_result) -> bool:
        return time.time() - st.st_mtime > self.ttl_seconds

    def get(self, key: str) -> Extraction | None:
        path = self._path(key)
        try:
            st = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(st.st_mode):  # never follow a planted link
            return None
        if self._expired(st):
            path.unlink(missing_ok=True)
            return None
        try:
            return Extraction.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError):
            path.unlink(missing_ok=True)  # corrupt or tampered: re-extract
            return None

    def put(self, key: str, extraction: Extraction) -> None:
        private_dir(self.dir)
        tmp = self.dir / f".{key}.{os.getpid()}.{threading.get_ident()}.tmp"
        write_private(tmp, extraction.model_dump_json())
        os.replace(tmp, self._path(key))  # atomic: readers never see half a file

    def purge_expired(self) -> int:
        """Delete expired entries (retention); returns how many were deleted."""
        if not self.dir.is_dir():
            return 0
        deleted = 0
        for path in self.dir.glob("*.json"):
            try:
                st = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode) and self._expired(st):
                path.unlink(missing_ok=True)
                deleted += 1
        return deleted
