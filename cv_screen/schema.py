"""Strict data model shared by the extractors, the matcher and the reports.

`Extraction` is what an extractor (LLM or mock) must return. Every claim carries a verbatim
evidence quote from the (redacted) CV text. `CandidateProfile` is the verified result after
quotes have been checked and years of relevant experience computed in code.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CEFRLevel = Literal["A1", "A2", "B1", "B2", "C1", "C2", "native"]
EducationLevel = Literal["secondary", "vocational", "bachelor", "master", "doctorate", "other"]
Status = Literal["met", "partly", "not met", "unknown"]

CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]
EDUCATION_ORDER = ["secondary", "vocational", "bachelor", "master", "doctorate"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Skill(Strict):
    name: str = Field(description="Skill or tool as written in the CV, e.g. 'Zendesk'.")
    evidence: str = Field(description="Verbatim quote from the CV that shows this skill.")


class Language(Strict):
    language: str = Field(description="Language name in English, e.g. 'German'.")
    level: CEFRLevel | None = Field(
        description="CEFR level only if the CV states it, or 'native' for native/mother tongue. "
        "null if the CV uses words like 'fluent' or gives no level."
    )
    level_as_written: str | None = Field(description="The level exactly as written, if any.")
    evidence: str = Field(description="Verbatim quote from the CV.")


class Education(Strict):
    level: EducationLevel
    field: str | None = Field(description="Subject or trade, if stated.")
    in_progress: bool = Field(description="True if not yet completed.")
    evidence: str = Field(description="Verbatim quote from the CV.")


class Experience(Strict):
    title: str = Field(description="Job title as written.")
    start: str | None = Field(description="Start as YYYY-MM or YYYY; null if not stated.")
    end: str | None = Field(
        description="End as YYYY-MM or YYYY, 'present' if ongoing; null if not stated."
    )
    relevant_to_job: bool = Field(
        description="True if the role matches the job's definition of relevant experience."
    )
    evidence: str = Field(description="Verbatim quote from the CV, ideally the line with dates.")


class Extraction(Strict):
    skills: list[Skill]
    languages: list[Language]
    education: list[Education]
    experience: list[Experience]


class CandidateProfile(Strict):
    candidate_id: str
    source_file: str
    extraction: Extraction
    years_relevant_experience: float | None
    undated_relevant_roles: int
    dropped_claims: list[str] = Field(
        default_factory=list,
        description="Claims removed because their evidence quote was not found in the CV.",
    )
    warnings: list[str] = Field(default_factory=list)


class CriterionResult(Strict):
    criterion_id: str
    label: str
    must_have: bool
    status: Status
    evidence: str | None
    note: str


def extraction_json_schema() -> dict[str, Any]:
    """JSON schema for structured outputs: every property required, no extra keys, no titles."""
    return _strictify(copy.deepcopy(Extraction.model_json_schema()))


def _strictify(node: Any) -> Any:
    if isinstance(node, dict):
        # Only strip annotation keys, never a property that happens to be called "title".
        if isinstance(node.get("title"), str):
            node.pop("title")
        node.pop("default", None)
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"])
            node["additionalProperties"] = False
            for prop in node["properties"].values():
                _strictify(prop)
        for key, value in node.items():
            if key != "properties":
                _strictify(value)
    elif isinstance(node, list):
        for item in node:
            _strictify(item)
    return node
