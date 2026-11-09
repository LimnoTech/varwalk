"""Smoke test: the package imports and knows its version."""

from __future__ import annotations


def test_package_imports_and_has_a_version():
    import varwalk

    assert isinstance(varwalk.__version__, str)
    assert varwalk.__version__
