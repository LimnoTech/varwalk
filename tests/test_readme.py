"""The README's example runs as written."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("pint_xarray")
pytest.importorskip("molmass")

README = Path(__file__).resolve().parents[1] / "README.md"


def test_the_readme_example_runs(capsys):
    text = README.read_text(encoding="utf-8")
    example = re.search(r"## Example\n+```python\n(.*?)```", text, re.S)
    assert example, "the README has no Python example under '## Example'"
    exec(compile(example.group(1), "README.md", "exec"), {})
    printed = capsys.readouterr().out
    assert "convert_units" in printed
    assert "varwalk:" in printed
