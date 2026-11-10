"""QUDT dimension vectors from units, and quantity-kind checks.
docs/units.md sections 5-6.

A unit string carries dimension and scale only, so a variable's quantity
kind is declared, and :func:`check_quantity_kind` confirms the unit has
that kind's dimensions. That catches a basis written into a unit
(``g N m-2`` parses as gram * newton per m2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pint

__all__ = ["check_quantity_kind", "dimension_vector"]

# pint base dimension -> QUDT dimension-vector letter, in QUDT's order
# (A E L I M H T, then D)
_LETTERS = (
    ("[substance]", "A"),
    ("[current]", "E"),
    ("[length]", "L"),
    ("[luminosity]", "I"),
    ("[mass]", "M"),
    ("[temperature]", "H"),
    ("[time]", "T"),
)


def dimension_vector(units: Any, registry: pint.UnitRegistry | None = None) -> str:
    """The QUDT dimension vector of ``units``, e.g.
    ``A0E0L-3I0M1H0T0D0`` for ``mg l-1``. D is 1 only when every other
    exponent is 0. A pint Unit from any registry is accepted: dimensions
    do not depend on the year setting, so there is nothing to refuse.
    Raises ``ValueError`` for a non-integer exponent or a dimension QUDT
    has no letter for."""
    from .registry import get_registry, parse_unit

    registry = registry if registry is not None else get_registry()
    if isinstance(units, str):
        units = parse_unit(units, registry)
    dims = dict(units.dimensionality)
    unknown = sorted(set(dims) - {name for name, _ in _LETTERS})
    if unknown:
        raise ValueError(f"{units!r} has dimensions with no QUDT letter: {unknown}")
    parts = []
    for name, letter in _LETTERS:
        exponent = dims.get(name, 0)
        exponent_int = int(exponent)  # type: ignore[arg-type]
        if exponent != exponent_int:
            raise ValueError(
                f"{units!r} has a non-integer exponent for {name}: {exponent}"
            )
        parts.append(f"{letter}{exponent_int}")
    return "".join(parts) + ("D1" if not any(dims.values()) else "D0")


def check_quantity_kind(
    units: Any, quantity_kind: str, registry: pint.UnitRegistry | None = None
) -> None:
    """Raise unless ``quantity_kind`` is in the QUDT subset or the local
    kinds (QUDT first) and ``units`` has its dimensions. ``ValueError``
    for an unknown kind (``qudt.UnknownTermError``) or a dimension
    mismatch."""
    from . import qudt

    expected = qudt.quantity_kind(quantity_kind)["dimension_vector"]
    actual = dimension_vector(units, registry)
    if actual != expected:
        raise ValueError(
            f"{units!r} has dimensions {actual}, but {quantity_kind} has {expected}"
        )
