"""Fixtures shared across test modules."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _forget_shown_annotation_warnings():
    """Each test sees an annotation warning afresh: ``varwalk.warnings``
    shows each one once per process, which would otherwise hide a
    warning from a test met earlier in another."""
    from varwalk.warnings import reset_shown

    reset_shown()
