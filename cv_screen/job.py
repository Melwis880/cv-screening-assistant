"""Load and validate the job description YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from cv_screen.schema import CEFRLevel, EducationLevel


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str


class LanguageCriterion(_Base):
    type: Literal["language"]
    language: str
    min_level: CEFRLevel


class LanguageAnyCriterion(_Base):
    type: Literal["language_any"]
    languages: list[str]
    min_level: CEFRLevel


class ExperienceCriterion(_Base):
    type: Literal["experience_years"]
    min_years: float
    partly_min_years: float | None = None


class SkillCriterion(_Base):
    type: Literal["skill"]
    any_of: list[str]
    partly_any_of: list[str] = Field(default_factory=list)


class EducationCriterion(_Base):
    type: Literal["education"]
    min_level: EducationLevel


Criterion = Annotated[
    LanguageCriterion
    | LanguageAnyCriterion
    | ExperienceCriterion
    | SkillCriterion
    | EducationCriterion,
    Field(discriminator="type"),
]


class RelevantExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    keywords: list[str] = Field(default_factory=list)


class Criteria(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_have: list[Criterion]
    nice_to_have: list[Criterion] = Field(default_factory=list)


class JobSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    company: str = ""
    location: str = ""
    relevant_experience: RelevantExperience
    criteria: Criteria


def load_job(path: Path) -> JobSpec:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    job = JobSpec.model_validate(data)
    ids = [c.id for c in job.criteria.must_have + job.criteria.nice_to_have]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate criterion ids in {path}")
    return job
