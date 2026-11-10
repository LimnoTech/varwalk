"""Annotations: what a unit string cannot carry -- quantity kind, what
the value counts, species, basis, medium and process -- on the variables
of a dataset. docs/units.md section 5.

**Where the fields live.** A table keeps them in its
``attrs["variables"]`` records, beside the data-dictionary columns; a
datacube keeps them as variable attributes of the same names. The schema
in ``varwalk.variables`` carries them (``ANNOTATION_COLUMNS``,
re-exported here as ``ANNOTATION_FIELDS``): a data dictionary always has
those columns, ``<NA>`` where a variable is not annotated, and a record
in ``attrs["variables"]`` has a key only where the field is set.
:func:`annotated_variables` is ``variables.variables_of``.

**Counting.** ``counting`` says what a chemical value counts --
``mass``, ``amount`` (moles of ``basis``) or ``equivalents`` (moles of
charge) -- which neither the unit nor the quantity kind can:
``mmol m-2 d-1`` and ``meq m-2 d-1`` share ``MolarFluxDensity``. It is
required wherever ``species`` is set, with no default. Equivalents are
written in moles, as CF does (``..._expressed_as_mole_equivalent``),
because UDUNITS has no ``eq``: ``meq/L`` is written ``mmol l-1`` with
``counting`` ``equivalents``. A kind in ``EQUIVALENT_KINDS``
(``EquivalentConcentration``, ``CationExchangeCapacity``, ...) still
means equivalents: :func:`annotate` writes the ``counting`` it implies.

**Curated tables.** :func:`read_table` reads and validates a curated
annotation table from a CSV file: one row per source variable, each
stating the ``source_units`` it was curated for. :func:`annotate` takes
such a table (a DataFrame indexed by ``name``) or a plain mapping.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .dictionary import (
    ANNOTATION_FIELDS,
    COUNTINGS,
    FIELDS,
    HISTORY_MARK,
    all_fields,
    counting_of,
    counting_problem,
    equivalent_kinds,
    exponent,
    fields,
    has_equivalent,
    has_variable,
    is_annotated,
    is_missing,
    numerator_counts,
    source_units,
    updated,
)

if TYPE_CHECKING:
    from datetime import datetime

    import pandas as pd
    import pint

__all__ = [
    "ANNOTATION_FIELDS",
    "COUNTINGS",
    "PROCESSES",
    "NoRowFitsError",
    "annotate",
    "annotated_variables",
    "clear_table_cache",
    "iri_fits",
    "read_table",
    "validate_annotations",
]

#: The ``process`` vocabulary. It mirrors CF's
#: ``..._due_to_wet_deposition``; it grows when a new use needs a new
#: process.
PROCESSES = frozenset(
    {"wet_deposition", "dry_deposition", "total_deposition", "precipitation", "none"}
)


def _equivalent_hint(unit: pint.Unit, registry: pint.UnitRegistry) -> str:
    """Why a unit written in ``eq`` is refused, with that unit written
    in mol."""
    from .dictionary import as_moles
    from .registry import format_units

    in_moles = format_units(as_moles(unit), registry)
    return (
        "UDUNITS has no eq: write equivalents in mol with counting "
        f"'equivalents' ({in_moles!r})"
    )


def read_table(path: Path) -> pd.DataFrame:
    """Read and validate one curated annotation table, indexed by
    ``name``. The file is a CSV with a ``name`` column, a
    ``quantity_kind`` column, optionally ``source_units``, and any of
    the annotation fields and ``units`` (a blank cell is "not given"). A
    name the source publishes in several units has a row for each, every
    one stating its ``source_units``. Raises ``ValueError`` for a
    missing column, an unknown column, a name repeated with the same or
    a blank ``source_units``. Returns a copy of a table read once per
    path and cached; :func:`clear_table_cache` forgets what was read."""
    return _read_table(path).copy()


def clear_table_cache() -> None:
    """Forget the tables :func:`read_table` has read, so a file changed
    on disk is read afresh."""
    _read_table.cache_clear()


@functools.cache
def _read_table(path: Path) -> pd.DataFrame:
    """Read and validate one table file; cached, so callers copy it."""
    import pandas as pd

    table = pd.read_csv(path, dtype=str, keep_default_na=False, engine="pyarrow")
    if "name" not in table.columns:
        raise ValueError(f"{path.name} has no 'name' column")
    unknown = sorted(set(table.columns) - {"name", "source_units", *FIELDS})
    if unknown:
        allowed = ["source_units", *FIELDS]
        raise ValueError(
            f"{path.name} has unknown column(s) {unknown}; allowed: {allowed}"
        )
    if "quantity_kind" not in table.columns:
        raise ValueError(f"{path.name} has no 'quantity_kind' column")
    table = table.set_index("name")
    _check_rows(table, path.name)
    return table


def _check_rows(table: pd.DataFrame, what: str) -> None:
    """A name appears once, or once per ``source_units``, each of its
    rows stating one."""
    repeated = table.index[table.index.duplicated()]
    if not len(repeated):
        return
    if "source_units" not in table.columns:
        raise ValueError(
            f"{what} names a variable more than once: {sorted(set(repeated))}"
        )
    rows = table.loc[sorted(set(repeated))]
    blank = sorted({str(n) for n, su in rows["source_units"].items() if is_missing(su)})
    if blank:
        raise ValueError(
            f"{what} has several rows for {blank}, so each must state its source_units"
        )
    keys = list(zip(rows.index, rows["source_units"], strict=True))
    twice = sorted({key for key in keys if keys.count(key) > 1})
    if twice:
        raise ValueError(
            f"{what} names a variable and source_units more than once: {twice}"
        )


def annotate(
    data: Any,
    annotations: Mapping[str, Mapping[str, Any]] | pd.DataFrame,
    *,
    registry: pint.UnitRegistry | None = None,
    now: datetime | None = None,
    mark: str = HISTORY_MARK,
) -> Any:
    """A copy of a table or Dataset with annotation fields added, then
    validated.

    ``annotations`` maps variable name to fields, or is a DataFrame
    indexed by name (such as :func:`read_table` returns). ``mark`` opens
    the ``history`` line written, after its timestamp. Blank and missing
    values are "not given".

    - A **DataFrame** is a curated table for a whole dataset, so its
      rows for variables the data does not hold are skipped: a table
      works when only some variables were extracted. Where it has
      ``source_units``, each variable takes the row for the unit its
      source published (``source_units`` in a table's data dictionary; a
      Dataset variable's ``source_units`` attribute, else its
      ``units``), or, for a Dataset that already carries the row's
      ``quantity_kind`` (a re-annotation, since the first one rewrote
      its ``units``), the row whose ``units`` it already has; a variable
      no row fits raises ``ValueError``, so a table never annotates
      another product or a source that changed its unit.
    - A **mapping** names the variables the caller means, so a name
      absent from the data raises ``ValueError`` (a typo there would
      otherwise annotate nothing).

    - A field already set to a different value raises ``ValueError``:
      re-annotation never overwrites.
    - ``units`` is the one shared-schema field an annotation may
      replace, because a published unit can pass UDUNITS and still be
      wrong (UDUNITS reads ``kg-N/ha`` as kg·newton per ha, so
      ``check_udunits`` leaves such a ``units`` empty and the annotation
      sets it). It may correct a unit, never relabel values: replacing a
      unit by another of the same dimensions but a different scale
      raises. Each replacement is recorded in ``history``. A unit set
      where the source had none is recorded with the source's own
      string: ``set n_dw units 'kg ha-1' (source_units 'kg-N/ha')``. The
      scale guard cannot run when there is no old unit or pint cannot
      read it; for a curated table the ``source_units`` match guards
      instead, since a row applies only to data published in the unit it
      names.
    - ``quantity_kind`` is required for every variable annotated, even
      by a units-only correction.
    - A variable whose ``quantity_kind`` is a kind in
      ``EQUIVALENT_KINDS`` (one that counts equivalents by definition,
      such as ``EquivalentConcentration``) and has no ``counting`` gets
      ``counting`` ``equivalents``.
    - A source's ``units`` is left as written unless the annotation
      supplies ``units`` (which then goes through ``format_units``), so
      a bare ``yr`` or ``year`` stays ambiguous until corrected. Curated
      tables should state ``units`` for every variable.
    """
    return _annotate(
        data, annotations, registry=registry, now=now, label="annotate", mark=mark
    )


def _annotate(
    data: Any,
    annotations: Mapping[str, Mapping[str, Any]] | pd.DataFrame,
    *,
    registry: pint.UnitRegistry | None,
    now: datetime | None,
    label: str,
    mark: str = HISTORY_MARK,
) -> Any:
    """:func:`annotate`, with ``label`` opening its history line:
    ``annotate`` for a direct call, or a longer one such as
    ``annotate from table <table>`` for a caller that annotates from a
    curated table."""
    import pandas as pd

    from .registry import format_units, get_registry, year_setting

    registry = registry if registry is not None else get_registry()
    if isinstance(annotations, pd.DataFrame):
        # a curated table covers a whole dataset; a dataset may hold
        # only some of it, and one name may have a row for each unit the
        # source publishes it in
        annotations = _rows_for(data, annotations, registry)
    wanted = _as_mapping(annotations)
    changes: dict[str, dict[str, Any]] = {}
    replaced = []
    for name, given in wanted.items():
        current = fields(data, name)
        if given and "quantity_kind" not in current and "quantity_kind" not in given:
            raise ValueError(
                f"{name}: quantity_kind is required on every annotated variable, "
                f"including "
                "one given only a units correction"
            )
        change: dict[str, Any] = {}
        for key, value in given.items():
            if key == "units":
                try:
                    value = format_units(value, registry)
                except ValueError as err:
                    raise ValueError(f"{name!r}: units {value!r}: {err}") from None
                if value != current.get("units"):
                    _check_correction(name, current.get("units"), value, registry)
                    change["units"] = value
                    replaced.append(
                        _units_note(data, name, current.get("units"), value)
                    )
            elif key not in current:
                change[key] = value
            elif current[key] != value:
                raise ValueError(
                    f"{name!r} is already annotated {key}={current[key]!r}; refusing "
                    f"to "
                    f"change it to {value!r}"
                )
        kind = change.get("quantity_kind", current.get("quantity_kind"))
        if (
            kind in equivalent_kinds()
            and "counting" not in current
            and "counting" not in given
        ):
            change["counting"] = "equivalents"  # what the kind means, stated
        if change:
            changes[name] = change
    history = []
    if changes:
        line = f"{label}: {sorted(changes)}"
        if replaced:
            line += "; " + "; ".join(replaced)
        history.append(f"{line} (year setting: {year_setting(registry)})")
    out = updated(data, changes, history=history, now=now, mark=mark)
    validate_annotations(out, registry=registry)
    return out


class NoRowFitsError(ValueError):
    """A curated table names a variable, and none of its rows is for the
    unit the source published it in (``published``; ``None`` when it has
    none). ``listed`` is the table's ``source_units`` for that name;
    ``found`` is ``"no row"`` or ``"more than one row"``."""

    def __init__(
        self, name: str, published: str | None, listed: list[str | None], found: str
    ):
        self.name, self.published, self.listed, self.found = (
            name,
            published,
            listed,
            found,
        )
        super().__init__(
            f"{name}: the source published it in {published!r}, and the annotation "
            f"table has "
            f"{found} for that (its source_units are {listed}); it is another product "
            f"or "
            "the source changed its unit, so the table cannot say what the values are"
        )


def _rows_for(
    data: Any, table: pd.DataFrame, registry: pint.UnitRegistry
) -> pd.DataFrame:
    """The rows of a curated ``table`` for the variables ``data`` holds,
    one per variable, and without ``source_units``. Where the table has
    ``source_units``, a variable takes the row whose ``source_units`` is
    the unit the source published it in (a blank one matches any). A
    Dataset variable that already carries a row's ``quantity_kind`` also
    takes that row when its ``units`` are the row's (a re-annotation,
    since a Dataset's own ``units`` is rewritten); a fresh Dataset never
    does, because a row's ``units`` write an equivalent as a mole. A
    table record keeps ``source_units`` verbatim, so it matches by that
    alone. A variable that matches no row, or more than one, raises
    ``ValueError``: the data is another product or the source changed
    its unit, and the table cannot say what the values are."""
    import pandas as pd

    from .dictionary import is_dataset
    from .registry import format_units

    _check_rows(table, "the annotation table")
    names = [str(n) for n in dict.fromkeys(table.index) if has_variable(data, str(n))]
    if "source_units" not in table.columns:
        return table.loc[names]
    dataset = is_dataset(data)
    chosen = []
    for name in names:
        rows = table.loc[[name]]
        published = source_units(data, name)
        have = fields(data, name) if dataset else {}
        current = have.get("units")
        hits = []
        for position, (given, units) in enumerate(
            zip(
                rows["source_units"], rows.get("units", [None] * len(rows)), strict=True
            )
        ):
            if is_missing(given) or given == published:
                hits.append(position)
            elif current is not None and not is_missing(units):
                kind = (
                    rows["quantity_kind"].iloc[position]
                    if "quantity_kind" in rows
                    else None
                )
                if (
                    not is_missing(kind)
                    and have.get("quantity_kind") == kind
                    and format_units(units, registry) == current
                ):
                    hits.append(position)
        if len(hits) != 1:
            listed = [None if is_missing(u) else u for u in rows["source_units"]]
            found = "no row" if not hits else "more than one row"
            raise NoRowFitsError(name, published, listed, found)
        chosen.append(rows.iloc[[hits[0]]])
    if not chosen:
        return table.iloc[0:0].drop(columns="source_units")
    return pd.concat(chosen).drop(columns="source_units")


def _units_note(data: Any, name: str, old: str | None, new: str) -> str:
    """The history note for an annotation that sets or replaces
    ``units``."""
    if old is not None:
        return f"replaced {name} units {old!r} -> {new!r}"
    published = source_units(data, name)
    of = "" if published is None else f" (source_units {published!r})"
    return f"set {name} units {new!r}{of}"


def _as_mapping(
    annotations: Mapping[str, Mapping[str, Any]] | pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    import pandas as pd

    if isinstance(annotations, pd.DataFrame):
        if annotations.index.has_duplicates:
            dup = sorted(
                {str(n) for n in annotations.index[annotations.index.duplicated()]}
            )
            raise ValueError(f"the annotations name a variable more than once: {dup}")
        rows = {str(name): row.to_dict() for name, row in annotations.iterrows()}
    elif isinstance(annotations, Mapping):
        rows = {name: dict(row) for name, row in annotations.items()}
    else:
        raise ValueError(
            f"annotations are a mapping or a DataFrame, not "
            f"{type(annotations).__name__}"
        )
    out = {}
    for name, row in rows.items():
        unknown = sorted(set(row) - set(FIELDS))
        if unknown:
            raise ValueError(
                f"unknown annotation field(s) {unknown} for {name!r}; allowed: "
                f"{list(FIELDS)}"
            )
        given = {key: value for key, value in row.items() if not is_missing(value)}
        for key, value in given.items():
            if not isinstance(value, str):
                raise ValueError(f"{name!r}: {key} must be a string, not {value!r}")
        out[name] = given
    return out


def _check_correction(
    name: str, old: str | None, new: str, registry: pint.UnitRegistry
) -> None:
    """An annotation may correct a wrong unit, never relabel values with
    another scale."""
    from .registry import parse_unit

    if old is None:
        return
    try:
        old_unit, new_unit = parse_unit(old, registry), parse_unit(new, registry)
    except ValueError:
        # an unreadable old unit is what corrections are for; a bad new
        # one fails below
        return
    if old_unit.dimensionality != new_unit.dimensionality:
        return
    factor = registry.Quantity(1.0, old_unit).to(new_unit).magnitude
    if not math.isclose(factor, 1.0, rel_tol=1e-9):
        raise ValueError(
            f"{name!r}: units: the values are in {old!r}, and 1 {old!r} is {factor:g} "
            f"{new!r}; an "
            "annotation corrects a unit, it does not relabel values -- use "
            "convert_units"
        )


def validate_annotations(
    data_or_variables_df: Any, *, registry: pint.UnitRegistry | None = None
) -> None:
    """Check every annotated variable, and raise one ``ValueError``
    listing every problem.

    Takes a table, a Dataset, or an annotated data dictionary: any
    DataFrame indexed by ``name`` with a ``units`` or annotation column
    (such as :func:`annotated_variables` or :func:`read_table` returns).
    A missing ``quantity_kind`` column is not an error of the frame;
    each annotated variable without one is reported. A variable with no
    annotation field is not checked.

    - ``quantity_kind`` is present, in the QUDT subset or the local
      kinds (``qudt.local_kinds_table``), and not deprecated (a
      deprecated kind is reported with its ``replaced_by``);
    - ``units`` is present, UDUNITS-valid, and has the quantity kind's
      dimensions;
    - ``units_iri``, if present, is in the subset, not deprecated, a
      unit of that quantity kind (or of a kind it specializes; for a
      local kind, a unit with its dimension vector), and has pint's
      conversion factor (:func:`iri_fits`);
    - ``species`` and ``basis`` come together, molmass reads both, and
      the basis is the species itself or one element of it;
    - ``counting`` is present wherever ``species`` is (a kind in
      ``EQUIVALENT_KINDS`` implies ``equivalents``), one of
      :data:`COUNTINGS`, agrees with an equivalents kind, and fits the
      unit: ``mass`` needs mass and no amount of substance, ``amount``
      and ``equivalents`` need mol. A dimensionless unit is judged by
      its numerator (``mg kg-1`` counts a mass, ``umol mol-1`` an
      amount), or, when that holds neither (``1``, ``percent``), by the
      kind's numerator (``MassFraction``'s is a mass); ``equivalents``
      needs a charged species;
    - ``process`` is in :data:`PROCESSES`.

    ``medium`` is not checked: the ODM2 Medium vocabulary is not
    shipped.
    """
    from .registry import get_registry

    registry = registry if registry is not None else get_registry()
    problems = []
    for name, found in _records(data_or_variables_df).items():
        if is_annotated(found):
            problems += _problems(name, found, registry)
    if problems:
        raise ValueError(
            "invalid annotations:\n" + "\n".join(f"- {p}" for p in problems)
        )


def _records(obj: Any) -> dict[str, dict[str, Any]]:
    import pandas as pd

    if (
        isinstance(obj, pd.DataFrame)
        and obj.index.name == "name"
        and any(column in FIELDS for column in obj.columns)
    ):
        _check_rows(obj, "the annotation table")
        repeated = obj.index.duplicated(keep=False)
        out = {}
        for (name, row), again in zip(obj.iterrows(), repeated, strict=True):
            # a name with a row per published unit is reported as "name
            # [source_units]"
            key = f"{name} [{row['source_units']}]" if again else str(name)
            out[key] = {
                field: row[field]
                for field in FIELDS
                if field in row.index and not is_missing(row[field])
            }
        return out
    return all_fields(obj)


def _deprecated(row: pd.Series, what: str) -> str | None:
    if not row["deprecated"]:
        return None
    replacement = row["replaced_by"]
    hint = "" if is_missing(replacement) else f"; use {replacement}"
    return f"{what} is deprecated in QUDT{hint}"


def _problems(
    name: str, found: Mapping[str, Any], registry: pint.UnitRegistry
) -> list[str]:
    from . import qudt
    from ._formula import basis_count, formula
    from .registry import parse_unit
    from .validate import dimension_vector
    from .variables import check_udunits

    out = []
    kind = found.get("quantity_kind")
    kind_row = None
    if kind is None:
        out.append(f"{name}: quantity_kind is required on an annotated variable")
    else:
        try:
            kind_row = qudt.quantity_kind(kind)
        except qudt.UnknownTermError as err:
            out.append(f"{name}: quantity_kind {err}")
        else:
            if note := _deprecated(kind_row, f"quantity_kind {kind}"):
                out.append(f"{name}: {note}")

    units = found.get("units")
    unit = None
    vector = None
    if units is None:
        out.append(f"{name}: units is required on an annotated variable")
    else:
        try:
            unit = parse_unit(units, registry)
        except ValueError as err:
            out.append(f"{name}: {err}")
        if unit is not None and has_equivalent(unit):
            out.append(f"{name}: units {units!r}: {_equivalent_hint(unit, registry)}")
            unit = None
        elif check_udunits(units) is None:
            out.append(f"{name}: units {units!r} is not a string UDUNITS-2 accepts")
        if unit is not None:
            try:
                vector = dimension_vector(unit, registry)
            except ValueError as err:
                out.append(f"{name}: {err}")
        if vector is not None and kind_row is not None:
            if vector != kind_row["dimension_vector"]:
                out.append(
                    f"{name}: units {units!r} has dimensions {vector}, but {kind} has "
                    f"{kind_row['dimension_vector']}"
                )

    iri = found.get("units_iri")
    if iri is not None:
        # a counting that cannot be read is reported below, with the
        # other counting problems
        counting = None if counting_problem(found) else counting_of(found, name)
        out += [
            f"{name}: {p}"
            for p in _iri_problems(units, iri, kind, registry, counting=counting)
        ]

    species, basis = found.get("species"), found.get("basis")
    if (species is None) != (basis is None):
        given = "species" if species is not None else "basis"
        out.append(f"{name}: species and basis go together; only {given} is given")
    readable = True
    for field, value in (("species", species), ("basis", basis)):
        if value is not None:
            try:
                formula(value)
            except ValueError as err:
                readable = False
                out.append(f"{name}: {field} {err}")
    if species is not None and basis is not None and readable:
        try:
            basis_count(species, basis)
        except ValueError as err:
            out.append(f"{name}: {err}")

    out += [
        f"{name}: {p}"
        for p in _counting_problems(name, found, unit, vector, kind_row, readable)
    ]

    process = found.get("process")
    if process is not None and process not in PROCESSES:
        out.append(f"{name}: process {process!r} is not one of {sorted(PROCESSES)}")
    return out


def _counting_problems(
    name: str,
    found: Mapping[str, Any],
    unit: pint.Unit | None,
    vector: str | None,
    kind_row: pd.Series | None,
    readable: bool,
) -> list[str]:
    """``counting``: required wherever ``species`` is, readable
    (:func:`counting_problem`: in :data:`COUNTINGS` and agreeing with an
    equivalents kind), fitting the unit, and ``equivalents`` only for a
    charged species. A dimensional unit fits by its dimension
    ``vector``; a dimensionless one by its numerator (``mg kg-1`` holds
    a mass), or by the kind's numerator when the unit's holds neither a
    mass nor an amount (``1``, ``percent``)."""
    from ._formula import charge

    species = found.get("species")
    if problem := counting_problem(found):
        return [problem]
    counting = counting_of(found, name)
    if counting is None:
        if species is None:
            return []
        return [
            f"counting is required wherever species is set: one of {list(COUNTINGS)} "
            f"(there is "
            "no default, so moles are never read as the wrong count)"
        ]
    out = []
    if vector is not None and unit is not None:
        if vector.endswith("D1"):  # dimensionless: what its numerator counts
            counts = numerator_counts(unit) or _kind_numerator_counts(kind_row)
            has_mass, has_amount = counts == "mass", counts == "amount"
        else:
            has_amount = exponent(vector, "A") > 0
            has_mass = exponent(vector, "M") > 0 and exponent(vector, "A") == 0
        if counting == "mass" and not has_mass:
            out.append(
                f"counting 'mass' needs a unit with mass and no amount of substance; "
                f"{found['units']!r} has dimensions {vector}"
            )
        elif counting != "mass" and not has_amount:
            out.append(
                f"counting {counting!r} needs a unit in mol; {found['units']!r} has "
                f"dimensions {vector}"
            )
    if (
        counting == "equivalents"
        and species is not None
        and readable
        and charge(species) == 0
    ):
        out.append(
            f"counting 'equivalents' needs a charged species; {species!r} has no charge"
        )
    return out


def _kind_numerator_counts(kind_row: pd.Series | None) -> str | None:
    """What a dimensionless kind's QUDT numerator counts
    (``MassFraction``: a mass; ``MoleFraction``: an amount), or
    ``None``."""
    numerator = kind_row["qkdv_numerator"] if kind_row is not None else None
    if not isinstance(numerator, str):
        return None
    if exponent(numerator, "A") > 0:
        return "amount"
    if exponent(numerator, "M") > 0:
        return "mass"
    return None


def _kind_and_ancestors(kind: str) -> set[str]:
    """``kind`` and every kind it specializes, transitively."""
    from . import qudt

    seen: set[str] = set()
    todo = [kind]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            todo.extend(qudt.quantity_kind(current)["specialization_of"])
        except qudt.UnknownTermError:
            pass
    return seen


def _iri_problems(
    units: str | None,
    iri: str,
    kind: str | None,
    registry: pint.UnitRegistry,
    *,
    counting: str | None = None,
) -> list[str]:
    from . import qudt
    from .registry import parse_unit

    try:
        row = qudt.unit(iri)
    except qudt.UnknownTermError as err:
        return [f"units_iri {err}"]
    out = []
    if note := _deprecated(row, f"units_iri {iri}"):
        out.append(note)
    kinds = {str(k) for k in row["quantity_kinds"]}
    if kind is not None and counting == "equivalents":
        # QUDT has equivalents units only under its equivalents kinds
        # (MilliEQ-PER-L under EquivalentConcentration), so one fits a
        # variable counting equivalents in its dimension
        if not kinds & equivalent_kinds():
            out.append(
                f"units_iri {iri} is a unit of {sorted(kinds)}, which count moles of a "
                "substance, but the variable counts equivalents"
            )
        else:
            try:
                expected = qudt.quantity_kind(kind)["dimension_vector"]
            except qudt.UnknownTermError:
                expected = row["dimension_vector"]  # reported with quantity_kind
            if row["dimension_vector"] != expected:
                out.append(
                    f"units_iri {iri} has dimensions {row['dimension_vector']}, but "
                    f"{kind} has "
                    f"{expected}"
                )
    elif kind is not None and qudt.is_local_kind(kind):
        # QUDT cannot list a kind it lacks, so a local kind is matched
        # by dimension
        expected = qudt.quantity_kind(kind)["dimension_vector"]
        if row["dimension_vector"] != expected:
            out.append(
                f"units_iri {iri} has dimensions {row['dimension_vector']}, but {kind} "
                f"has "
                f"{expected}"
            )
    elif kind is not None and not kinds & _kind_and_ancestors(kind):
        out.append(f"units_iri {iri} is a unit of {sorted(kinds)}, not of {kind}")
    multiplier, offset = row["conversion_multiplier"], row["conversion_offset"]
    if is_missing(multiplier):
        out.append(
            f"units_iri {iri} has no conversion factor in QUDT (not convertible)"
        )
        return out
    if units is None:
        return out
    try:
        unit = parse_unit(units, registry)
    except ValueError:
        return out  # reported with the units
    if has_equivalent(unit):
        return out  # reported with the units
    for value in (0.0, 1.0):
        expected = (value + offset) * multiplier
        actual = registry.Quantity(value, unit).to_base_units().magnitude
        if not math.isclose(actual, expected, rel_tol=1e-6):
            out.append(
                f"units_iri {iri} is {multiplier:g} SI units per unit, but {units!r} "
                f"is "
                f"{registry.Quantity(1.0, unit).to_base_units().magnitude:g}"
            )
            break
    return out


def iri_fits(
    units: str,
    iri: str,
    kind: str | None,
    registry: pint.UnitRegistry | None = None,
    *,
    counting: str | None = None,
) -> bool:
    """True when the QUDT unit ``iri`` describes ``units`` of quantity
    kind ``kind``: in the subset, not deprecated, a unit of the kind (or
    of one it specializes; for a local kind, one with its dimension
    vector), and with pint's conversion factor. With ``counting``
    ``equivalents`` the unit must be one of QUDT's equivalents units
    (``MilliEQ-PER-L``) with the kind's dimension vector, so
    ``MilliEQ-PER-L`` fits ``mmol l-1`` of
    ``AmountOfSubstanceConcentration`` counted as equivalents, and
    ``MilliMOL-PER-L`` does not. Without ``counting``, a kind in
    ``EQUIVALENT_KINDS`` (``EquivalentConcentration``) implies it. A
    ``counting`` that is not one of :data:`COUNTINGS`, or conflicts with
    such a kind, raises ``ValueError``. QUDT's ``MO`` is the synodic
    month (29.53 d), so it never fits a ``month`` of year / 12."""
    from .registry import get_registry

    registry = registry if registry is not None else get_registry()
    given = {"quantity_kind": kind, "counting": counting}
    counting = counting_of({k: v for k, v in given.items() if v is not None}, units)
    return not _iri_problems(units, iri, kind, registry, counting=counting)


def annotated_variables(
    data: Any, *, crosswalk_sources: Collection[str] | None = None
) -> pd.DataFrame:
    """The annotated data dictionary of a table or Dataset: the shared
    columns (``variables.VARIABLE_COLUMNS``) then the annotation fields,
    indexed by ``name`` (``variables.variables_of``, which takes
    ``crosswalk_sources``). The annotation columns are left to
    :func:`validate_annotations`."""
    from .variables import variables_of

    return variables_of(data, crosswalk_sources=crosswalk_sources)
