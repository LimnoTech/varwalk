"""The variable model: a data dictionary with one row per variable.

A **data dictionary** (``variables_df``) has one row per variable,
indexed by ``name``, the source's own variable name. Its columns
(:data:`VARIABLE_COLUMNS`) come in groups:

- ``source_long_name``, ``source_description``, ``source_units`` -- the
  source's own words, carried verbatim. This is the provenance anchor.
- ``standard_name`` (CF Standard Name Table) and ``units`` (accepted by
  UDUNITS-2) -- only where one applies, never guessed.
- ``aliases`` -- ``{vocabulary: term}``, e.g.
  ``{"usgs_pcode": "00010", "hydromt": "temp"}``. Always a mapping: a
  USGS parameter code packs constituent, medium and units into one
  identifier, so an alias without its vocabulary means nothing.
- ``crosswalk_source`` and ``crosswalk_reference`` -- who asserts the
  ``standard_name``. Any non-empty string is accepted unless the caller
  passes ``crosswalk_sources``, the collection of values it allows.
  Aliases need no such column: each vocabulary implies who asserts it (a
  ``usgs_pcode`` alias is USGS's own code).
- ``quantity_kind``, ``counting``, ``units_iri``, ``species``,
  ``basis``, ``medium`` and ``process`` (:data:`ANNOTATION_COLUMNS`) --
  what a unit string cannot carry. This module only names and carries
  them; ``annotate.validate_annotations`` checks their values.

Stdlib-only at import time, so ``import varwalk.variables`` stays light.
pandas, xarray and cf-units are imported inside the functions that need
them.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Collection, Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd
    import xarray as xr

__all__ = [
    "ANNOTATION_COLUMNS",
    "VARIABLE_COLUMNS",
    "check_udunits",
    "describe_variables",
    "validate_variables_df",
    "variables_frame",
    "variables_of",
    "variables_to_records",
]

#: The data dictionary's columns, in order. Its index is ``name``, the
#: source's variable name.
VARIABLE_COLUMNS = (
    "source_long_name",
    "source_description",
    "source_units",
    "standard_name",
    "units",
    "aliases",
    "crosswalk_source",
    "crosswalk_reference",
)

#: The annotation columns that follow :data:`VARIABLE_COLUMNS`, in order
#: (``dictionary`` re-exports this as ``ANNOTATION_FIELDS``).
ANNOTATION_COLUMNS = (
    "quantity_kind",
    "counting",
    "units_iri",
    "species",
    "basis",
    "medium",
    "process",
)

_ALL_COLUMNS = (*VARIABLE_COLUMNS, *ANNOTATION_COLUMNS)


def _is_missing(value: Any) -> bool:
    import pandas as pd

    return (
        value is None
        or value is pd.NA
        or (isinstance(value, float) and math.isnan(value))
    )


#: A chemical basis written into a unit string, in the two forms sources
#: use: a hyphen before a letter (``kg-N/ha``, ``kg-ca/ha``) or an
#: ``as`` token (USGS's ``mg/l as N``). UDUNITS-2 reads the basis as a
#: unit symbol (newton, centiare, attosecond), so such a string is never
#: passed on as ``units``. A hyphen before a digit is an exponent
#: (``m-2``).
_BASIS_IN_UNITS = re.compile(r"-[^\W\d_]|(?<!\S)as(?!\S)")


def check_udunits(units: str | None) -> str | None:
    """Return ``units`` unchanged when UDUNITS-2 accepts it and it means
    what it says, else ``None`` -- never a guess.

    Checked with `cf-units <https://cf-units.readthedocs.io/>`_, the
    UDUNITS-2 wrapper the Iris project maintains (see docs/units.md
    section 2 for why not cfunits). cf-units' own ``unknown`` and
    ``no_unit`` are not units and give ``None``. Where cf-units is not
    installed the answer is ``None``: unknown, not invalid.

    A string that writes a chemical basis into the unit gives ``None``
    even where UDUNITS-2 parses it, because it parses as other units: a
    hyphen before a letter (``kg-N/ha`` is kilogram-newtons per hectare,
    ``kg-ca/ha`` kilogram-centiares) or an ``as`` token (``mg/l as N``
    is attosecond-newtons); a hyphen used as multiplication (``N-m``,
    ``kW-h``) is refused too, by design (unknown, not invalid).
    ``source_units`` keeps the string, and a curated annotation table
    gives the corrected ``units`` and the ``basis``. A basis set off by
    a space (``mg N/L``, ``g N m-2``) is not caught, because ``N m-2``
    is a legitimate unit; an annotation's ``quantity_kind`` exposes it
    (its dimensions do not match).
    """
    if not isinstance(units, str) or not units.strip():
        return None
    if _BASIS_IN_UNITS.search(units):
        return None
    try:
        import cf_units
    except ImportError:
        return None
    try:
        parsed = cf_units.Unit(units)
    except ValueError:
        return None
    if parsed.is_unknown() or parsed.is_no_unit():
        return None
    return units


def variables_frame(
    rows: Iterable[Mapping[str, Any]],
    *,
    crosswalk_sources: Collection[str] | None = None,
) -> pd.DataFrame:
    """Build a data dictionary from row mappings. Each row needs
    ``name``; any column in :data:`VARIABLE_COLUMNS` or
    :data:`ANNOTATION_COLUMNS` may be given, missing ones become
    ``<NA>`` (``aliases`` becomes ``{}``), and any other key raises
    ``ValueError``. The frame always has every column, shared ones
    first. ``crosswalk_sources`` is the collection of values
    ``crosswalk_source`` may take (:func:`validate_variables_df`)."""
    import pandas as pd

    records = [dict(row) for row in rows]
    allowed = {"name", *_ALL_COLUMNS}
    for record in records:
        if "name" not in record:
            raise ValueError(f"every data-dictionary row needs a 'name'; got {record}")
        unknown = sorted(set(record) - allowed)
        if unknown:
            raise ValueError(
                f"unknown data-dictionary column(s) {unknown}; allowed: "
                f"{sorted(allowed)}"
            )

    df = pd.DataFrame(records, columns=["name", *_ALL_COLUMNS])
    for column in ["name", *_ALL_COLUMNS]:
        if column != "aliases":
            df[column] = df[column].astype("string")
    df["aliases"] = [  # pyrefly: ignore[unsupported-operation]
        {} if _is_missing(aliases) else aliases for aliases in df["aliases"]
    ]
    df = df.set_index("name")
    validate_variables_df(df, crosswalk_sources=crosswalk_sources)
    return df


def validate_variables_df(
    variables_df: pd.DataFrame, *, crosswalk_sources: Collection[str] | None = None
) -> None:
    """Raise ``ValueError`` unless ``variables_df`` follows the
    data-dictionary schema.

    ``crosswalk_sources`` is the collection of values
    ``crosswalk_source`` may take. With the default ``None`` any
    non-empty string is accepted; a caller that names who may assert a
    ``standard_name`` passes its own set (``{"source", "curator"}``),
    and any other value raises. A ``crosswalk_source`` without a
    ``standard_name`` has nothing to describe, and is kept as it is.
    """
    if variables_df.index.name != "name":
        raise ValueError(
            f"a data dictionary is indexed by 'name', not {variables_df.index.name!r}"
        )
    if variables_df.index.hasnans:
        raise ValueError("a data dictionary has a variable with no name")
    duplicated = sorted(set(variables_df.index[variables_df.index.duplicated()]))
    if duplicated:
        raise ValueError(
            f"a data dictionary names each variable once; duplicated: {duplicated}"
        )
    if list(variables_df.columns) != list(_ALL_COLUMNS):
        raise ValueError(
            f"data-dictionary columns must be {list(_ALL_COLUMNS)}, got "
            f"{list(variables_df.columns)}"
        )
    for name, aliases in variables_df["aliases"].items():
        if not isinstance(aliases, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in aliases.items()
        ):
            raise ValueError(
                f"aliases for {name!r} must map vocabulary to term, "
                f"e.g. {{'usgs_pcode': '00010'}}; got {aliases!r}"
            )
    for name, source in variables_df["crosswalk_source"].items():
        if _is_missing(source):
            continue
        if crosswalk_sources is None:
            if not isinstance(source, str) or not source.strip():
                raise ValueError(
                    f"crosswalk_source for {name!r} must be a non-empty string; got "
                    f"{source!r}"
                )
        elif source not in crosswalk_sources:
            raise ValueError(
                f"crosswalk_source for {name!r} must be one of "
                f"{sorted(crosswalk_sources)}; got {source!r}"
            )


def variables_to_records(
    variables_df: pd.DataFrame, *, crosswalk_sources: Collection[str] | None = None
) -> list[dict[str, Any]]:
    """The data dictionary as JSON-safe row dicts (``<NA>`` becomes
    ``None``), for ``attrs``. An annotation column appears only where it
    is set, so an unannotated record is the shared columns alone.
    :func:`variables_frame` rebuilds the frame from them.
    ``crosswalk_sources`` is passed on to :func:`validate_variables_df`.
    """
    validate_variables_df(variables_df, crosswalk_sources=crosswalk_sources)
    records = []
    for name, row in variables_df.iterrows():
        record: dict[str, Any] = {"name": str(name)}
        for column in VARIABLE_COLUMNS:
            value = row[column]
            if column == "aliases":
                record[column] = dict(value)
            else:
                record[column] = None if _is_missing(value) else str(value)
        for column in ANNOTATION_COLUMNS:
            if not _is_missing(row[column]):
                record[column] = str(row[column])
        records.append(record)
    return records


def variables_of(
    obj: pd.DataFrame | xr.Dataset, *, crosswalk_sources: Collection[str] | None = None
) -> pd.DataFrame:
    """The data dictionary ``obj`` carries: a table's
    ``attrs["variables"]`` records, or a Dataset's variable attributes
    (:func:`describe_variables`). Always every column of
    :func:`variables_frame`; an object with no dictionary gives an empty
    one. ``crosswalk_sources`` is passed on to the check of
    ``crosswalk_source`` (:func:`validate_variables_df`)."""
    import pandas as pd

    if isinstance(obj, pd.DataFrame):
        return variables_frame(
            obj.attrs.get("variables") or [], crosswalk_sources=crosswalk_sources
        )
    return describe_variables(obj, crosswalk_sources=crosswalk_sources)


def _read_aliases(name: str, raw: Any) -> dict[str, str]:
    """Decode a variable's ``aliases`` attribute, or raise
    ``ValueError`` naming the variable."""
    if not isinstance(raw, str):
        return {}
    problem = (
        f"variable {name!r} has an 'aliases' attribute that is not a JSON object of "
    )
    problem += f"vocabulary to term: {raw!r}"
    try:
        aliases = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(problem) from None
    if not isinstance(aliases, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in aliases.items()
    ):
        raise ValueError(problem)
    return aliases


def describe_variables(
    ds: xr.Dataset, *, crosswalk_sources: Collection[str] | None = None
) -> pd.DataFrame:
    """The data dictionary of ``ds``: one row per data variable, read
    from its attributes.

    ``long_name`` and ``description`` are the source's own words,
    carried verbatim into ``source_long_name`` and
    ``source_description``. ``source_units`` is the ``source_units``
    attribute where present (an annotated variable, whose ``units`` an
    annotation set), else ``units``. ``units`` is the ``units``
    attribute where ``source_units`` is present and differs from it (an
    annotation corrected the published unit), else it repeats the
    published unit only when UDUNITS-2 accepts it. The annotation
    attributes (``quantity_kind``, ``counting``, ...) are read as
    columns; this reads, it never annotates. ``standard_name``,
    ``aliases`` (a JSON object string), ``crosswalk_source`` and
    ``crosswalk_reference`` are read where present -- written by the
    source, or by whoever described the dataset. A ``standard_name``
    without a stated ``crosswalk_source`` came from the source; aliases
    carry no crosswalk source, their vocabulary implies it. Only data
    variables are described; coordinates are not. ``crosswalk_sources``
    is passed on to :func:`validate_variables_df`.
    """
    rows = []
    for name, variable in ds.data_vars.items():
        attrs = variable.attrs
        aliases = _read_aliases(str(name), attrs.get("aliases"))
        standard_name = attrs.get("standard_name")
        crosswalk_source = attrs.get("crosswalk_source") or (
            "source" if standard_name else None
        )
        # An annotation corrected the published unit: ``source_units``
        # is kept and differs.
        corrected = attrs.get("source_units", attrs.get("units")) != attrs.get("units")
        rows.append(
            {
                "name": str(name),
                "source_long_name": attrs.get("long_name"),
                "source_description": attrs.get("description"),
                "source_units": attrs.get("source_units", attrs.get("units")),
                "standard_name": standard_name,
                "units": attrs.get("units")
                if corrected
                else check_udunits(attrs.get("units")),
                "aliases": aliases,
                "crosswalk_source": crosswalk_source,
                "crosswalk_reference": attrs.get("crosswalk_reference"),
                **{column: attrs.get(column) for column in ANNOTATION_COLUMNS},
            }
        )
    return variables_frame(rows, crosswalk_sources=crosswalk_sources)
