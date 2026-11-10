"""Chemical basis and amount: :func:`convert_basis` and
:func:`convert_amount`. docs/units.md section 5.

Every variable used needs ``species`` (the chemical entity, with its
charge: ``NO3-``) and ``basis`` (what the number counts: ``N`` for "as
nitrogen", or the species itself). Molar masses and charges come from
molmass, never typed by hand.

What a value counts is its ``counting`` (``annotate.COUNTINGS``), never
guessed from the unit:

- a **mass** counts grams of the basis;
- an **amount** (``mol``) counts moles of the basis: 100 umol/L of
  nitrate with basis ``N`` is 100 umol/L of N, which is 1.40 mg/L as N;
- **equivalents** count the species' charge:
  ``meq = mmol of species x |charge|``. They are written in ``mol`` with
  ``counting`` ``equivalents``, as CF does, because UDUNITS has no
  ``eq``.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from ._formula import basis_count, charge, formula, molar_mass
from .dictionary import (
    COUNTINGS,
    HISTORY_MARK,
    as_moles,
    converted_ranges,
    counting_of,
    equivalent_kinds,
    exponent,
    fields,
    has_equivalent,
    numerator_counts,
    require_kind,
    scaled,
    updated,
)

if TYPE_CHECKING:
    from datetime import datetime

    import pint

__all__ = [
    "AMOUNT_KINDS",
    "EQUIVALENT_KINDS",  # noqa: F822  (module __getattr__: derived from QUDT on first use)
    "basis_count",
    "charge",
    "convert_amount",
    "convert_basis",
    "formula",
    "molar_mass",
]

#: One quantity counted as a mass and as an amount of substance, per
#: row: the pairs ``convert_amount`` moves between for mass <-> amount
#: (and mass <-> equivalents, which are written in the amount kind).
#: ``AmountOfSubstancePerArea`` is a local kind
#: (``qudt.local_kinds_table``): QUDT has no amount-per-area kind. The
#: first row that matches is used, so an amount converts back to
#: ``MassConcentration`` from either concentration kind. Amount <->
#: equivalents needs no row: the quantity kind does not change, only
#: ``counting``.
AMOUNT_KINDS: tuple[tuple[str, str], ...] = (
    ("MassConcentration", "AmountOfSubstanceConcentration"),
    ("MassConcentration", "Concentration"),
    ("MassPerAreaTime", "MolarFluxDensity"),
    ("MassFluxDensity", "MolarFluxDensity"),
    ("Mass", "AmountOfSubstance"),
    ("MassFlowRate", "MolarFlowRate"),
    ("MassPerTime", "MolarFlowRate"),
    ("MassPerArea", "AmountOfSubstancePerArea"),
)

#: The dimensional kind ``convert_amount`` writes in place of each kind
#: that counts equivalents by definition (``EQUIVALENT_KINDS``), with
#: ``counting`` ``equivalents``: one form for every dimension.
_DIMENSIONAL_KIND = {
    "EquivalentConcentration": "AmountOfSubstanceConcentration",
    "MolarEquivalent": "AmountOfSubstance",
    "ReactiveCharge": "AmountOfSubstance",
    "ReactiveChargePerMass": "AmountOfSubstancePerMass",
    "CationExchangeCapacity": "AmountOfSubstancePerMass",
}


def __getattr__(name: str) -> Any:
    if name == "EQUIVALENT_KINDS":  # derived from the QUDT subset on first use
        return equivalent_kinds()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@contextmanager
def _naming(name: str) -> Generator[None]:
    """Prefix a refusal with the variable's name unless it already
    starts with it (a message that names the species ``'N'`` does not
    name the variable ``'N'``)."""
    try:
        yield
    except ValueError as err:
        if str(err).startswith(repr(name)):
            raise
        raise ValueError(f"{name!r}: {err}") from err


def _chemistry(name: str, found: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """The variable's quantity kind, species, basis and counting;
    ``ValueError`` naming the first one missing."""
    kind = require_kind(name, found, "a chemical conversion")
    missing = [key for key in ("species", "basis") if key not in found]
    if missing:
        raise ValueError(
            f"{name!r} has no {' or '.join(missing)}; a chemical conversion needs both"
        )
    counting = counting_of(found, name)
    if counting is None:
        raise ValueError(
            f"{name!r} has no counting; a chemical conversion needs to know whether it "
            f"counts {', '.join(COUNTINGS)}"
        )
    return kind, found["species"], found["basis"], counting


def _target_counting(name: str, unit: pint.Unit, registry: pint.UnitRegistry) -> str:
    """What a target unit asks for: ``equivalents`` (``eq`` in it),
    ``amount`` (``mol``), or ``mass`` (mass and no amount of substance).
    A dimensionless target is read by its numerator: ``mg kg-1`` asks
    for a mass, ``umol mol-1`` an amount, ``ueq mol-1`` equivalents."""
    from .validate import dimension_vector

    vector = dimension_vector(unit, registry)
    mass, substance = exponent(vector, "M"), exponent(vector, "A")
    if vector.endswith("D1"):
        counts = numerator_counts(unit)
        if counts == "amount":
            return "equivalents" if has_equivalent(unit) else "amount"
        if counts == "mass":
            return "mass"
    elif substance > 0:
        return "equivalents" if has_equivalent(unit) else "amount"
    elif substance == 0 and mass > 0:
        return "mass"
    raise ValueError(
        f"{name!r}: {unit} counts neither a mass nor an amount of substance"
    )


def convert_basis(
    data: Any,
    new_bases: Mapping[str, str],
    *,
    registry: pint.UnitRegistry | None = None,
    now: datetime | None = None,
    mark: str = HISTORY_MARK,
) -> Any:
    """Change the entity a value counts, keeping ``quantity_kind`` and
    ``units``: ``{"NH4": "N"}`` turns mg/L of NH4+ into mg/L as N.

    For a mass the factor is ``n_new x M(new) / (n_old x M(basis))``,
    where ``n`` is how many of a basis one species contains (14.007 /
    18.038 for NH4+ -> N); for an amount it is ``n_new / n_old``;
    equivalents count the species' charge and do not change. A Dataset
    variable's ``valid_min``, ``valid_max``, ``valid_range`` and
    ``actual_range`` are scaled with its values (packed ``valid_*``
    unpacked first). Refuses (``ValueError``) a new basis that is not a
    string, and one whose element the species does not contain.

    ``mark`` opens each ``history`` line this writes, after its
    timestamp.
    """
    from .annotate import validate_annotations
    from .registry import get_registry, year_setting

    registry = registry if registry is not None else get_registry()
    if not new_bases:
        raise ValueError("convert_basis needs at least one {variable: new basis}")
    setting = year_setting(registry)
    changes: dict[str, dict[str, Any]] = {}
    values: dict[str, Any] = {}
    history = []
    for name, new_basis in new_bases.items():
        if not isinstance(new_basis, str):
            raise ValueError(
                f"{name!r}: the new basis must be a string, not {new_basis!r}"
            )
        found = fields(data, name)
        _, species, basis, role = _chemistry(name, found)
        with _naming(name):
            old_count = basis_count(species, basis)
            new_count = basis_count(species, new_basis)
            new_mass = molar_mass(new_basis) if role == "mass" else 0.0
            old_mass = molar_mass(basis) if role == "mass" else 0.0
        if role == "mass":
            factor = new_count * new_mass / (old_count * old_mass)
        elif role == "amount":
            factor = new_count / old_count
        else:
            factor = 1.0
        values[name] = scaled(data, name, factor)
        changes[name] = {
            "basis": new_basis,
            **converted_ranges(data, name, lambda raw, f=factor: raw * f),
        }
        history.append(
            f"convert_basis: {name} ({species}) as {basis} -> as {new_basis}, "
            f"x{factor:.6g} (year setting: {setting})"
        )
    out = updated(data, changes, values=values, history=history, now=now, mark=mark)
    validate_annotations(out, registry=registry)
    return out


def _paired_kind(name: str, kind: str, counting: str) -> str:
    """The kind of ``kind`` counted the other way, mass <-> amount, from
    :data:`AMOUNT_KINDS`."""
    have, other = (0, 1) if counting == "mass" else (1, 0)
    for row in AMOUNT_KINDS:
        if row[have] == kind:
            return row[other]
    known = sorted({row[have] for row in AMOUNT_KINDS})
    raise ValueError(
        f"{name!r} is {kind} counted as {counting}; convert_amount moves mass <-> "
        f"amount for {known}"
    )


def convert_amount(
    data: Any,
    targets: Mapping[str, Any],
    *,
    registry: pint.UnitRegistry | None = None,
    now: datetime | None = None,
    mark: str = HISTORY_MARK,
) -> Any:
    """Convert between mass, amount and equivalents, in any dimension
    that has both forms: ``targets`` maps variable name to a unit in
    another counting (``"mg l-1"``, ``"umol l-1"``, ``"meq m-2 d-1"``).

    - mass <-> amount uses the molar mass of ``basis``, and the quantity
      kind changes by :data:`AMOUNT_KINDS` (``MassPerArea`` ->
      ``AmountOfSubstancePerArea``);
    - amount <-> equivalents uses ``|charge|`` of ``species`` (always
      positive) and how many of the basis one species contains; the
      quantity kind does not change, only ``counting``: 1 mmol m-2 d-1
      of Ca+2 is 2 meq m-2 d-1, both ``MolarFluxDensity``.

    What the source counts is its ``counting``; what the target counts
    is read from its unit: a ``mol`` target is an amount (moles of
    ``basis``), an ``eq`` target equivalents, whatever the source
    counts. Equivalents are written in moles (``meq m-2 d-1`` as
    ``mmol d-1 m-2``), and a kind that counts equivalents by definition
    is written as its dimensional kind (``EquivalentConcentration`` ->
    ``AmountOfSubstanceConcentration``, ``CationExchangeCapacity`` ->
    ``AmountOfSubstancePerMass``, with the ``counting`` it converts to).
    ``units``, ``counting`` and ``quantity_kind`` are written and
    ``units_iri`` is removed. A Dataset variable's ``valid_min``,
    ``valid_max``, ``valid_range`` and ``actual_range`` are scaled with
    its values (packed ``valid_*`` unpacked first). Refuses
    (``ValueError``) a target in the same counting (use
    ``convert_units``), equivalents of an uncharged species, a mass <->
    amount change for a kind :data:`AMOUNT_KINDS` lacks, and a target
    whose dimensions do not fit.

    ``mark`` opens each ``history`` line this writes, after its
    timestamp.
    """
    from . import qudt
    from .annotate import validate_annotations
    from .registry import format_units, get_registry, parse_unit, year_setting
    from .validate import dimension_vector

    registry = registry if registry is not None else get_registry()
    if not targets:
        raise ValueError("convert_amount needs at least one {variable: target unit}")
    setting = year_setting(registry)
    changes: dict[str, dict[str, Any]] = {}
    values: dict[str, Any] = {}
    history = []
    for name, target in targets.items():
        found = fields(data, name)
        kind, species, basis, role = _chemistry(name, found)
        with _naming(name):
            source = parse_unit(found["units"], registry)
            wanted = parse_unit(target, registry)
            target_role = _target_counting(name, wanted, registry)
        if target_role == role == "equivalents":
            raise ValueError(
                f"{name!r} is already counted as equivalents; rescale it with "
                "convert_units, writing the target in moles (for example "
                f"{found['units']!r}), not eq"
            )
        if target_role == role:
            raise ValueError(
                f"{name!r} is already counted as {role}; change its scale with "
                "convert_units"
            )
        dimensional = _DIMENSIONAL_KIND.get(kind, kind)
        if "mass" in (role, target_role):
            target_kind = _paired_kind(name, dimensional, role)
        else:
            target_kind = (
                dimensional  # amount <-> equivalents: the same quantity, recounted
            )
        written_unit = as_moles(wanted) if target_role == "equivalents" else wanted
        with _naming(name):
            expected = qudt.quantity_kind(target_kind)["dimension_vector"]
            actual = dimension_vector(written_unit, registry)
        if actual != expected:
            raise ValueError(
                f"{name!r}: the {target_role} form of {kind} would be {target_kind} "
                f"({expected}), which does not match the dimensions of the target "
                f"{target!r} ({actual})"
            )
        with _naming(name):
            z = abs(charge(species))
            if "equivalents" in (role, target_role) and z == 0:
                raise ValueError(
                    f"{name!r}: species {species!r} has no charge, so no equivalents"
                )
            n = basis_count(species, basis)
            per_mole = registry.Quantity(molar_mass(basis), "g mol-1")

        # one source unit, as moles of the basis
        one = registry.Quantity(1.0, source)
        if role == "mass":
            moles = one / per_mole
        elif role == "amount":
            moles = one
        else:
            moles = one * n / z
        # and as the target
        if target_role == "mass":
            factor = (moles * per_mole).to(wanted).magnitude
        elif target_role == "amount":
            factor = moles.to(wanted).magnitude
        else:
            factor = (moles * z / n).to(written_unit).magnitude

        with _naming(name):
            written = format_units(written_unit, registry)
        values[name] = scaled(data, name, factor)
        changes[name] = {
            "units": written,
            "quantity_kind": target_kind,
            "counting": target_role,
            "units_iri": None,
            **converted_ranges(data, name, lambda raw, f=factor: raw * f),
        }
        history.append(
            f"convert_amount: {name} {found['units']!r} ({kind}, {role}) -> "
            f"{written!r} ({target_kind}, {target_role}) as {basis}, "
            f"species {species}, x{factor:.6g} (year setting: {setting})"
        )
    out = updated(data, changes, values=values, history=history, now=now, mark=mark)
    validate_annotations(out, registry=registry)
    return out
