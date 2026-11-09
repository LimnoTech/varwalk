"""Importing varwalk loads none of the heavy scientific packages."""

from __future__ import annotations

import subprocess
import sys

import pytest

HEAVY = ("pint", "pandas", "xarray", "cf_xarray", "cf_units", "molmass")


@pytest.mark.parametrize("module", ["varwalk", "varwalk.variables", "varwalk.warnings"])
def test_importing_loads_no_heavy_package(module):
    code = f"import sys, {module}; print([m for m in {HEAVY!r} if m in sys.modules])"
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "[]"
