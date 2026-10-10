"""Turn CV files (PDF, DOCX, TXT/MD) into plain text.

Images (including photos) are never extracted: only the text layer is read. Files over the
size limits are not parsed at all; they go to manual review.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class ParseError(Exception):
    """Raised when a file cannot be read as a CV."""


class LimitError(ParseError):
    """The file is larger than a configured limit; a person should read it instead."""


MB = 1_000_000


@dataclass(frozen=True)
class Limits:
    """Input limits. A CV over any of them goes to manual review, never to a rejection."""

    max_file_mb: float = 5
    max_pdf_pages: int = 10
    max_chars: int = 30_000  # roughly 8k tokens, far above a real 1-3 page CV
    max_unpacked_mb: float = 50  # DOCX is a zip; guards against zip bombs

    @property
    def max_file_bytes(self) -> int:
        return int(self.max_file_mb * MB)


def parse_file(path: Path, limits: Limits | None = None) -> str:
    limits = limits or Limits()
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ParseError(f"unsupported file type: {path.name}")
    try:
        size = path.stat().st_size
        if size > limits.max_file_bytes:
            raise LimitError(f"{path.name} is {size / MB:.1f} MB, over the "
                             f"{limits.max_file_mb:g} MB limit (--max-file-mb); read it manually")
        data = path.read_bytes()
        if suffix == ".pdf":
            text = _parse_pdf(data, path.name, limits)
        elif suffix == ".docx":
            text = _parse_docx(data, path.name, limits)
        else:
            text = data.decode("utf-8")
    except ParseError:
        raise
    except Exception as exc:  # corrupt files surface as many different library errors
        raise ParseError(f"could not read {path.name}: {exc}") from exc
    if len(text) > limits.max_chars:
        raise _too_long(path.name, len(text), limits)
    text = normalize_text(text)
    if not text.strip():
        raise ParseError(f"no text found in {path.name} (scanned image? OCR is not supported)")
    return text


def _too_long(name: str, chars: int, limits: Limits) -> LimitError:
    return LimitError(f"{name} has {chars} characters of text, over the {limits.max_chars} "
                      f"limit (--max-chars); not sent to the model, read it manually")


def _parse_pdf(data: bytes, name: str, limits: Limits) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = len(reader.pages)
    if pages > limits.max_pdf_pages:
        raise LimitError(f"{name} has {pages} pages, over the {limits.max_pdf_pages} page limit "
                         f"(--max-pages); read it manually")
    parts, chars = [], 0
    for page in reader.pages:
        parts.append(page.extract_text() or "")
        chars += len(parts[-1]) + 1
        if chars > limits.max_chars:  # stop extracting early
            raise _too_long(name, chars, limits)
    return "\n".join(parts)


def _parse_docx(data: bytes, name: str, limits: Limits) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        unpacked = sum(info.file_size for info in zf.infolist())
    if unpacked > limits.max_unpacked_mb * MB:
        raise LimitError(f"{name} unpacks to {unpacked / MB:.1f} MB, over the "
                         f"{limits.max_unpacked_mb:g} MB limit; read it manually")
    doc = Document(io.BytesIO(data))
    lines = []
    for para in doc.paragraphs:
        is_list = para.style is not None and "list" in (para.style.name or "").lower()
        lines.append(f"- {para.text}" if is_list and para.text.strip() else para.text)
    for table in doc.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(lines)


def normalize_text(text: str) -> str:
    """Normalise whitespace and dash variants; keep one item per line."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ")
    text = re.sub(r"[‐-―−]", "-", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    lines = [re.sub(r"^[•●▪*]\s*", "- ", line) for line in lines]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip() + "\n"


def find_cv_files(folder: Path) -> list[Path]:
    if folder.is_file():
        return [folder]
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and not p.name.startswith(".")
        and p.name.lower() not in {"readme.md"}
    )
