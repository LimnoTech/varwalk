"""Every function that writes ``history`` takes a mark for its lines."""

from __future__ import annotations

import pytest

pytest.importorskip("pint")
pytest.importorskip("pint_xarray")
pytest.importorskip("molmass")

from fixtures import NOW, STAMP, cube, table  # noqa: E402

from varwalk.annotate import annotate  # noqa: E402
from varwalk.chemistry import convert_amount, convert_basis  # noqa: E402
from varwalk.convert import convert_units, rate_to_amount  # noqa: E402
from varwalk.dictionary import HISTORY_MARK, updated  # noqa: E402

NITRATE = {
    "quantity_kind": "AmountOfSubstanceConcentration",
    "counting": "amount",
    "species": "NO3-",
    "basis": "N",
}


def _annotate(data, **kwargs):
    return annotate(data, {"NO3": NITRATE}, now=NOW, **kwargs)


def _units(data, **kwargs):
    return convert_units(
        _annotate(data, **kwargs), {"NO3": "mmol l-1"}, now=NOW, **kwargs
    )


def _rate(data, **kwargs):
    data = annotate(
        data, {"NO3": {"quantity_kind": "MolarFluxDensity"}}, now=NOW, **kwargs
    )
    return rate_to_amount(data, ["NO3"], period="time", freq="MS", now=NOW, **kwargs)


def _basis(data, **kwargs):
    return convert_basis(_annotate(data, **kwargs), {"NO3": "NO3-"}, now=NOW, **kwargs)


def _amount(data, **kwargs):
    return convert_amount(
        _annotate(data, **kwargs), {"NO3": "mg l-1"}, now=NOW, **kwargs
    )


def _make(step):
    if step is _rate:
        return cube({"NO3": ([1.0, 2.0], "mmol m-2 d-1")})
    return table({"NO3": ([1.0, 2.0], "umol l-1")})


STEPS = [_annotate, _units, _rate, _basis, _amount]


def test_the_default_mark_is_varwalk():
    assert HISTORY_MARK == " varwalk: "


@pytest.mark.parametrize("step", STEPS, ids=lambda f: f.__name__.strip("_"))
def test_history_lines_use_the_mark_given(step):
    default = step(_make(step))
    assert default.attrs["history"].splitlines()[-1].startswith(f"{STAMP} varwalk: ")
    marked = step(_make(step), mark=" x: ")
    last = marked.attrs["history"].splitlines()[-1]
    assert last.startswith(f"{STAMP} x: ")
    assert "varwalk:" not in marked.attrs["history"]


def test_updated_writes_the_mark_after_the_timestamp():
    out = updated(
        table({"a": ([1.0], "m")}), {}, history=["a line"], now=NOW, mark=" m: "
    )
    assert out.attrs["history"] == f"{STAMP} m: a line"
