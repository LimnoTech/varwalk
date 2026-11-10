"""The annotation warnings: the classes, and a message shown once per process."""

from __future__ import annotations

import sys
import warnings

import pytest

from varwalk import warnings as vw
from varwalk.warnings import (
    AnnotationWarning,
    ReannotatedWarning,
    UnannotatedWarning,
    reset_shown,
    warn,
)


def test_the_warning_classes():
    assert issubclass(AnnotationWarning, UserWarning)
    assert issubclass(UnannotatedWarning, AnnotationWarning)
    assert issubclass(ReannotatedWarning, AnnotationWarning)


class _Shown:
    """Counts the warnings Python would print, under the interpreter's default filters."""

    def __init__(self):
        self.messages: list[str] = []

    def __call__(self, message, category, *args, **kwargs):
        self.messages.append(f"{category.__name__}: {message}")


@pytest.fixture
def default_filters(monkeypatch):
    """The default warning filters (as a script runs), with every printed warning counted."""
    shown = _Shown()
    with warnings.catch_warnings():
        warnings.resetwarnings()
        warnings.simplefilter("default")
        monkeypatch.setattr(warnings, "showwarning", shown)
        yield shown


def test_warn_issues_the_category_given_and_defaults_to_unannotated():
    with pytest.warns(UnannotatedWarning, match="^a message$"):
        warn("a message")
    with pytest.warns(ReannotatedWarning, match="^another$"):
        warn("another", ReannotatedWarning)


def test_a_warning_is_shown_once_per_process_however_often_it_is_met(default_filters):
    for _ in range(5):
        warn("the same message")
        with (
            warnings.catch_warnings()
        ):  # pandas and xarray do this; it resets the registry
            pass
    assert len(default_filters.messages) == 1
    assert "the same message" in default_filters.messages[0]


def test_an_error_filter_raises_every_time_even_after_the_warning_was_shown(
    default_filters,
):
    warn("a message")  # shown once
    for _ in range(2):
        with warnings.catch_warnings():
            warnings.simplefilter("error", AnnotationWarning)
            with pytest.raises(UnannotatedWarning, match="a message"):
                warn("a message")
    assert len(default_filters.messages) == 1


def test_an_always_filter_shows_every_repeat(default_filters):
    warnings.simplefilter("always", AnnotationWarning)
    for _ in range(3):
        warn("a message")
    assert len(default_filters.messages) == 3


def test_an_ignored_warning_is_still_shown_when_next_met_unfiltered(default_filters):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=AnnotationWarning)
        warn("a message")
    assert default_filters.messages == []
    warn("a message")
    warn("a message")
    assert len(default_filters.messages) == 1


def test_a_plain_string_filter_is_matched_as_the_standard_library_does(default_filters):
    # CPython stores some filters with plain-string fields (its own startup filter for
    # DeprecationWarning in __main__), and compares those for equality
    other = "not the message"  # a plain string, compared for equality
    warnings.filters.insert(0, ("ignore", other, AnnotationWarning, None, 0))
    warnings.filters.insert(0, ("error", None, AnnotationWarning, "elsewhere", 0))
    warnings._filters_mutated()  # type: ignore[attr-defined]
    warn("a message")
    assert len(default_filters.messages) == 1
    warnings.filters.insert(0, ("error", None, AnnotationWarning, vw.__name__, 0))
    warnings._filters_mutated()  # type: ignore[attr-defined]
    with pytest.raises(UnannotatedWarning):
        warn("a message")


def test_a_filter_naming_the_warning_line_matches():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        warnings.filterwarnings(
            "error", category=AnnotationWarning, module=vw.__name__, lineno=vw.WARN_LINE
        )
        with pytest.raises(UnannotatedWarning):
            warn("a message")


def test_context_aware_warnings_follow_the_interpreter_flag():
    expected = bool(getattr(sys.flags, "context_aware_warnings", False))
    assert vw._context_aware_warnings() is expected


def test_under_context_aware_warnings_the_filters_in_force_are_read(
    default_filters, monkeypatch
):
    # Python 3.14 with sys.flags.context_aware_warnings set: catch_warnings() keeps its filters
    # in a context variable, read through warnings._get_filters(), not warnings.filters
    in_force = [("error", None, AnnotationWarning, None, 0)]
    monkeypatch.setattr(vw, "_context_aware_warnings", lambda: True)
    monkeypatch.setattr(warnings, "_get_filters", lambda: in_force, raising=False)
    assert vw._action("a message", UnannotatedWarning) == "error"


def test_without_context_aware_warnings_the_module_filters_are_read(
    default_filters, monkeypatch
):
    # Python 3.12 and 3.13, or 3.14 without the flag: warnings.filters is the list in force
    monkeypatch.setattr(vw, "_context_aware_warnings", lambda: False)
    monkeypatch.setattr(
        warnings,
        "_get_filters",
        lambda: [("error", None, Warning, None, 0)],
        raising=False,
    )
    assert vw._action("a message", UnannotatedWarning) == "default"
    warnings.simplefilter("error", AnnotationWarning)
    assert vw._action("a message", UnannotatedWarning) == "error"


def test_context_aware_warnings_without_the_private_reader_fall_back(
    default_filters, monkeypatch
):
    monkeypatch.setattr(vw, "_context_aware_warnings", lambda: True)
    monkeypatch.delattr(warnings, "_get_filters", raising=False)
    assert vw._action("a message", UnannotatedWarning) == "default"


def test_reset_shows_a_warning_again(default_filters):
    warn("a message")
    reset_shown()
    warn("a message")
    assert len(default_filters.messages) == 2
