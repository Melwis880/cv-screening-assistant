import pytest
from pydantic import ValidationError

from cv_screen.schema import Extraction, extraction_json_schema


def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from _objects(item)


def test_json_schema_is_strict():
    schema = extraction_json_schema()
    objects = list(_objects(schema))
    assert len(objects) >= 5
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])


def test_json_schema_keeps_property_named_title():
    exp = extraction_json_schema()["$defs"]["Experience"]
    assert "title" in exp["properties"]


def test_every_claim_requires_evidence():
    defs = extraction_json_schema()["$defs"]
    for name in ["Skill", "Language", "Education", "Experience"]:
        assert "evidence" in defs[name]["required"], name


def test_extraction_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Extraction.model_validate(
            {"skills": [], "languages": [], "education": [], "experience": [], "score": 99}
        )


def test_extraction_rejects_invalid_level():
    with pytest.raises(ValidationError):
        Extraction.model_validate({
            "skills": [], "education": [], "experience": [],
            "languages": [{"language": "German", "level": "fluent",
                           "level_as_written": "fluent", "evidence": "German: fluent"}],
        })


def test_extraction_requires_all_lists():
    with pytest.raises(ValidationError):
        Extraction.model_validate({"skills": []})
