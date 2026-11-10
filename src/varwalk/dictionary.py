"""A dataset's variable fields, read and written the same way for tables
and datacubes.

- **Tables** (DataFrames, one column per variable) keep one record per
  variable in ``attrs["variables"]``: the data-dictionary schema of
  ``varwalk.variables`` plus the annotation fields. The records are
  plain JSON types, so they survive a save to Parquet.
- **Datacubes** (xarray Datasets) keep the fields as variable attributes
  of the same names.

Every function that changes something returns a new object; its input is
never modified.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from functools import cache
from typing import TYPE_CHECKING, Any

from .variables import ANNOTATION_COLUMNS

if TYPE_CHECKING:
    import pandas as pd
    import pint

#: What opens each ``history`` line varwalk writes, after its timestamp.
HISTORY_MARK = " varwalk: "

#: The annotation fields, in order; defined in ``varwalk.variables``.
ANNOTATION_FIELDS = ANNOTATION_COLUMNS


#: What a chemical value counts: a mass, an amount (moles of ``basis``),
#: or equivalents (moles of charge, ``|charge|`` per mole of
#: ``species``). Required wherever ``species`` is set.
COUNTINGS = ("mass", "amount", "equivalents")


#: QUDT's roots of the kinds that count equivalents by definition;
#: :func:`equivalent_kinds` adds every kind of the shipped subset that
#: specializes one (``CationExchangeCapacity``).
EQUIVALENT_ROOTS = frozenset(
    {"EquivalentConcentration", "MolarEquivalent", "ReactiveChargePerMass"}
)
#: What varwalk reads and writes: the shared schema's ``units`` plus the
#: annotations.
FIELDS = ("units", *ANNOTATION_FIELDS)
#: CF range attributes, in a Dataset variable's units; they must change
#: with its values.
RANGE_ATTRS = ("valid_min", "valid_max", "valid_range", "actual_range")
#: The range attributes CF writes in packed (stored) units on a packed
#: variable.
_PACKED_RANGE_ATTRS = ("valid_min", "valid_max", "valid_range")


@cache
def equivalent_kinds() -> frozenset[str]:
    """Quantity kinds that count equivalents by definition:
    :data:`EQUIVALENT_ROOTS` and every kind of the shipped QUDT subset
    that specializes one, transitively. A variable of one counts
    equivalents without saying so, and a ``counting`` other than
    ``equivalents`` conflicts with it. Derived on first use (it reads
    the subset), and exported as ``EQUIVALENT_KINDS``."""
    from . import qudt

    specializes = qudt.quantity_kinds_table()["specialization_of"]
    kinds = set(EQUIVALENT_ROOTS)
    grown = True
    while grown:
        found = {
            str(name) for name, parents in specializes.items() if set(parents) & kinds
        } - kinds
        kinds |= found
        grown = bool(found)
    return frozenset(kinds)


def __getattr__(name: str) -> Any:
    if (
        name == "EQUIVALENT_KINDS"
    ):  # derived from the QUDT subset, so built on first use
        return equivalent_kinds()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def is_missing(value: Any) -> bool:
    """``None``, NaN, ``<NA>`` or a blank string."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, float):
        return value != value
    import pandas as pd

    return value is pd.NA


def is_dataset(data: Any) -> bool:
    """True for an xarray Dataset, False for a (Geo)DataFrame;
    ``TypeError`` otherwise."""
    import pandas as pd
    import xarray as xr

    if isinstance(data, xr.Dataset):
        return True
    if isinstance(data, pd.DataFrame):
        return False
    raise TypeError(
        f"expected a DataFrame or an xarray Dataset, not {type(data).__name__}"
    )


def _table_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records = df.attrs.get("variables")
    if not records:
        raise ValueError(
            "the table has no data dictionary in attrs['variables']; build one "
            "with varwalk.variables.variables_frame and store "
            "variables_to_records(...) there first"
        )
    return records


def _table_record(df: pd.DataFrame, name: str) -> dict[str, Any]:
    for record in _table_records(df):
        if record.get("name") == name:
            return record
    raise ValueError(
        f"{name!r} has no row in the table's data dictionary (attrs['variables'])"
    )


def _set(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: source[key]
        for key in FIELDS
        if key in source and not is_missing(source[key])
    }


def source_units(data: Any, name: str) -> str | None:
    """The unit string the source published for variable ``name``: a
    table's ``source_units`` record, or a Dataset variable's
    ``source_units`` attribute, else its ``units`` attribute (a Dataset
    opened from a file carries the file's own). ``None`` when there is
    none."""
    if is_dataset(data):
        attrs = data[name].attrs
        value = attrs.get("source_units")
        if is_missing(
            value
        ):  # absent or blank: the file's own ``units`` is what it published
            value = attrs.get("units")
    else:
        value = _table_record(data, name).get("source_units")
    return None if is_missing(value) else str(value)


def has_variable(data: Any, name: str) -> bool:
    """True when ``name`` is a data variable of a Dataset or a column of
    a table."""
    if is_dataset(data):
        return name in data.data_vars
    return name in data.columns


def fields(data: Any, name: str) -> dict[str, Any]:
    """The fields of variable ``name`` that are set (``units`` and the
    annotations). Raises ``ValueError`` when ``name`` is not a variable
    of ``data``."""
    if is_dataset(data):
        if name not in data.data_vars:
            have = sorted(str(n) for n in data.data_vars)
            raise ValueError(f"{name!r} is not a data variable; the dataset has {have}")
        return _set(data[name].attrs)
    if name not in data.columns:
        raise ValueError(
            f"{name!r} is not a column; the table has {[str(c) for c in data.columns]}"
        )
    return _set(_table_record(data, name))


def all_fields(data: Any) -> dict[str, dict[str, Any]]:
    """``{name: fields}`` for every data variable of a Dataset, or every
    row of a table's data dictionary (a table without one has none)."""
    if is_dataset(data):
        return {str(name): _set(data[name].attrs) for name in data.data_vars}
    return {
        str(record["name"]): _set(record)
        for record in data.attrs.get("variables") or []
    }


def is_annotated(found: Mapping[str, Any]) -> bool:
    """True when any annotation field is set."""
    return any(key in found for key in ANNOTATION_FIELDS)


def counting_problem(found: Mapping[str, Any]) -> str | None:
    """Why the variable's ``counting`` cannot be read, or ``None``: it
    is not one of :data:`COUNTINGS`, or its ``quantity_kind`` counts
    equivalents by definition (:func:`equivalent_kinds`) and it is not
    ``equivalents``."""
    given, kind = found.get("counting"), found.get("quantity_kind")
    if given is None:
        return None
    if given not in COUNTINGS:
        return f"counting {given!r} is not one of {list(COUNTINGS)}"
    if kind is not None and kind in equivalent_kinds() and given != "equivalents":
        return (
            f"quantity_kind {kind} counts equivalents, so counting {given!r} "
            "conflicts with it"
        )
    return None


def counting_of(found: Mapping[str, Any], name: str) -> str | None:
    """What variable ``name`` counts: its ``counting``, else
    ``equivalents`` when its ``quantity_kind`` counts equivalents by
    definition (:func:`equivalent_kinds`), else ``None``. Raises
    ``ValueError`` naming the variable when the ``counting`` given is
    not one of :data:`COUNTINGS` or conflicts with the kind
    (:func:`counting_problem`): every reader of ``counting`` comes
    through here, so a value written by hand is checked, not trusted."""
    if problem := counting_problem(found):
        raise ValueError(f"{name!r}: {problem}")
    counting = found.get("counting")
    kind = found.get("quantity_kind")
    if counting is None and kind is not None and kind in equivalent_kinds():
        return "equivalents"
    return counting


def exponent(vector: str, letter: str) -> int:
    """The exponent of ``letter`` in a QUDT dimension vector (``M`` is 1
    in ``A0E0L-3I0M1H0T0D0``)."""
    match = re.search(rf"{letter}(-?\d+)", vector)
    return int(match.group(1)) if match else 0


def require_kind(name: str, found: Mapping[str, Any], operation: str) -> str:
    """The variable's ``quantity_kind``; ``ValueError`` when it has
    none, or no ``units``."""
    kind = found.get("quantity_kind")
    if kind is None:
        raise ValueError(
            f"{name!r} has no quantity_kind; annotate it (varwalk.annotate.annotate) "
            f"before "
            f"{operation}"
        )
    if "units" not in found:
        raise ValueError(f"{name!r} has no units")
    return kind


def has_equivalent(unit: pint.Unit) -> bool:
    """True when ``unit`` counts equivalents (``meq l-1``), which
    UDUNITS cannot write."""
    return any("equivalent" in name for name in unit._units)


def numerator_dimensionality(unit: pint.Unit) -> Any:
    """The dimensionality of ``unit``'s numerator: the product of its
    positive-power units (``[mass]`` for ``mg kg-1``, ``[substance]``
    for ``umol mol-1``, none for ``1`` or ``percent``). Read from the
    unit's own container, never by re-parsing a name."""
    from pint.util import UnitsContainer

    registry = unit._REGISTRY
    numerator = {name: power for name, power in unit._units.items() if power.real > 0}
    return registry.Unit(UnitsContainer(numerator)).dimensionality


def numerator_counts(unit: pint.Unit) -> str | None:
    """What a dimensionless ``unit``'s numerator counts: ``amount`` when
    it holds an amount of substance, ``mass`` when it holds a mass and
    no amount, else ``None`` (``1``, ``percent``)."""
    dims = numerator_dimensionality(unit)
    if dims.get("[substance]", 0) > 0:
        return "amount"
    if dims.get("[mass]", 0) > 0:
        return "mass"
    return None


def as_moles(unit: pint.Unit) -> pint.Unit:
    """``unit`` with every equivalent written as a mole (``meq l-1`` ->
    ``mmol l-1``). Built from the unit's own container, never re-parsed,
    so the year preprocessor cannot touch it."""
    from pint.util import UnitsContainer

    renamed = {
        name.replace("equivalent", "mole"): power for name, power in unit._units.items()
    }
    return unit._REGISTRY.Unit(UnitsContainer(renamed))


def series_like(column: pd.Series, magnitudes: Any) -> pd.Series:
    """``magnitudes`` as a Series shaped like ``column``: nullable
    ``Float64`` when the column is a pandas extension dtype (so ``<NA>``
    stays ``<NA>``), else ``float64``."""
    import pandas as pd

    dtype = (
        "Float64"
        if isinstance(column.dtype, pd.api.extensions.ExtensionDtype)
        else "float64"
    )
    return pd.Series(magnitudes, index=column.index, name=column.name).astype(dtype)


def float_values(column: pd.Series) -> Any:
    """A table column as a float64 numpy array, ``<NA>`` as NaN."""
    import numpy as np

    return column.to_numpy(dtype="float64", na_value=np.nan)


def scaled(data: Any, name: str, factor: Any) -> Any:
    """Variable ``name`` multiplied by ``factor`` (a scalar, or one
    value per row or time step as a numpy array or DataArray), keeping
    its coordinates and attributes. A Dataset variable's encoding is
    cleared: the source's packing does not fit the new values."""
    if is_dataset(data):
        original = data[name]
        result = (original * factor).transpose(*original.dims)
        out = original.copy(deep=False, data=result.data)
        out.encoding = {}
        return out
    column = data[name]
    return series_like(column, float_values(column) * factor)


def converted_ranges(
    data: Any, name: str, convert: Callable[[Any], Any]
) -> dict[str, Any]:
    """The CF range attributes of Dataset variable ``name``, passed
    through ``convert`` (a function of a float64 array) like its values:
    they are in the variable's units, so left alone they would mask
    valid data after a conversion. A table has none (``{}``).

    Under CF, ``valid_*`` of a packed variable are in packed (stored)
    units and are unpacked first (``raw * scale_factor + add_offset``);
    ``actual_range`` is already unpacked. The converted variable's
    encoding is cleared, so the results are unpacked values. Each
    attribute keeps its container: a list stays a list, a scalar a
    float, an array an array."""
    import numpy as np

    if not is_dataset(data):
        return {}
    attrs, encoding = data[name].attrs, data[name].encoding
    packed = "scale_factor" in encoding or "add_offset" in encoding
    scale = encoding.get("scale_factor", 1)
    offset = encoding.get("add_offset", 0)
    out: dict[str, Any] = {}
    for key in RANGE_ATTRS:
        if key not in attrs:
            continue
        given = attrs[key]
        raw = np.asarray(given).astype("float64")
        if packed and key in _PACKED_RANGE_ATTRS:
            raw = raw * scale + offset
        moved = convert(raw)
        if isinstance(given, np.ndarray):
            out[key] = np.asarray(moved)
        elif isinstance(given, (list, tuple)):
            out[key] = [float(v) for v in np.atleast_1d(moved)]
        else:
            out[key] = float(moved)
    return out


def present_ranges(data: Any, name: str) -> list[str]:
    """The CF range attributes Dataset variable ``name`` carries (none
    for a table)."""
    if not is_dataset(data):
        return []
    return [key for key in RANGE_ATTRS if key in data[name].attrs]


def updated(
    data: Any,
    changes: Mapping[str, Mapping[str, Any]],
    *,
    values: Mapping[str, Any] | None = None,
    history: list[str],
    now: datetime | None = None,
    mark: str = HISTORY_MARK,
) -> Any:
    """A copy of ``data`` with the field ``changes`` applied (``None``
    removes a field), the new ``values`` of some variables (a Series for
    a table, a DataArray for a Dataset), and ``history`` lines appended
    to ``attrs["history"]``, each opened by ``mark`` after its
    timestamp."""
    if is_dataset(data):
        out = data.copy(deep=False)
        out.attrs = copy.deepcopy(dict(data.attrs))
        for name, new in (values or {}).items():
            out[name] = new
        for name, change in changes.items():
            variable = out.variables[name]
            attrs = dict(variable.attrs)
            _apply(attrs, change)
            variable.attrs = attrs
    else:
        out = data.copy(deep=False)
        out.attrs = copy.deepcopy(data.attrs)
        for name, new in (values or {}).items():
            out[name] = new
        for name, change in changes.items():
            _apply(_table_record(out, name), change)
    _append_history(out.attrs, history, now, mark)
    return out


def _apply(target: dict[str, Any], change: Mapping[str, Any]) -> None:
    for key, value in change.items():
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value


def _append_history(
    attrs: dict[str, Any],
    lines: list[str],
    now: datetime | None,
    mark: str = HISTORY_MARK,
) -> None:
    if not lines:
        return
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    added = "\n".join(f"{stamp}{mark}{line}" for line in lines)
    history = attrs.get("history")
    attrs["history"] = f"{history}\n{added}" if history else added
