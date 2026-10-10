"""Dependencies have a floor and an upper bound; pypdf is new enough for its DoS fixes."""

import re
import tomllib

from packaging.requirements import Requirement
from packaging.version import Version

from tests.conftest import ROOT

PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
REQUIREMENTS = [Requirement(r) for r in PROJECT["dependencies"]
                + PROJECT["optional-dependencies"]["dev"]]


def test_every_dependency_has_a_floor_and_an_upper_bound():
    for req in REQUIREMENTS:
        ops = {spec.operator for spec in req.specifier}
        assert ">=" in ops and "<" in ops, req


def test_pypdf_floor():
    pypdf = next(r for r in REQUIREMENTS if r.name == "pypdf")
    floor = next(s.version for s in pypdf.specifier if s.operator == ">=")
    assert Version(floor) >= Version("6.1")


def test_requirements_are_plain_names():
    for raw in PROJECT["dependencies"]:
        assert re.fullmatch(r"[A-Za-z0-9_.-]+[<>=!,.\d ]+", raw), raw  # no URLs or VCS refs
