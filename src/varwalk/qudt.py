"""The shipped QUDT subset: units and quantity kinds from QUDT v3.5.2
(CC BY 4.0, QUDT.org), and the local quantity kinds for the dimensions
QUDT has no kind for.

Built by ``scripts/build_qudt_subset.py`` (``pixi run build-qudt``); see
the README beside the files for the release and checksum. Terms are QUDT
local names (``MilliGM-PER-L``, ``MassConcentration``); :func:`iri`
gives the full IRI. docs/units.md section 6.

**Local quantity kinds** live in ``data/local_kinds.csv``, with the QUDT
kinds' columns plus a ``definition``. Today there are two:
``AmountOfSubstancePerArea`` (``A1E0L-2I0M0H0T0D0``, keq/ha or mmol
m-2), for which QUDT 3.5.2 has no kind with that dimension vector, and
``DirectionalVarianceSpectralDensity`` (``A0E0L2I0M0H0T1D0``, a wave
spectrum in m2 s rad-1), whose vector only ``AreaTime`` has and which
therefore lists ``AreaTime`` in ``specialization_of``.
:func:`quantity_kind` searches QUDT first, then the local kinds; a local
kind has no QUDT IRI. A local name that QUDT also defines raises when
the vocabulary loads, so a QUDT release that adds the kind is noticed.
"""

from __future__ import annotations

import difflib
import re
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd

__all__ = [
    "DATA_DIR",
    "LOCAL_KINDS_PATH",
    "QUANTITY_KIND_NAMESPACE",
    "UNIT_NAMESPACE",
    "UnknownTermError",
    "iri",
    "is_local_kind",
    "local_kinds_table",
    "quantity_kind",
    "quantity_kinds_table",
    "unit",
    "units_table",
]

DATA_DIR = Path(__file__).resolve().parent / "data" / "qudt"
#: The local quantity kinds: kinds for dimensions QUDT has none for.
LOCAL_KINDS_PATH = Path(__file__).resolve().parent / "data" / "local_kinds.csv"
UNIT_NAMESPACE = "http://qudt.org/vocab/unit/"
QUANTITY_KIND_NAMESPACE = "http://qudt.org/vocab/quantitykind/"


class UnknownTermError(KeyError, ValueError):
    """A name that is not in the shipped QUDT subset. A ``KeyError`` for
    mapping-style callers and a ``ValueError`` because every refusal is
    one."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


def _read(stem: str) -> pd.DataFrame:
    import pandas as pd

    path = DATA_DIR / f"{stem}.parquet"
    if not path.is_file():
        raise FileNotFoundError(
            f"QUDT subset file missing: {path}. It ships as package data; rebuild it "
            "with `pixi run build-qudt`."
        )
    return pd.read_parquet(path).set_index("name")


@cache
def units_table() -> pd.DataFrame:
    """Every QUDT unit in the subset, indexed by local name."""
    return _read("units")


@cache
def quantity_kinds_table() -> pd.DataFrame:
    """Every QUDT quantity kind in the subset, indexed by local name."""
    return _read("quantity_kinds")


_VECTOR = re.compile(r"^A-?\d+E-?\d+L-?\d+I-?\d+M-?\d+H-?\d+T-?\d+D[01]$")


@cache
def local_kinds_table() -> pd.DataFrame:
    """Every local quantity kind, indexed by name, with the QUDT kinds'
    columns plus ``definition``. Raises ``ValueError`` when a name is
    also a QUDT kind in the subset (QUDT now defines it: use QUDT's), is
    listed twice, or has a malformed dimension vector."""
    import pandas as pd

    if not LOCAL_KINDS_PATH.is_file():
        raise FileNotFoundError(f"local quantity kinds missing: {LOCAL_KINDS_PATH}")
    table = pd.read_csv(
        LOCAL_KINDS_PATH, dtype=str, keep_default_na=False, engine="pyarrow"
    )
    expected = ["name", *quantity_kinds_table().columns, "definition"]
    if list(table.columns) != expected:
        raise ValueError(
            f"{LOCAL_KINDS_PATH.name} has columns {list(table.columns)}; expected "
            f"{expected}"
        )
    duplicated = sorted(set(table["name"][table["name"].duplicated()]))
    if duplicated:
        raise ValueError(f"{LOCAL_KINDS_PATH.name} lists {duplicated} more than once")
    clash = sorted(set(table["name"]) & set(quantity_kinds_table().index))
    if clash:
        raise ValueError(
            f"local quantity kind(s) {clash} in {LOCAL_KINDS_PATH.name} are also QUDT "
            "quantity kinds in the shipped subset: QUDT now defines them, so remove "
            "them from the local vocabulary and use QUDT's"
        )
    malformed = sorted(table["name"][~table["dimension_vector"].str.match(_VECTOR)])
    if malformed:
        raise ValueError(
            f"{LOCAL_KINDS_PATH.name}: malformed dimension vector for {malformed}"
        )
    table["specialization_of"] = [
        [k for k in cell.split(";") if k] for cell in table["specialization_of"]
    ]
    table["deprecated"] = table["deprecated"] == "True"
    for column in ("qkdv_numerator", "qkdv_denominator", "replaced_by"):
        table[column] = table[column].replace("", None)
    return table.set_index("name")


def is_local_kind(name: str) -> bool:
    """True when ``name`` is a local quantity kind (never also a QUDT
    one)."""
    return name in local_kinds_table().index


def _row(table: pd.DataFrame, name: str, what: str) -> pd.Series:
    if name not in table.index:
        close = difflib.get_close_matches(name, list(table.index), n=3)
        hint = f"; did you mean {close}?" if close else ""
        raise UnknownTermError(
            f"{name!r} is not a QUDT {what} in the shipped subset{hint}"
        )
    return table.loc[name]  # type: ignore[return-value]


def quantity_kind(name: str) -> pd.Series:
    """The row for a quantity kind: QUDT's subset first, then the local
    kinds (:func:`is_local_kind`). Raises ``UnknownTermError`` with
    suggestions from both."""
    qudt_kinds = quantity_kinds_table()
    if name in qudt_kinds.index:
        return qudt_kinds.loc[name]  # type: ignore[return-value]
    local = local_kinds_table()
    if name in local.index:
        return local.loc[name]  # type: ignore[return-value]
    close = difflib.get_close_matches(name, [*qudt_kinds.index, *local.index], n=3)
    hint = f"; did you mean {close}?" if close else ""
    raise UnknownTermError(
        f"{name!r} is not a QUDT quantity kind in the shipped subset, nor a local "
        f"one{hint}"
    )


def unit(name: str) -> pd.Series:
    """The subset's row for a QUDT unit. Raises ``UnknownTermError``
    with suggestions."""
    return _row(units_table(), name, "unit")


def iri(name: str, kind: Literal["unit", "quantity_kind"]) -> str:
    """The full QUDT IRI for a local name. Raises ``ValueError`` for a
    local quantity kind, which QUDT does not define."""
    if kind == "quantity_kind" and is_local_kind(name):
        raise ValueError(
            f"{name!r} is a local quantity kind ({LOCAL_KINDS_PATH.name}), not a QUDT "
            "one, so it has no QUDT IRI"
        )
    namespace = {"unit": UNIT_NAMESPACE, "quantity_kind": QUANTITY_KIND_NAMESPACE}[kind]
    return namespace + name
