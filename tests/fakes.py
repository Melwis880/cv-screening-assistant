"""A fake Anthropic client so the real extractor can be tested offline."""

import json
from types import SimpleNamespace


class FakeMessages:
    def __init__(self, payload, stop_reason="end_turn", usage=(1200, 400)):
        self.payload = payload
        self.stop_reason = stop_reason
        self.usage = usage
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payload(kwargs) if callable(self.payload) else self.payload
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=self.usage[0], output_tokens=self.usage[1]),
        )


class FakeClient:
    def __init__(self, payload, **kwargs):
        self.messages = FakeMessages(payload, **kwargs)


GOOD_PAYLOAD = {
    "skills": [{"name": "Zendesk", "evidence": "Zendesk, Shopify, live chat, email support"},
               {"name": "email support", "evidence": "Zendesk, Shopify, live chat, email support"}],
    "languages": [
        {"language": "German", "level": "native", "level_as_written": "native",
         "evidence": "German: native"},
        {"language": "English", "level": "C1", "level_as_written": "C1",
         "evidence": "English: C1"},
    ],
    "education": [{"level": "vocational", "field": "Retail Salesperson", "in_progress": False,
                   "evidence": "Vocational training as Retail Salesperson (IHK)"}],
    "experience": [{"title": "Customer Service Agent", "start": "2022-03", "end": "present",
                    "relevant_to_job": True,
                    "evidence": "Customer Service Agent, Example Shop GmbH (fictional) - "
                                "03/2022 - present"}],
}
