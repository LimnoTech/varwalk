"""Unit conversion for secondary datasets: :func:`convert_units` and
:func:`rate_to_amount`. docs/units.md sections 3-4.

Both work on annotated variables only (``quantity_kind`` is required),
on a wide table (one column per variable) or a Dataset, and return a new
object whose ``units`` are rewritten with ``registry.format_units`` --
explicit UDUNITS year names -- and whose ``history`` records the source
unit, the target unit and the year setting. A chemical basis or species
is never needed here: a change of what a value counts (mass, amount,
equivalents) belongs to ``chemistry.convert_amount``. Equivalents are
stored in mol with ``counting`` ``equivalents`` (UDUNITS has no ``eq``),
so rescaling ``meq m-2 s-1`` (stored ``mmol m-2 s-1``) to
``umol d-1 m-2`` is an ordinary conversion here, in any dimension, and
``counting`` is kept. A target written in ``eq`` is refused: on a
variable counted as equivalents with a hint to write it in mol; on any
other with a pointer to ``chemistry.convert_amount``, which knows the
species' charge.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from .dictionary import (
    HISTORY_MARK,
    as_moles,
    converted_ranges,
    counting_of,
    fields,
    float_values,
    has_equivalent,
    is_dataset,
    numerator_counts,
    present_ranges,
    require_kind,
    scaled,
    series_like,
    updated,
)

if TYPE_CHECKING:
    from datetime import datetime

    import pint

__all__ = ["RATE_TO_AMOUNT", "convert_units", "rate_to_amount"]

#: Each rate's quantity kind and the kind of the amount it accumulates.
#: Every pair whose amount kind exists in QUDT 3.5.2, plus
#: ``MolarFluxDensity`` -> ``AmountOfSubstancePerArea``, a local kind
#: (``qudt.local_kinds_table``): QUDT has no amount-per-area kind.
RATE_TO_AMOUNT = {
    "MassPerAreaTime": "MassPerArea",
    "MassFluxDensity": "MassPerArea",
    "VolumeFlowRate": "Volume",
    "VolumePerTime": "Volume",
    "VolumetricFlux": "VolumePerArea",
    "MassFlowRate": "Mass",
    "MassPerTime": "Mass",
    "MolarFlowRate": "AmountOfSubstance",
    "MolarFluxDensity": "AmountOfSubstancePerArea",
}

# offsets whose label is the period's start: start + one step is the
# period's end
_START_ANCHORED = re.compile(r"^\d*(?:MS|QS(?:-[A-Z]{3})?|YS(?:-[A-Z]{3})?|D|h|min|s)$")


def convert_units(
    data: Any,
    targets: Mapping[str, Any],
    *,
    registry: pint.UnitRegistry | None = None,
    now: datetime | None = None,
    mark: str = HISTORY_MARK,
) -> Any:
    """Convert annotated variables to new units: ``targets`` maps
    variable name to a unit string
    (``{"DUDP003": "kg ha-1 julian_year-1"}``) or a Unit of
    ``registry``.

    A Dataset converts through pint-xarray with ``registry`` passed
    explicitly; the converted variable's encoding is cleared, since the
    source's packing no longer fits. A table converts its column,
    keeping a nullable column nullable.

    Rescales within one counting in any dimension, keeping ``counting``.
    Refuses (``ValueError``) a variable with no ``quantity_kind``; a
    ``counting`` that is not one of ``COUNTINGS`` or conflicts with its
    kind; a target whose dimensions differ from the quantity kind's
    (mass <-> amount belongs to ``chemistry.convert_amount``); a
    dimensionless target whose numerator counts a mass where the
    source's counts an amount, or the reverse (``mg kg-1`` ->
    ``mmol mol-1``: that needs the molar masses of the substance and of
    its matrix, which no function here has; a bare ``1`` or ``percent``
    counts what its kind's numerator does); a source written in ``eq``
    (the message gives it written in mol); a target written in ``eq`` on
    a variable counted as equivalents (write it in mol: the message
    gives the target so written); a target in ``eq`` on any other
    variable, since changing what it counts needs the species' charge
    (use ``chemistry.convert_amount`` with that target); and a pint
    Quantity as a target. Writes ``units`` with ``format_units``,
    removes a ``units_iri`` that no longer fits
    (:func:`annotate.iri_fits`), converts a Dataset variable's
    ``valid_min``, ``valid_max``, ``valid_range`` and ``actual_range``
    with its values (they are in the variable's units), and appends to
    ``history``.

    ``mark`` opens each ``history`` line this writes, after its
    timestamp.
    """
    from . import qudt
    from .annotate import (
        _equivalent_hint,
        _kind_numerator_counts,
        iri_fits,
        validate_annotations,
    )
    from .registry import format_units, get_registry, parse_unit, year_setting
    from .validate import dimension_vector

    registry = registry if registry is not None else get_registry()
    if not targets:
        raise ValueError("convert_units needs at least one {variable: target unit}")
    setting = year_setting(registry)
    changes: dict[str, dict[str, Any]] = {}
    values: dict[str, Any] = {}
    history = []
    for name, target in targets.items():
        found = fields(data, name)
        kind = require_kind(name, found, "converting its units")
        counting = counting_of(found, name)
        try:
            source = parse_unit(found["units"], registry)
        except ValueError as err:
            raise ValueError(f"{name!r}: units {found['units']!r}: {err}") from err
        try:
            wanted = parse_unit(target, registry)
        except ValueError as err:
            raise ValueError(f"{name!r}: target {target!r}: {err}") from err
        if has_equivalent(source):
            hint = _equivalent_hint(source, registry)
            raise ValueError(f"{name!r}: units {found['units']!r}: {hint}")
        if has_equivalent(wanted):
            if counting == "equivalents":
                in_moles = format_units(as_moles(wanted), registry)
                raise ValueError(
                    f"{name!r}: target {target!r}: UDUNITS has no eq: write it in mol, "
                    f"{in_moles!r}, which keeps counting 'equivalents'"
                )
            counted = (
                f"counted as {counting}" if counting else "not counted as equivalents"
            )
            raise ValueError(
                f"{name!r} is {counted}: target {target!r}: counting it as equivalents "
                "needs the species' charge: use chemistry.convert_amount with "
                f"{target!r}"
            )
        try:
            kind_row = qudt.quantity_kind(kind)
        except ValueError as err:
            raise ValueError(f"{name!r}: quantity_kind {kind!r}: {err}") from err
        expected = kind_row["dimension_vector"]
        have = dimension_vector(source, registry)
        if have != expected:
            raise ValueError(
                f"{name!r} is {kind} ({expected}), but its units {found['units']!r} "
                f"have dimensions {have}; fix them with varwalk.annotate.annotate first"
            )
        actual = dimension_vector(wanted, registry)
        if actual != expected:
            raise ValueError(
                f"{name!r} is {kind} ({expected}), but {target!r} has dimensions "
                f"{actual}; mass <-> amount needs a molar mass and belongs to "
                "chemistry.convert_amount"
            )
        if expected.endswith("D1"):  # dimensionless: the numerator says what it counts
            fallback = _kind_numerator_counts(kind_row)
            had = numerator_counts(source) or fallback
            asked = numerator_counts(wanted) or fallback
            if had and asked and had != asked:
                raise ValueError(
                    f"{name!r} is {kind} in {found['units']!r}, a fraction counting "
                    f"{had}, but target {target!r} counts {asked}: a mass fraction and "
                    "a mole fraction differ by the molar masses of both the substance "
                    "and its matrix, which this layer does not have, so the conversion "
                    "is refused"
                )
        written = format_units(wanted, registry)
        values[name] = _converted(data, name, source, wanted, registry)
        change: dict[str, Any] = {"units": written}
        change.update(
            converted_ranges(
                data,
                name,
                lambda raw, s=source, w=wanted: (
                    registry.Quantity(raw, s).to(w).magnitude
                ),
            )
        )
        iri = found.get("units_iri")
        if iri is not None and not iri_fits(
            written, iri, kind, registry, counting=counting
        ):
            change["units_iri"] = None
        changes[name] = change
        history.append(
            f"convert_units: {name} {found['units']!r} -> {written!r} (year setting: "
            f"{setting})"
        )
    out = updated(data, changes, values=values, history=history, now=now, mark=mark)
    validate_annotations(out, registry=registry)
    return out


def _converted(
    data: Any,
    name: str,
    source: pint.Unit,
    wanted: pint.Unit,
    registry: pint.UnitRegistry,
) -> Any:
    if is_dataset(data):
        import pint_xarray  # noqa: F401  (registers the .pint accessor)
        import xarray as xr

        original = data[name]
        # no coordinates: their units attributes are not ours to parse
        bare = xr.DataArray(original.variable)
        converted = (
            bare.pint.quantify(source, unit_registry=registry)
            .pint.to(wanted)
            .pint.dequantify(format="cf")
        )
        result = original.copy(deep=False, data=converted.data)
        result.encoding = {}
        return result
    column = data[name]
    magnitudes = registry.Quantity(float_values(column), source).to(wanted).magnitude
    return series_like(column, magnitudes)


def rate_to_amount(
    data: Any,
    variables: Sequence[str],
    *,
    period: str | tuple[str, str] | list[str] = "time",
    freq: str | None = None,
    registry: pint.UnitRegistry | None = None,
    now: datetime | None = None,
    mark: str = HISTORY_MARK,
) -> Any:
    """Multiply rates by each period's actual length, giving the amount
    over the period.

    - ``period="time"`` names a coordinate (Dataset) or column or index
      level (table) holding each period's **start**; the end is one
      ``freq`` step later. ``freq`` is a start-anchored offset alias
      (``"MS"``, ``"YS"``, ``"QS"``, ``"D"``, ``"h"``). A Dataset infers
      it from the coordinate when omitted (``xarray.infer_freq``, which
      needs three values); a table must give it, because a long table
      repeats each time once per site.
    - ``period=("startDate", "endDate")`` (a tuple or a two-item list)
      names each period's start and end; the length is end - start. a
      source whose periods are built from whole weekly samples has
      months that are not calendar months and needs this form.

    Lengths come from the time values and their calendar: February 2024
    has 29 days, and a cftime ``noleap`` February 28. No year constant
    is used. The quantity kind changes by :data:`RATE_TO_AMOUNT`;
    ``units`` loses its per-time factor (``kg m-2 s-1`` -> ``kg m-2``).
    A Dataset variable's ``valid_min``, ``valid_max``, ``valid_range``
    and ``actual_range`` are removed (the factor differs per period, so
    no one range fits), and ``history`` says so. ``counting`` is kept: a
    rate of equivalents accumulates to an amount of equivalents. A
    period it cannot determine, a kind with no amount kind, and a
    ``counting`` that is not one of ``COUNTINGS`` or conflicts with its
    kind raise ``ValueError``.

    ``mark`` opens each ``history`` line this writes, after its
    timestamp.
    """
    from . import qudt
    from .annotate import validate_annotations
    from .registry import format_units, get_registry, parse_unit, year_setting
    from .validate import dimension_vector

    registry = registry if registry is not None else get_registry()
    if isinstance(variables, str) or not variables:
        raise ValueError("rate_to_amount takes a non-empty list of variable names")
    duplicated = sorted({v for v in variables if list(variables).count(v) > 1})
    if duplicated:
        raise ValueError(f"rate_to_amount: duplicate variable names {duplicated}")
    named = ", ".join(map(repr, variables))
    if (
        isinstance(period, (tuple, list))
        and len(period) == 2
        and all(isinstance(p, str) for p in period)
    ):
        period = (period[0], period[1])
    elif not isinstance(period, str):
        raise ValueError(
            f"{named}: period is a name or a (start, end) pair of names, not {period!r}"
        )
    if isinstance(period, tuple) and freq is not None:
        raise ValueError(f"{named}: give freq= or period=(start, end), not both")
    setting = year_setting(registry)
    plans = []
    for name in variables:
        found = fields(data, name)
        kind = require_kind(name, found, "turning its rate into an amount")
        counting_of(found, name)  # kept, so it must be readable
        amount_kind = RATE_TO_AMOUNT.get(kind)
        if amount_kind is None:
            raise ValueError(
                f"{name!r} is {kind}, which has no amount kind; rate_to_amount takes "
                f"{sorted(RATE_TO_AMOUNT)}"
            )
        try:
            rate = parse_unit(found["units"], registry)
        except ValueError as err:
            raise ValueError(f"{name!r}: units {found['units']!r}: {err}") from err
        amount = _without_time(name, rate, registry)
        expected = qudt.quantity_kind(amount_kind)["dimension_vector"]
        if dimension_vector(amount, registry) != expected:
            raise ValueError(f"{name!r}: {amount} is not {amount_kind} ({expected})")
        factor = registry.Quantity(1.0, rate * registry.Unit("s")).to(amount).magnitude
        try:
            written = format_units(amount, registry)
        except ValueError as err:
            raise ValueError(f"{name!r}: units {str(amount)!r}: {err}") from err
        plans.append((name, found, kind, amount_kind, written, factor))

    try:
        seconds, how = _period_seconds(data, period, freq)
    except ValueError as err:
        raise ValueError(f"{named}: {err}") from err
    changes: dict[str, dict[str, Any]] = {}
    values: dict[str, Any] = {}
    history = []
    for name, found, kind, amount_kind, written, factor in plans:
        values[name] = scaled(data, name, seconds * factor)
        changes[name] = {
            "units": written,
            "quantity_kind": amount_kind,
            "units_iri": None,
        }
        # each step has its own factor, so no single range fits the new
        # values
        dropped = present_ranges(data, name)
        changes[name].update(dict.fromkeys(dropped))
        removed = (
            f"; removed {', '.join(dropped)} (each period has its own factor)"
            if dropped
            else ""
        )
        history.append(
            f"rate_to_amount: {name} {found['units']!r} ({kind}) -> {written!r} "
            f"({amount_kind}) over each period's own length, {how}{removed} "
            f"(year setting: {setting})"
        )
    out = updated(data, changes, values=values, history=history, now=now, mark=mark)
    validate_annotations(out, registry=registry)
    return out


def _without_time(name: str, rate: pint.Unit, registry: pint.UnitRegistry) -> pint.Unit:
    """``rate`` with its one per-time factor removed. Built from the
    unit's own container, so the year preprocessor never re-reads a year
    name."""
    from pint.util import UnitsContainer

    time = registry.Unit("s").dimensionality
    kept, per_time = {}, []
    # pint exposes no public per-unit-name powers; the container is the
    # only faithful source
    for unit_name, power in rate._units.items():
        if registry.Unit(UnitsContainer({unit_name: 1})).dimensionality == time:
            per_time.append(power)
        else:
            kept[unit_name] = power
    if per_time != [-1]:
        raise ValueError(f"{name!r}: {rate} is not a rate with a single per-time unit")
    return registry.Unit(UnitsContainer(kept))


def _times(data: Any, name: str) -> Any:
    """The values of ``name`` as a DatetimeIndex or CFTimeIndex, one per
    row or time step."""
    import pandas as pd
    import xarray as xr

    if is_dataset(data):
        if name not in data.variables:
            raise ValueError(f"{name!r} is not a coordinate of the dataset")
        if data[name].ndim != 1:
            raise ValueError(f"{name!r} must be one-dimensional")
        index = data[name].to_index()
    elif name in data.columns:
        index = pd.Index(data[name])
    elif name in data.index.names:
        index = pd.Index(data.index.get_level_values(name))
    else:
        raise ValueError(f"{name!r} is not a column or index level of the table")
    if isinstance(index, (pd.DatetimeIndex, xr.CFTimeIndex)):
        return index
    try:
        return pd.DatetimeIndex(index)
    except (TypeError, ValueError) as err:
        raise ValueError(f"{name!r} does not hold times: {err}") from None


def _require_on_boundary(starts: Any, freq: str, how: str) -> None:
    """Every start must sit on ``freq``'s boundary; a start that does
    not (2024-01-15 with ``"MS"``) would measure a different length than
    the period it labels."""
    import pandas as pd

    if isinstance(starts, pd.DatetimeIndex):
        offset = pd.tseries.frequencies.to_offset(freq)
        on = [offset.is_on_offset(ts) for ts in starts]
    else:
        from xarray.coding.cftime_offsets import to_offset

        offset = to_offset(freq)
        on = [offset.onOffset(ts) for ts in starts]
    if not all(on):
        first = starts[on.index(False)]
        raise ValueError(
            f"the period start {first} is not on a {freq!r} boundary ({how}); "
            "pass period=(start, end) for periods that are not labelled by their start"
        )


def _period_seconds(data: Any, period: str | tuple[str, str], freq: str | None) -> Any:
    """Each period's length in seconds (a numpy array for a table, a
    DataArray along the time dimension for a Dataset), and a description
    of how it was found."""
    import numpy as np
    import xarray as xr

    if isinstance(period, tuple):
        start_name, end_name = period
        starts, ends = _times(data, start_name), _times(data, end_name)
        how = f"{start_name} to {end_name}"
    else:
        start_name = period
        starts = _times(data, period)
        inferred = freq is None
        if freq is None:
            if not is_dataset(data):
                raise ValueError(
                    f"cannot determine the period from the table's {period!r} column, "
                    "which repeats per site: give freq= (such as 'MS') or "
                    "period=(start, end)"
                )
            freq = xr.infer_freq(starts) if len(starts) >= 3 else None
            if freq is None:
                raise ValueError(
                    f"cannot determine the period length from {period!r}: give "
                    "freq= or period=(start, end)"
                )
        if not _START_ANCHORED.match(freq):
            if inferred:
                raise ValueError(
                    f"inferred freq {freq!r} does not label each period by its start; "
                    "pass freq= (a start-anchored alias such as 'MS', 'YS', 'QS', 'D' "
                    "or 'h') or period=(start, end)"
                )
            raise ValueError(
                f"freq {freq!r} does not label each period by its start; use a "
                "start-anchored alias such as 'MS', 'YS', 'QS', 'D' or 'h'"
            )
        _require_on_boundary(starts, freq, how=f"{period} + 1 {freq}")
        ends = starts.shift(1, freq)
        how = f"{period} + 1 {freq}"
    seconds = np.asarray((ends - starts).total_seconds(), dtype="float64")
    if not np.all(np.isfinite(seconds)) or np.any(seconds <= 0):
        raise ValueError(
            f"cannot determine every period from {how}: a length is missing or <= 0"
        )
    if is_dataset(data):
        return xr.DataArray(seconds, dims=data[start_name].dims), how
    return seconds, how
