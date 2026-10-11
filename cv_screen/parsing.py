"""Turn CV files (PDF, DOCX, TXT/MD) into plain text.

Images (including photos) are never extracted: only the text layer is read. Files over the
size limits are not parsed at all; they go to manual review. PDF text that a reader cannot see
(white, invisible, tiny or off-page) is still extracted but flagged.
"""

from __future__ import annotations

import io
import math
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
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
    # PDF work budget: a small file can hold megabytes of compressed drawing operators, or
    # invoke one form thousands of times. Samples use about 200 operators and 6 KB per file.
    max_pdf_ops: int = 300_000  # content-stream operators visited, forms included
    max_pdf_content_mb: float = 5  # decoded content parsed; a form counts each time it is used
    max_docx_xml_mb: float = 10  # the DOCX's XML parts; the unpacked limit is mostly for images

    @property
    def max_file_bytes(self) -> int:
        return int(self.max_file_mb * MB)


@dataclass
class ParsedCV:
    text: str
    warnings: list[str] = field(default_factory=list)  # shown to the manager, never a reason


def parse_file(path: Path, limits: Limits | None = None) -> str:
    return parse_cv(path, limits).text


def parse_cv(path: Path, limits: Limits | None = None) -> ParsedCV:
    limits = limits or Limits()
    warnings: list[str] = []
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ParseError(f"unsupported file type: {path.name}")
    if path.is_symlink():
        # A link in the applications folder could point at any file the manager can read
        # (an SSH key renamed .txt), whose text would be sent to the API and quoted in outputs.
        raise ParseError(f"{path.name} is a symbolic link; not read (copy the file into the "
                         "folder instead)")
    try:
        size = path.stat().st_size
        if size > limits.max_file_bytes:
            raise LimitError(f"{path.name} is {size / MB:.1f} MB, over the "
                             f"{limits.max_file_mb:g} MB limit (--max-file-mb); read it manually")
        data = path.read_bytes()
        if suffix == ".pdf":
            text = _parse_pdf(data, path.name, limits, warnings)
        elif suffix == ".docx":
            text = _parse_docx(data, path.name, limits, warnings)
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
    return ParsedCV(text, warnings)


def _too_long(name: str, chars: int, limits: Limits) -> LimitError:
    return LimitError(f"{name} has {chars} characters of text, over the {limits.max_chars} "
                      f"limit (--max-chars); not sent to the model, read it manually")


HIDDEN_TEXT_MIN_CHARS = 30  # non-space characters; a hidden sentence, not a stray dot


def _parse_pdf(data: bytes, name: str, limits: Limits, warnings: list[str]) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = len(reader.pages)
    if pages > limits.max_pdf_pages:
        raise LimitError(f"{name} has {pages} pages, over the {limits.max_pdf_pages} page limit "
                         f"(--max-pages); read it manually")
    parts, chars, hidden, shown = [], 0, 0, 0
    budget = _PdfBudget(name, limits)
    for page in reader.pages:
        contents = page.get_contents()
        budget.charge_bytes(len(contents.get_data()) if contents is not None else 0)
        tracker = _Visibility(page.mediabox, budget, _form_sizes(page.get("/Resources"), budget))
        parts.append(page.extract_text(visitor_operand_before=tracker.before) or "")
        budget.check()  # pypdf swallows an error raised inside a form; re-raise it here
        hidden, shown = hidden + tracker.hidden, shown + tracker.hidden + tracker.visible
        chars += len(parts[-1]) + 1
        if chars > limits.max_chars:  # stop extracting early
            raise _too_long(name, chars, limits)
    if hidden >= HIDDEN_TEXT_MIN_CHARS:
        warnings.append(
            f"Hidden text in the PDF: {hidden} of {shown} characters are not visible on the page "
            "(white, invisible, tiny or off-page text). This can be the text layer of a scanned "
            "CV, or text meant to steer the screening. Compare the PDF with the extracted "
            "claims before relying on them.")
    return "\n".join(parts)


def _docx_hidden_warning(hidden: int, shown: int) -> str:
    return (f"Hidden text in the DOCX: {hidden} of {shown} characters are not visible in Word "
            "(hidden, white without shading, or under 1 pt). This can be leftover template "
            "text, or text meant to steer the screening. Compare the document with the "
            "extracted claims before relying on them.")


class _PdfBudget:
    """Counts the work pypdf does for one file and raises `LimitError` once it is over."""

    def __init__(self, name: str, limits: Limits):
        self.name = name
        self.max_ops = limits.max_pdf_ops
        self.max_bytes = int(limits.max_pdf_content_mb * MB)
        self.ops = 0
        self.bytes = 0
        self.form_bytes = 0
        self.forms: dict = {}  # object number -> decoded size, shared by all pages
        self.error: LimitError | None = None

    def charge_op(self) -> None:
        self.ops += 1
        if self.ops > self.max_ops:
            self._fail(f"more than {self.max_ops} drawing operators")

    def charge_bytes(self, n: int) -> None:
        self.bytes += n
        if self.bytes > self.max_bytes:
            self._fail(f"more than {self.max_bytes / MB:g} MB of page content")

    def charge_form(self, size: int) -> None:
        # Forms are decoded up front to learn their size, and pypdf keeps decoded streams in
        # memory, so their total is capped too (else many large unused forms exhaust memory).
        self.form_bytes += size
        if self.form_bytes > self.max_bytes:
            self._fail(f"more than {self.max_bytes / MB:g} MB of drawing forms")

    def check(self) -> None:
        if self.error:
            raise self.error

    def _fail(self, what: str) -> None:
        self.error = LimitError(f"{self.name} has {what}, over the PDF parsing limit; "
                                "read it manually")
        raise self.error


def _form_sizes(resources: Any, budget: _PdfBudget, sizes: dict | None = None,
                walked: set | None = None) -> dict:
    """Decoded size of every form XObject reachable from `resources`, by resource name (the
    largest if two forms share a name), so each use of a form can be charged before pypdf
    parses it. Each form is decoded once per file; images are skipped without decoding."""
    sizes = {} if sizes is None else sizes
    walked = set() if walked is None else walked
    try:
        xobjects = resources.get_object().get("/XObject") if resources is not None else None
        items = list(xobjects.get_object().items()) if xobjects is not None else []
    except AttributeError:
        return sizes
    for name, ref in items:
        obj = ref.get_object()
        if not hasattr(obj, "get") or obj.get("/Subtype") != "/Form":
            continue
        key = getattr(ref, "idnum", id(obj))
        if key not in budget.forms:
            budget.forms[key] = len(obj.get_data())
            budget.charge_form(budget.forms[key])
        sizes[name] = max(sizes.get(name, 0), budget.forms[key])
        if key not in walked:  # once per page: no endless loop on a self-referencing form
            walked.add(key)
            _form_sizes(obj.get("/Resources"), budget, sizes, walked)
    return sizes


class _Visibility:
    """Follows the PDF graphics state while pypdf extracts a page and counts the characters a
    reader cannot see: render mode invisible, white fill on a page with no coloured fill or
    image drawn before it, an effective size under 1 pt, or a position outside the page.
    A heuristic: it only feeds a warning for the manager. It also charges every operator, and
    every form before it is drawn, to the file's `_PdfBudget`."""

    TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}
    PAINT_OPS = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
    BACKDROP_OPS = {b"Do", b"sh", b"INLINE IMAGE"}  # images, forms, shadings

    def __init__(self, box: Any, budget: _PdfBudget, forms: dict):
        self.budget = budget
        self.forms = forms
        self.box = [float(v) for v in (box.left, box.bottom, box.right, box.top)]
        self.state = {"white": False, "render": 0, "size": 12.0}
        self.stack: list[dict] = []
        self.backdrop = False
        self.hidden = 0
        self.visible = 0

    def before(self, op: bytes, args: list, cm: list, tm: list) -> None:
        self.budget.charge_op()
        if op == b"Do" and args:
            self.budget.charge_bytes(self.forms.get(args[0], 0))
        s = self.state
        nums = [float(a) for a in args if isinstance(a, int | float)]
        if op == b"q":
            self.stack.append(dict(s))
        elif op == b"Q" and self.stack:
            self.state = self.stack.pop()
        elif op in (b"g", b"rg", b"k", b"sc", b"scn") and nums:
            # 1 value: gray, 3: RGB, 4: CMYK (where white is all zero)
            s["white"] = (all(v <= 0.05 for v in nums) if len(nums) == 4
                          else all(v >= 0.95 for v in nums))
        elif op == b"cs":
            s["white"] = False  # a new colour space starts at black
        elif op == b"Tr" and nums:
            s["render"] = int(nums[0])
        elif op == b"Tf" and nums:
            s["size"] = abs(nums[-1])
        elif op in self.PAINT_OPS and not s["white"] or op in self.BACKDROP_OPS:
            self.backdrop = True
        elif op in self.TEXT_OPS:
            n = _shown_chars(op, args)
            if self._is_hidden(cm, tm):
                self.hidden += n
            else:
                self.visible += n

    def _is_hidden(self, cm: list, tm: list) -> bool:
        s = self.state
        if s["render"] in (3, 7) or (s["white"] and not self.backdrop):
            return True
        scale = math.sqrt(abs((tm[0] * tm[3] - tm[1] * tm[2]) * (cm[0] * cm[3] - cm[1] * cm[2])))
        if s["size"] * scale < 1.0:
            return True
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        left, bottom, right, top = self.box
        return not (left - 5 <= x <= right + 5 and bottom - 5 <= y <= top + 5)


def _shown_chars(op: bytes, args: list) -> int:
    items = list(args[0]) if op == b"TJ" and args else args[-1:]
    return sum(len(i.replace(" ", "")) if isinstance(i, str) else len(i.replace(b" ", b""))
               for i in items if isinstance(i, str | bytes))


def _parse_docx(data: bytes, name: str, limits: Limits, warnings: list[str]) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
    unpacked = sum(info.file_size for info in infos)
    if unpacked > limits.max_unpacked_mb * MB:
        raise LimitError(f"{name} unpacks to {unpacked / MB:.1f} MB, over the "
                         f"{limits.max_unpacked_mb:g} MB limit; read it manually")
    markup = sum(i.file_size for i in infos if i.filename.lower().endswith((".xml", ".rels")))
    if markup > limits.max_docx_xml_mb * MB:
        raise LimitError(f"{name} has {markup / MB:.1f} MB of document markup, over the "
                         f"{limits.max_docx_xml_mb:g} MB limit; read it manually")
    doc = Document(io.BytesIO(data))
    reader = _DocxReader(name, limits, doc.styles.element)
    reader.blocks(doc.element.body)
    if reader.hidden >= HIDDEN_TEXT_MIN_CHARS:
        warnings.append(_docx_hidden_warning(reader.hidden, reader.hidden + reader.visible))
    return "\n".join(reader.lines)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
# Not text a reader sees: properties, deleted or moved-away text, and the second (VML) copy of
# a text box that Word writes next to the DrawingML one.
_DOCX_SKIP = {_W + "pPr", _W + "rPr", _W + "del", _W + "moveFrom", _MC_FALLBACK}


class _DocxReader:
    """Text of a DOCX body in reading order: paragraphs, table rows (one line each) and text
    boxes (after the paragraph that anchors them), inside content controls too. Stops as soon
    as the text is over `max_chars`, so a file of millions of empty paragraphs is cheap.

    Like `_Visibility` for PDFs, it counts characters Word does not show: runs marked hidden,
    under 1 pt, or white with no shading behind them (run, paragraph or cell). A heuristic
    for a warning; text coloured by a style is not checked."""

    def __init__(self, name: str, limits: Limits, styles: Any):
        self.name = name
        self.limits = limits
        self.lines: list[str] = []
        self.chars = -1  # "\n".join(lines) has one separator fewer than lines
        self.hidden = 0
        self.visible = 0
        # Style lookup once per document: python-docx scans every style per paragraph.
        para_styles = [st for st in styles.style_lst if st.type == WD_STYLE_TYPE.PARAGRAPH]
        self.styles = {st.styleId: "list" in (st.name_val or "").lower() for st in para_styles}
        default = styles.default_for(WD_STYLE_TYPE.PARAGRAPH)
        self.default_is_list = default is not None and "list" in (default.name_val or "").lower()

    def add(self, line: str) -> None:
        self.lines.append(line)
        self.chars += len(line) + 1
        if self.chars > self.limits.max_chars:
            raise _too_long(self.name, self.chars, self.limits)

    def blocks(self, parent: Any) -> None:
        for child in parent.iterchildren():
            if child.tag == _W + "p":
                self.paragraph(child)
            elif child.tag == _W + "tbl":
                self.table(child)
            elif child.tag == _W + "sdt":
                self.blocks_in(child, "sdtContent")

    def blocks_in(self, el: Any, tag: str) -> None:
        content = el.find(_W + tag)
        if content is not None:
            self.blocks(content)

    def paragraph(self, p: Any) -> None:
        text, boxes = self.inline(p, _shaded(p.find(f"{_W}pPr/{_W}shd")))
        style = p.find(f"{_W}pPr/{_W}pStyle")
        style_id = style.get(_W + "val") if style is not None else None
        is_list = self.styles.get(style_id, self.default_is_list)
        self.add(f"- {text}" if is_list and text.strip() else text)
        for box in boxes:
            self.blocks(box)

    def table(self, tbl: Any) -> None:
        for tr in tbl.iterchildren(_W + "tr"):
            cells, boxes = [], []
            for tc in tr.iterchildren(_W + "tc"):  # a merged cell is one <w:tc>: read once
                texts = []
                cell_shaded = _shaded(tc.find(f"{_W}tcPr/{_W}shd"))
                for p in tc.iterchildren(_W + "p"):
                    shaded = cell_shaded or _shaded(p.find(f"{_W}pPr/{_W}shd"))
                    text, found = self.inline(p, shaded)
                    texts.append(text)
                    boxes += found
                cells.append("\n".join(texts))
            self.add(" | ".join(cells))
            for box in boxes:
                self.blocks(box)

    def inline(self, p: Any, shaded: bool = False) -> tuple[str, list]:
        """A paragraph's own text, and the text boxes anchored in it (read separately)."""
        out: list[str] = []
        boxes: list = []

        def walk(el: Any, hidden: bool = False) -> None:
            for child in el:
                tag = child.tag
                if not isinstance(tag, str) or tag in _DOCX_SKIP:
                    continue
                if tag == _W + "t":
                    out.append(child.text or "")
                    n = len("".join((child.text or "").split()))
                    if hidden:
                        self.hidden += n
                    else:
                        self.visible += n
                elif tag == _W + "r":
                    walk(child, _run_hidden(child.find(_W + "rPr"), shaded))
                elif tag in (_W + "tab", _W + "ptab"):
                    out.append("\t")
                elif tag == _W + "br":
                    out.append("\n" if child.get(_W + "type", "textWrapping") == "textWrapping"
                               else "")
                elif tag == _W + "cr":
                    out.append("\n")
                elif tag == _W + "noBreakHyphen":
                    out.append("-")
                elif tag == _W + "txbxContent":
                    boxes.append(child)
                elif tag != _W + "p":  # a nested paragraph belongs to something else
                    walk(child, hidden)

        walk(p)
        return "".join(out), boxes


_OFF = {"0", "false", "off"}
_NO_FILL = {None, "auto", "FFFFFF", "ffffff"}


def _shaded(shd: Any) -> bool:
    """A w:shd with a non-white fill: white text on it is visible."""
    return shd is not None and shd.get(_W + "fill") not in _NO_FILL


def _run_hidden(rpr: Any, shaded: bool) -> bool:
    if rpr is None:
        return False
    vanish = rpr.find(_W + "vanish")
    if vanish is not None and vanish.get(_W + "val", "true") not in _OFF:
        return True
    size = rpr.find(_W + "sz")
    half_points = size.get(_W + "val") if size is not None else None
    if half_points and half_points.isdigit() and int(half_points) < 2:
        return True  # under 1 pt
    color = rpr.find(_W + "color")
    white = color is not None and (
        (color.get(_W + "val") or "").upper() == "FFFFFF"
        or color.get(_W + "themeColor") in {"background1", "light1"})
    highlight = rpr.find(_W + "highlight")
    return (white and not shaded and not _shaded(rpr.find(_W + "shd"))
            and (highlight is None or highlight.get(_W + "val") in (None, "none")))


def normalize_text(text: str) -> str:
    """Normalise whitespace and dash variants; keep one item per line. Invisible format
    characters (soft hyphens from PDF hyphenation, zero-width spaces, bidi controls, BOM) are
    dropped: they split words ("Zen\u00addesk" would not match "zendesk") and can reorder how
    text is displayed."""
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
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
