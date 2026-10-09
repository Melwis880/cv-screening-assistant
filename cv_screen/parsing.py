"""Turn CV files (PDF, DOCX, TXT/MD) into plain text.

Images (including photos) are never extracted: only the text layer is read.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class ParseError(Exception):
    """Raised when a file cannot be read as a CV."""


def parse_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ParseError(f"unsupported file type: {path.name}")
    try:
        if suffix == ".pdf":
            text = _parse_pdf(path)
        elif suffix == ".docx":
            text = _parse_docx(path)
        else:
            text = path.read_text(encoding="utf-8")
    except ParseError:
        raise
    except Exception as exc:  # corrupt files surface as many different library errors
        raise ParseError(f"could not read {path.name}: {exc}") from exc
    text = normalize_text(text)
    if not text.strip():
        raise ParseError(f"no text found in {path.name} (scanned image? OCR is not supported)")
    return text


def _parse_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _parse_docx(path: Path) -> str:
    doc = Document(str(path))
    lines = [p.text for p in doc.paragraphs]
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
