"""The .env loader only reads the tool's own settings, never e.g. ANTHROPIC_BASE_URL."""

import os

import pytest

from cv_screen.cli import _load_dotenv

ALLOWED = {"ANTHROPIC_API_KEY": "sk-test", "CV_SCREEN_MODEL": "some-model", "MOCK_LLM": "1"}
BLOCKED = {"ANTHROPIC_BASE_URL": "https://attacker.example", "HTTPS_PROXY": "http://proxy.example",
           "ANTHROPIC_AUTH_TOKEN": "stolen", "PYTHONPATH": "/tmp/evil", "SSL_CERT_FILE": "/tmp/ca"}


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for name in [*ALLOWED, *BLOCKED]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_only_allowlisted_variables_are_loaded(clean_env):
    lines = [f"{k}={v}" for k, v in {**ALLOWED, **BLOCKED}.items()]
    (clean_env / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _load_dotenv()
    for name, value in ALLOWED.items():
        assert os.environ.get(name) == value
    for name in BLOCKED:
        assert name not in os.environ, name


def test_existing_environment_wins(clean_env, monkeypatch):
    monkeypatch.setenv("CV_SCREEN_MODEL", "from-shell")
    (clean_env / ".env").write_text("CV_SCREEN_MODEL=from-file\n", encoding="utf-8")
    _load_dotenv()
    assert os.environ["CV_SCREEN_MODEL"] == "from-shell"
