"""Chemical formulas through molmass: molar masses, charges and element counts, never
hand-typed. Private to varwalk; ``annotate`` and ``chemistry`` share it.

A formula is written as molmass reads it, with its charge: ``NO3-``, ``NH4+``, ``SO4-2`` (or
``SO4--``, ``[SO4]2-``), ``Ca+2``. molmass subtracts or adds the electrons' mass for a charge,
so ``NO3-`` weighs 62.0055 g/mol and the neutral ``NO3`` 62.0049 g/mol.
"""

from __future__ import annotations

from functools import cache
from typing import Any


@cache
def formula(text: str) -> Any:
    """``text`` as a ``molmass.Formula``. Raises ``ValueError`` when molmass cannot read it."""
    from molmass import Formula, FormulaError

    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{text!r} is not a chemical formula")
    try:
        parsed = Formula(text)
        _ = parsed.mass  # molmass parses lazily; force it so a bad formula fails here
    except (FormulaError, ValueError, KeyError) as err:
        raise ValueError(f"{text!r} is not a formula molmass can read: {err}") from None
    return parsed


def molar_mass(text: str) -> float:
    """The molar mass of ``text`` in g/mol."""
    return float(formula(text).mass)


def charge(text: str) -> int:
    """The charge of ``text`` (``-2`` for ``SO4-2``, ``0`` for a neutral formula)."""
    return int(formula(text).charge)


def _elements(text: str) -> dict[str, int]:
    """Element counts of ``text``, without the electrons molmass lists for a charge."""
    return {
        symbol: int(item.count)
        for symbol, item in formula(text).composition().items()
        if symbol != "e-"
    }


def basis_count(species: str, basis: str) -> int:
    """How many of ``basis`` one ``species`` contains: 1 when the basis is the species itself
    (charge aside, so ``NO3`` counts ``NO3-``), else the count of the basis element in it
    (2 for ``N`` in ``N2O``). Raises ``ValueError`` for an element the species lacks, and for
    a basis that is neither the species nor one atom of an element."""
    of_species, of_basis = _elements(species), _elements(basis)
    if of_basis == of_species:
        return 1
    if len(of_basis) == 1:
        ((element, count),) = of_basis.items()
        if count == 1:
            if element not in of_species:
                raise ValueError(
                    f"species {species!r} contains no {element}, so it cannot be counted as "
                    f"{basis!r}"
                )
            return of_species[element]
    raise ValueError(
        f"basis {basis!r} must be the species {species!r} itself or one element of it"
    )
