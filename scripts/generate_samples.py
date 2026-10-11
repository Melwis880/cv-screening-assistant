"""Generate the synthetic sample CVs in samples/.

Every person here is fictional. Names are well-known placeholder names, addresses use
"Example Street" / "Sampletown", emails use example.com, phone numbers are 0000 numbers.
Each CV ends with a footer saying it is synthetic.

Output is deterministic: re-running produces byte-identical files.

    python scripts/generate_samples.py
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"
FOOTER = "SYNTHETIC CV - fictional person generated for a software demo. Not a real applicant."
FIXED_DATE = datetime(2026, 10, 1, 9, 0, 0)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class Job:
    title: str
    employer: str
    start: str | None  # "YYYY-MM" or "YYYY" or None (undated)
    end: str | None  # "YYYY-MM", "YYYY", "present" or None
    bullets: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    cid: str
    fmt: str  # "pdf" or "docx"
    layout: str  # "A", "B" or "C"
    name: str
    address: str
    dob: str
    nationality: str
    gender: str
    marital: str
    photo: bool
    profile: str
    jobs: list[Job]
    education: list[str]
    languages: list[str] | None
    skills: list[str] | None


def fmt_date(value: str | None, layout: str) -> str:
    if value is None:
        return ""
    if value == "present":
        return {"A": "present", "B": "Present", "C": "now"}[layout]
    if len(value) == 4:
        return value
    year, month = value.split("-")
    if layout == "A":
        return f"{month}/{year}"
    if layout == "B":
        return f"{MONTHS[int(month) - 1]} {year}"
    return f"{year}-{month}"


def job_line(job: Job, layout: str) -> str:
    if job.start is None:
        dates = ""
    else:
        sep = " to " if layout == "C" else " - "
        dates = fmt_date(job.start, layout) + sep + fmt_date(job.end, layout)
    if layout == "C":
        return " | ".join(p for p in (dates, job.title, job.employer) if p)
    line = f"{job.title}, {job.employer}"
    return f"{line} - {dates}" if dates else line


HEADINGS = {
    "A": ["Profile", "Experience", "Education", "Languages", "Skills"],
    "B": ["SUMMARY", "WORK EXPERIENCE", "EDUCATION", "LANGUAGES", "SKILLS & TOOLS"],
    "C": ["About me", "Professional Experience", "Education & Training", "Language skills", "Tools"],
}


def cv_lines(c: Candidate) -> list[tuple[str, str]]:
    """Return (kind, text) pairs; kind is title, contact, heading, text, bullet, footer."""
    h = HEADINGS[c.layout]
    email = c.name.lower().replace(" ", ".").replace("'", "") + "@example.com"
    out: list[tuple[str, str]] = []
    if c.layout == "B":
        out.append(("title", "CURRICULUM VITAE"))
        out.append(("contact", f"Name: {c.name}"))
    else:
        out.append(("title", c.name))
    out.append(("contact", f"Address: {c.address}"))
    out.append(("contact", f"Email: {email} | Phone: +49 30 0000 {c.cid[-2:]}00"))
    out.append(
        (
            "contact",
            f"Date of birth: {c.dob} | Nationality: {c.nationality} | "
            f"Gender: {c.gender} | Marital status: {c.marital}",
        )
    )
    out.append(("heading", h[0]))
    out.append(("text", c.profile))
    out.append(("heading", h[1]))
    for job in c.jobs:
        out.append(("job", job_line(job, c.layout)))
        for b in job.bullets:
            out.append(("bullet", b))
    if c.education:
        out.append(("heading", h[2]))
        for e in c.education:
            out.append(("text", e))
    if c.languages is not None:
        out.append(("heading", h[3]))
        for lang in c.languages:
            out.append(("text", lang))
    if c.skills is not None:
        out.append(("heading", h[4]))
        out.append(("text", ", ".join(c.skills)))
    out.append(("footer", FOOTER))
    return out


def placeholder_photo() -> bytes:
    img = Image.new("RGB", (120, 150), (210, 210, 210))
    d = ImageDraw.Draw(img)
    d.ellipse((35, 20, 85, 70), fill=(160, 160, 160))
    d.rectangle((25, 80, 95, 150), fill=(160, 160, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def write_pdf(c: Candidate, path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    pdf.setTitle("Synthetic CV")
    pdf.setAuthor("cv-screening-assistant sample generator")
    width, height = A4
    y = height - 60
    if c.photo:
        pdf.setFillGray(0.8)
        pdf.rect(width - 140, height - 170, 90, 110, fill=1, stroke=0)
        pdf.setFillGray(0)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(width - 115, height - 120, "[Photo]")
    for kind, text in cv_lines(c):
        if kind == "title":
            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawString(50, y, text)
            y -= 26
            continue
        if kind == "heading":
            y -= 8
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(50, y, text)
            y -= 18
            continue
        if kind == "footer":
            pdf.setFont("Helvetica-Oblique", 7)
            pdf.drawString(50, 30, text)
            continue
        font, size, indent, prefix = "Helvetica", 9.5, 50, ""
        if kind == "contact":
            size = 8.5
        elif kind == "job":
            font = "Helvetica-Bold"
        elif kind == "bullet":
            indent, prefix = 62, "- "
        pdf.setFont(font, size)
        for i, part in enumerate(wrap(text, 95 if kind != "bullet" else 90)):
            pdf.drawString(indent, y, (prefix if i == 0 else "  ") + part)
            y -= 13
    pdf.showPage()
    pdf.save()


def write_docx(c: Candidate, path: Path) -> None:
    doc = Document()
    props = doc.core_properties
    props.author = "cv-screening-assistant sample generator"
    props.title = "Synthetic CV"
    props.created = FIXED_DATE
    props.modified = FIXED_DATE
    props.last_modified_by = "generator"
    props.revision = 1
    style = doc.styles["Normal"]
    style.font.size = Pt(10)
    if c.photo:
        doc.add_picture(io.BytesIO(placeholder_photo()), width=Cm(2.5))
    for kind, text in cv_lines(c):
        if kind == "title":
            doc.add_heading(text, level=0)
        elif kind == "heading":
            doc.add_heading(text, level=1)
        elif kind == "bullet":
            doc.add_paragraph(text, style="List Bullet")
        elif kind == "job":
            doc.add_paragraph().add_run(text).bold = True
        elif kind == "footer":
            doc.add_paragraph().add_run(text).italic = True
        else:
            doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    path.write_bytes(normalize_zip(buf.getvalue()))


def normalize_zip(data: bytes) -> bytes:
    """Rewrite a DOCX zip with fixed entry timestamps so output is reproducible."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=(2026, 10, 1, 9, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, src.read(item.filename))
    return out.getvalue()


ADDR = "{n} Example Street, 10115 Sampletown"

CANDIDATES: list[Candidate] = [
    Candidate(
        "cv01", "pdf", "A", "Erika Mustermann", ADDR.format(n=12), "14 March 1999",
        "Fictionalian", "Female", "Single", True,
        "Customer service agent who enjoys solving problems in writing and keeping customers calm.",
        [
            Job("Customer Service Agent", "Example Shop GmbH (fictional)", "2022-03", "present", [
                "Answered customer emails and live chat in Zendesk, about 60 tickets per day",
                "Handled returns and refunds for a Shopify store",
            ]),
            Job("Sales Assistant", "Sampletown Fashion (fictional)", "2019-08", "2022-02", [
                "Advised customers on the shop floor and at the checkout",
            ]),
        ],
        ["Vocational training as Retail Salesperson (IHK), Sampletown Vocational School, 2016 - 2019"],
        ["German: native", "English: C1", "French: B1"],
        ["Zendesk", "Shopify", "live chat", "email support", "Excel"],
    ),
    Candidate(
        "cv02", "docx", "B", "Max Mustermann", ADDR.format(n=3), "2 June 1996",
        "Exampleland", "Male", "Married", False,
        "Support specialist from an online shop background, calm under pressure.",
        [
            Job("Customer Support Specialist", "Demo Webstore AG (fictional)", "2021-01", "2023-12", [
                "Resolved customer tickets by email and chat in Freshdesk",
                "Maintained FAQ pages in WooCommerce",
            ]),
            Job("Barista", "Placeholder Coffee (fictional)", "2018-05", "2020-12", [
                "Served guests in a busy city cafe",
            ]),
        ],
        ["Bachelor of Arts in Communication, University of Sampletown, 2015 - 2018"],
        ["German: C2", "English: C2"],
        ["Freshdesk", "WooCommerce", "ticketing", "chat support", "Google Sheets"],
    ),
    Candidate(
        "cv03", "pdf", "C", "Jan Kowalski", ADDR.format(n=45), "30 November 1994",
        "Fictionalian", "Male", "Single", False,
        "Experienced call centre agent who wants to move into an online shop.",
        [
            Job("Call Centre Agent", "Hotline Services Ltd (fictional)", "2023-06", "present", [
                "Phone support for an energy provider, 80 calls per day",
                "Logged cases in the company CRM",
            ]),
            Job("Warehouse Operative", "Logistics Demo GmbH (fictional)", "2019-01", "2023-05", [
                "Picked and packed orders",
            ]),
        ],
        ["Secondary school leaving certificate, Sampletown High School, 2013"],
        ["Polish: native", "German: C1", "English: C1"],
        ["phone support", "CRM", "Microsoft Office"],
    ),
    Candidate(
        "cv04", "docx", "A", "Jane Placeholder", ADDR.format(n=8), "21 July 2000",
        "Exampleland", "Female", "Single", True,
        "Friendly retail worker looking for a first office-based support role.",
        [
            Job("Retail Sales Assistant", "Sample Electronics (fictional)", "2023-02", "present", [
                "Helped customers choose products and answered their emails about orders",
            ]),
        ],
        ["Vocational training as Office Clerk, Sampletown Vocational School, 2019 - 2022"],
        ["English: C1", "German: B1", "Spanish: A2"],
        ["customer emails", "Excel", "cash register"],
    ),
    Candidate(
        "cv05", "pdf", "B", "John Q. Sample", ADDR.format(n=101), "5 January 1992",
        "Exampleland", "Male", "Divorced", False,
        "Bilingual support agent with five years in e-commerce.",
        [
            Job("Customer Support Agent", "Demo Marketplace Inc (fictional)", "2020-04", "2025-06", [
                "Email support and live chat for marketplace buyers using Zendesk",
                "Trained new agents on Shopify order handling",
            ]),
        ],
        ["Bachelor of Science in Business, Example State University, 2010 - 2014"],
        ["English: native", "Spanish: C1"],
        ["Zendesk", "Shopify", "email support", "live chat"],
    ),
    Candidate(
        "cv06", "docx", "C", "Ola Nordmann", ADDR.format(n=27), "19 September 2002",
        "Fictionalian", "Male", "Single", False,
        "Recent business graduate with a support internship.",
        [
            Job("Customer Service Intern", "Example Travel GmbH (fictional)", "2025-07", "2025-12", [
                "Answered customer emails about bookings",
            ]),
        ],
        ["Bachelor of Arts in Business Administration, University of Sampletown, 2021 - 2025"],
        ["German: C1", "English: C1", "Dutch: B2"],
        ["email support", "HubSpot", "Excel"],
    ),
    Candidate(
        "cv07", "pdf", "A", "Mario Rossi", ADDR.format(n=5), "8 August 1997",
        "Exampleland", "Male", "Married", True,
        "Hotel receptionist used to guests from all over the world.",
        [
            Job("Front Desk Receptionist", "Hotel Demo (fictional)", "2020-10", "present", [
                "Checked guests in and out and answered booking requests by email",
            ]),
        ],
        ["Vocational training in Hotel Management, Sampletown Hospitality School, 2017 - 2020"],
        None,
        ["customer emails", "Opera PMS", "Excel"],
    ),
    Candidate(
        "cv08", "docx", "B", "Juan Perez", ADDR.format(n=64), "1 February 1995",
        "Fictionalian", "Male", "Single", False,
        "Customer-facing generalist.",
        [
            Job("Customer Advisor", "Telecom Example Shop (fictional)", None, None, [
                "Advised customers in store and by email on mobile contracts",
            ]),
            Job("Cashier", "Supermarket Demo (fictional)", None, None, []),
        ],
        ["Secondary school leaving certificate (Abitur), Sampletown Gymnasium, 2014"],
        ["Spanish: native", "German: C1", "English: C1"],
        ["customer emails", "Excel"],
    ),
    Candidate(
        "cv09", "pdf", "C", "Erika Beispiel", ADDR.format(n=19), "12 December 1988",
        "Exampleland", "Female", "Married", False,
        "Career changer from logistics who has started working with customers.",
        [
            Job("Weekend Sales Assistant", "Bookshop Demo (fictional)", "2026-02", "present", [
                "Served customers and answered questions via the shop's live chat",
            ]),
            Job("Warehouse Team Lead", "Logistics Demo GmbH (fictional)", "2016-01", "2025-12", [
                "Led a team of eight in goods receiving",
            ]),
        ],
        ["Vocational training as Warehouse Logistics Specialist, Sampletown Vocational School, "
         "2013 - 2016"],
        ["German: native", "English: C1"],
        ["live chat", "SAP", "Excel"],
    ),
    Candidate(
        "cv10", "docx", "A", "Tommy Atkins", ADDR.format(n=2), "17 April 1985",
        "Fictionalian", "Male", "Married", False,
        "Support team lead with six years in online retail.",
        [
            Job("Customer Support Team Lead", "Demo Outdoor Shop (fictional)", "2020-01", "present", [
                "Led a team of five handling email and live chat in Gorgias",
                "Set up Zendesk macros and Shopify order workflows",
            ]),
            Job("Customer Support Agent", "Demo Outdoor Shop (fictional)", "2018-03", "2019-12", [
                "Answered customer tickets",
            ]),
        ],
        ["Master of Arts in Media Studies, University of Sampletown, 2008 - 2013"],
        ["German: native", "English: C2", "Italian: B2"],
        ["Gorgias", "Zendesk", "Shopify", "live chat", "ticketing", "Excel"],
    ),
    Candidate(
        "cv11", "pdf", "B", "Jane Roe", ADDR.format(n=88), "23 May 1998",
        "Exampleland", "Female", "Single", True,
        "Customer service agent with strong languages.",
        [
            Job("Customer Service Agent", "Demo Insurance (fictional)", "2022-09", "present", [
                "Answered customer emails and phone calls",
            ]),
        ],
        ["Vocational training as Insurance Clerk, Sampletown Vocational School, 2019 - 2022"],
        ["German: fluent", "English: fluent", "French: basic"],
        ["email support", "phone support", "Excel"],
    ),
    Candidate(
        "cv12", "docx", "C", "Fulan Al-Fulani", ADDR.format(n=31), "9 March 1993",
        "Fictionalian", "Male", "Married", False,
        "Hospitality professional moving into e-commerce support.",
        [
            Job("Front Desk Agent", "Grand Demo Hotel (fictional)", "2022-01", "present", [
                "Handled guest requests at the desk and by email",
            ]),
        ],
        ["Vocational training in Hospitality, Sampletown Hospitality School, 2018 - 2021"],
        ["German: C2", "English: B2", "French: C1"],
        ["customer emails", "Opera PMS"],
    ),
    Candidate(
        "cv13", "pdf", "A", "Joe Bloggs", ADDR.format(n=72), "28 October 1990",
        "Exampleland", "Male", "Single", False,
        "Backend developer who wants a change of pace.",
        [
            Job("Software Developer", "Demo Tech GmbH (fictional)", "2015-04", "present", [
                "Built internal tools in Python",
            ]),
        ],
        ["Bachelor of Science in Computer Science, University of Sampletown, 2011 - 2015"],
        ["German: C2", "English: C1"],
        ["Python", "SQL", "Excel"],
    ),
    Candidate(
        "cv14", "docx", "B", "Maria Musterfrau", ADDR.format(n=14), "3 March 2001",
        "Fictionalian", "Female", "Single", True,
        "She is a patient support agent and her colleagues describe her as the calmest person "
        "on the team.",
        [
            Job("E-commerce Support Agent", "Demo Beauty Shop (fictional)", "2023-04", "present", [
                "Answered customer emails and live chat in Help Scout",
                "Updated product pages in Shopware",
            ]),
        ],
        ["Vocational training as E-commerce Clerk (IHK), Sampletown Vocational School, 2020 - 2023"],
        ["German: native", "English: C1", "Italian: B1"],
        ["Help Scout", "Shopware", "email support", "live chat", "Google Sheets"],
    ),
    Candidate(
        "cv15", "pdf", "C", "Kari Nordmann", ADDR.format(n=50), "11 November 1999",
        "Exampleland", "Female", "Single", False,
        "Reliable cashier ready for the next step.",
        [
            Job("Cashier", "Supermarket Demo (fictional)", "2025-03", "present", [
                "Served customers at the checkout and handled complaints in person",
            ]),
        ],
        ["Secondary school leaving certificate, Sampletown Comprehensive, 2018"],
        ["German: native", "English: C1"],
        ["cash handling", "Microsoft Word"],
    ),
    Candidate(
        "cv16", "docx", "A", "Anna Kowalska", ADDR.format(n=7), "6 June 1997",
        "Fictionalian", "Female", "Married", False,
        "E-commerce support agent with Polish and German.",
        [
            Job("Online Shop Support Agent", "Demo Furniture Online (fictional)", "2025-09",
                "present", [
                    "Answered customer emails and tickets in Shopware",
                ]),
            Job("Au pair", "Private household", "2019-09", "2020-08", []),
        ],
        ["Bachelor of Arts in German Studies, Example University, 2016 - 2019"],
        ["Polish: native", "German: C1", "English: C1"],
        ["Shopware", "ticketing", "email support"],
    ),
    Candidate(
        "cv17", "pdf", "B", "Lisa Beispiel", ADDR.format(n=99), "15 January 2004",
        "Exampleland", "Female", "Single", False,
        "Student working part-time in chat support.",
        [
            Job("Chat Support Agent (part-time)", "Demo Fashion Online (fictional)", "2024-01",
                "present", ["Live chat support in Intercom for an online fashion store"]),
        ],
        [
            "Bachelor of Arts in Linguistics (in progress, expected 2027), University of Sampletown",
            "Secondary school leaving certificate (Abitur), Sampletown Gymnasium, 2022",
        ],
        ["German: native", "English: C1", "Spanish: B2"],
        ["Intercom", "live chat", "chat support"],
    ),
    Candidate(
        "cv18", "docx", "C", "John Doe", ADDR.format(n=1), "20 April 1996",
        "Fictionalian", "Male", "Single", False,
        "Looking for a job in customer support.",
        [
            Job("Support Agent", "Various employers", "2024-05", "present", []),
        ],
        [],
        None,
        None,
    ),
    Candidate(
        "cv19", "pdf", "A", "Mario Bianchi", ADDR.format(n=36), "29 February 1996",
        "Exampleland", "Male", "Single", True,
        "Freelance virtual assistant for small online shops.",
        [
            Job("Freelance Virtual Assistant", "Self-employed", "2024-04", "present", [
                "Email support for three online shops in Help Scout",
                "Updated orders in Shopify",
            ]),
        ],
        ["Vocational training as Office Clerk, Sampletown Vocational School, 2014 - 2017"],
        ["German: B2", "English: C2", "Italian: native"],
        ["Help Scout", "Shopify", "email support", "Excel"],
    ),
    Candidate(
        "cv20", "docx", "B", "Erika Exempel", ADDR.format(n=55), "1 May 1980",
        "Fictionalian", "Female", "Widowed", False,
        "Former teacher who worked in retail before teaching.",
        [
            Job("Teacher", "Sampletown Primary School (fictional)", "2008-08", "2026-07", [
                "Taught English and German to primary school children",
            ]),
            Job("Retail Sales Assistant", "Demo Department Store (fictional)", "2005-01",
                "2006-06", ["Served customers in the toy department"]),
        ],
        ["Master of Education, University of Sampletown, 2002 - 2008"],
        ["German: native", "English: C1"],
        ["Excel", "Microsoft PowerPoint"],
    ),
]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("cv*.*"):
        old.unlink()
    for c in CANDIDATES:
        path = OUT / f"{c.cid}.{c.fmt}"
        (write_pdf if c.fmt == "pdf" else write_docx)(c, path)
        print(f"wrote {path.relative_to(OUT.parent)}")


if __name__ == "__main__":
    main()
