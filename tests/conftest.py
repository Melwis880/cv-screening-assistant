from datetime import date
from pathlib import Path

import pytest

from cv_screen.job import load_job

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
AS_OF = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Tests must never reach the network: no key, mock mode unless a test overrides it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MOCK_LLM", raising=False)


@pytest.fixture(scope="session")
def job():
    return load_job(ROOT / "job.yaml")


@pytest.fixture
def as_of():
    return AS_OF


CV_TEXT = """Erika Mustermann
Address: 12 Example Street, 10115 Sampletown
Email: erika.mustermann@example.com | Phone: +49 30 0000 0100
Date of birth: 14 March 1999 | Nationality: Fictionalian | Gender: Female | Marital status:
Single
[Photo]
Profile
Erika is a customer service agent. She enjoys solving problems in writing and her manager
describes her as calm.
Experience
Customer Service Agent, Example Shop GmbH (fictional) - 03/2022 - present
- Answered customer emails and live chat in Zendesk
Sales Assistant, Sampletown Fashion (fictional) - 08/2019 - 02/2022
- Advised customers on the shop floor
Education
Vocational training as Retail Salesperson (IHK), Sampletown Vocational School, 2016 - 2019
Languages
German: native
English: C1
French: B1
Skills
Zendesk, Shopify, live chat, email support, Excel
"""


@pytest.fixture
def cv_text():
    return CV_TEXT
