from __future__ import annotations

import tomllib
from pathlib import Path


def test_aiohttp_dependency_allows_home_assistant_pin() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]

    assert "aiohttp>=3.13.5,<4" in project["dependencies"]
