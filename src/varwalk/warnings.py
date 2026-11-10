"""The annotation warnings: the ``AnnotationWarning`` family and
:func:`warn`.

**The data always arrives**: an annotation that cannot be made is a
warning from this family, never an exception. Each warning is shown once
per process under the default filters, however many results a loop
annotates: :func:`warn` remembers each ``(category, message)`` it
showed, since Python's own registry is cleared by every
``warnings.catch_warnings()``. To see every repeat,
``warnings.simplefilter("always", AnnotationWarning)``; to silence them,
``warnings.filterwarnings("ignore", category=AnnotationWarning)``. A
filter that makes them errors raises at every meeting, even for a
message already shown.

Only the standard library is imported here, so
``import varwalk.warnings`` stays light.
"""

from __future__ import annotations

import sys
import warnings
from typing import Any

__all__ = [
    "WARN_LINE",
    "AnnotationWarning",
    "ReannotatedWarning",
    "UnannotatedWarning",
    "reset_shown",
    "warn",
]


class AnnotationWarning(UserWarning):
    """A result's annotations are not what its curated table says: some
    are missing, or the stored ones were replaced. The data itself is
    always complete.

    Each message is shown once per process;
    ``warnings.simplefilter("always", AnnotationWarning)`` shows every
    repeat, and an ``"error"`` filter raises every time."""


class UnannotatedWarning(AnnotationWarning):
    """Some or all of a result's variables could not be annotated, so
    they carry no quantity kind, counting, species or basis. Shown once
    per process, as :class:`AnnotationWarning`."""


class ReannotatedWarning(AnnotationWarning):
    """A result's stored annotations differ from the current
    curated table: replaced by it for a variable still as published,
    kept for a secondary dataset's variable. Shown once per process, as
    :class:`AnnotationWarning`."""


#: The ``(category, message)`` pairs already shown under a once-only
#: filter action.
_shown: set[tuple[type[AnnotationWarning], str]] = set()


def reset_shown() -> None:
    """Forget which annotation warnings were shown, here and in Python's
    registry for this module, so each is shown once more
    (tests/conftest.py calls it before every test)."""
    _shown.clear()
    globals().pop("__warningregistry__", None)


def _context_aware_warnings() -> bool:
    """Whether ``catch_warnings()`` keeps its filters in a context
    variable: Python 3.14+ with ``sys.flags.context_aware_warnings`` set
    (by default in the free-threaded build, or with
    ``-X context_aware_warnings``). False on 3.12 and 3.13, which have
    no such flag."""
    return bool(getattr(sys.flags, "context_aware_warnings", False))


def _action(message: str, category: type[Warning]) -> str:
    """The action the active warning filters give a warning issued from
    :func:`_issue`, matched as ``warnings.warn_explicit`` matches (first
    filter wins, then ``warnings.defaultaction``)."""
    # Mirrors warn_explicit's filter search in CPython 3.12 to 3.14
    # (3.14 checked in its Lib/_py_warnings.py, 2026-11-07). Under
    # context-aware warnings, catch_warnings() puts its filters in a
    # context variable and warn_explicit reads them through
    # warnings._get_filters(), a private function (3.14+), leaving
    # warnings.filters as the process-wide list; elsewhere
    # warnings.filters is the list in force.
    for action, text, kind, module, lineno in _filters_in_force():
        if (
            _matches(text, message)
            and issubclass(category, kind)
            and _matches(module, __name__)
            and lineno in (0, WARN_LINE)
        ):
            return action
    return str(
        getattr(warnings, "defaultaction", "default")
    )  # not in the typeshed stubs


def _filters_in_force() -> list[Any]:
    """The warning filters ``warnings.warn`` would search now (see
    :func:`_action`)."""
    if _context_aware_warnings():
        get_filters = getattr(warnings, "_get_filters", None)  # private, 3.14+
        if get_filters is not None:
            return list(get_filters())
    return list(warnings.filters)


def _matches(pattern: Any, text: str) -> bool:
    """A filter field matched as the standard library matches it:
    ``None`` matches anything, a plain ``str`` (as CPython stores its
    own startup filters) by equality, a regex by match."""
    if pattern is None:
        return True
    if type(pattern) is str:
        return pattern == text
    return bool(pattern.match(text))


def warn(message: str, category: type[AnnotationWarning] = UnannotatedWarning) -> None:
    """Issue an annotation warning, each ``(category, message)`` shown
    once per process.

    Python's own once-per-location registry cannot do this: every
    ``warnings.catch_warnings()`` (pandas and xarray enter one
    internally) clears it, so a loop fetching five results showed five
    copies. A message is therefore skipped here when it was already
    shown under a once-only action (``default``, ``module``, ``once``).
    Every other action is passed to Python every time: ``error`` raises
    at each meeting, even after the message was shown; ``always`` shows
    every repeat; ``ignore`` shows nothing and does not count as shown.
    """
    key = (category, message)
    if _action(message, category) in _ONCE_ACTIONS:
        if key in _shown:
            return
        _shown.add(key)
    _issue(message, category)


def _issue(message: str, category: type[AnnotationWarning]) -> None:
    warnings.warn(message, category, stacklevel=1)  # every warning comes from this line


#: The line ``_issue`` warns from, for a filter that names a line
#: number.
WARN_LINE = _issue.__code__.co_firstlineno + 1
#: The filter actions under which Python itself would show a message
#: only once.
_ONCE_ACTIONS = frozenset({"default", "module", "once"})
