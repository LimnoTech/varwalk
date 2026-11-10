"""convert_units and rate_to_amount. See docs/units.md sections 3-4."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pint")
pytest.importorskip("pint_xarray")

from fixtures import NOW, STAMP, cf_roundtrip, cube, record, table, values  # noqa: E402

from varwalk.annotate import annotate  # noqa: E402
from varwalk.convert import (  # noqa: E402
    RATE_TO_AMOUNT,
    convert_units,
    rate_to_amount,
)
from varwalk.registry import get_registry  # noqa: E402

FLUX = {"quantity_kind": "MassPerAreaTime"}
SECONDS_PER_JULIAN_YEAR = 365.25 * 86400


def flux(make, values_=(1.0, 2.0, 3.0), units="kg m-2 s-1", **kwargs):
    return annotate(make({"DEP": (list(values_), units)}, **kwargs), {"DEP": FLUX})


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
def test_convert_units_rewrites_units_and_appends_history(make):
    out = convert_units(flux(make), {"DEP": "kg ha-1 yr-1"}, now=NOW)
    assert record(out, "DEP")["units"] == "kg ha-1 julian_year-1"
    assert values(out, "DEP")[0] == pytest.approx(
        1e4 * SECONDS_PER_JULIAN_YEAR, rel=1e-12
    )
    assert out.attrs["history"].endswith(
        f"{STAMP} varwalk: convert_units: DEP 'kg m-2 s-1' -> "
        "'kg ha-1 julian_year-1' (year setting: julian)"
    )


def test_table_and_dataset_paths_agree():
    by_table = convert_units(flux(table), {"DEP": "kg ha-1 common_year-1"})
    by_cube = convert_units(flux(cube), {"DEP": "kg ha-1 common_year-1"})
    assert values(by_table, "DEP") == pytest.approx(values(by_cube, "DEP"), rel=1e-12)
    assert record(by_table, "DEP")["units"] == record(by_cube, "DEP")["units"]


@pytest.mark.parametrize(
    ("setting", "written"),
    [
        ("julian", "kg ha-1 julian_year-1"),
        ("common", "kg common_year-1 ha-1"),
        ("tropical", "kg ha-1 year-1"),
    ],
)
def test_year_setting_is_written_explicitly(setting, written):
    registry = get_registry(setting)
    data = annotate(
        table({"DEP": ([1.0], "kg m-2 s-1")}), {"DEP": FLUX}, registry=registry
    )
    out = convert_units(data, {"DEP": "kg/ha/yr"}, registry=registry)
    assert record(out, "DEP")["units"] == written
    assert f"(year setting: {setting})" in out.attrs["history"]


def test_dimension_mismatch_raises():
    with pytest.raises(
        ValueError,
        match=r"'DEP' is MassPerAreaTime \(A0E0L-2I0M1H0T-1D0\), but 'kg ha-1' has dimensions",
    ):
        convert_units(flux(table), {"DEP": "kg ha-1"})


def test_mass_to_amount_belongs_to_convert_amount():
    data = annotate(
        table({"NO3": ([1.0], "mg l-1")}),
        {"NO3": {"quantity_kind": "MassConcentration"}},
    )
    with pytest.raises(ValueError, match="chemistry.convert_amount"):
        convert_units(data, {"NO3": "umol l-1"})


def test_a_variable_without_quantity_kind_is_refused():
    with pytest.raises(ValueError, match="'DEP' has no quantity_kind"):
        convert_units(table({"DEP": ([1.0], "kg m-2 s-1")}), {"DEP": "kg ha-1 yr-1"})


def test_a_quantity_target_is_refused():
    registry = get_registry()
    with pytest.raises(ValueError, match="not a Quantity"):
        convert_units(flux(table), {"DEP": registry.Quantity(1, "kg ha-1 yr-1")})


def test_missing_values_stay_missing_and_nullable():
    data = flux(table, values_=(1.0, None, 3.0))
    out = convert_units(data, {"DEP": "g m-2 s-1"})
    assert str(out["DEP"].dtype) == "Float64"
    assert out["DEP"].isna().tolist() == [False, True, False]
    assert out["DEP"].iloc[2] == pytest.approx(3000.0)


def test_input_is_not_modified():
    data = flux(table)
    before = (data.copy(), record(data, "DEP")["units"])
    convert_units(data, {"DEP": "kg ha-1 yr-1"})
    assert data["DEP"].tolist() == before[0]["DEP"].tolist()
    assert record(data, "DEP")["units"] == before[1]


def test_units_iri_kept_when_it_still_fits_and_removed_when_not():
    data = annotate(
        table({"DEP": ([1.0], "kg ha-1 julian_year-1")}),
        {"DEP": {**FLUX, "units_iri": "KiloGM-PER-HA-YR"}},
    )
    kept = convert_units(data, {"DEP": "kg/ha/yr"})
    assert record(kept, "DEP")["units_iri"] == "KiloGM-PER-HA-YR"
    dropped = convert_units(data, {"DEP": "kg m-2 s-1"})
    assert "units_iri" not in record(dropped, "DEP")


def test_converted_cube_drops_source_packing_and_encodes_the_new_values():
    data = flux(cube)
    data["DEP"].encoding = {"dtype": "int16", "scale_factor": 0.1, "_FillValue": -9999}
    out = convert_units(data, {"DEP": "kg ha-1 yr-1"})
    assert out["DEP"].encoding == {}
    back = cf_roundtrip(out)
    assert float(back["DEP"][0]) == pytest.approx(
        1e4 * SECONDS_PER_JULIAN_YEAR, rel=1e-12
    )
    assert back["DEP"].attrs["units"] == "kg ha-1 julian_year-1"
    assert back["DEP"].attrs["long_name"] == "DEP as published"


def test_equivalent_concentration_rescales_between_mol_units():
    data = annotate(
        table({"CA": ([1.0, 2.0], "mmol l-1")}),
        {"CA": {"quantity_kind": "EquivalentConcentration"}},
    )
    out = convert_units(data, {"CA": "umol l-1"})
    assert values(out, "CA") == pytest.approx([1000.0, 2000.0])
    assert record(out, "CA")["quantity_kind"] == "EquivalentConcentration"
    assert record(out, "CA")["units"] == "umol l-1"


def test_an_eq_target_is_refused_and_says_to_write_mol():
    data = annotate(
        table({"CA": ([1.0], "mmol l-1")}),
        {"CA": {"quantity_kind": "EquivalentConcentration"}},
    )
    with pytest.raises(ValueError, match="'CA'") as err:
        convert_units(data, {"CA": "ueq l-1"})
    message = str(err.value)
    assert "'ueq l-1'" in message
    assert "write it in mol, 'umol l-1', which keeps counting 'equivalents'" in message
    assert "convert_amount" not in message


@pytest.mark.parametrize(
    "attr", ["valid_min", "valid_max", "actual_range", "valid_range"]
)
def test_dataset_range_attributes_are_converted_with_the_values(attr):
    data = annotate(
        cube({"M": ([1.0, 2.0, 3.0], "kg")}), {"M": {"quantity_kind": "Mass"}}
    )
    given = [0, 5] if attr.endswith("range") else 5
    data["M"].attrs[attr] = given
    out = convert_units(data, {"M": "g"})
    expected = [0, 5000] if attr.endswith("range") else 5000
    assert list(np.atleast_1d(out["M"].attrs[attr])) == pytest.approx(
        list(np.atleast_1d(expected))
    )
    assert values(out, "M") == pytest.approx([1000.0, 2000.0, 3000.0])
    assert (
        np.atleast_1d(data["M"].attrs[attr]).tolist() == np.atleast_1d(given).tolist()
    )


def test_packed_valid_range_is_unpacked_before_conversion():
    data = annotate(
        cube({"M": ([1.0, 2.0, 3.0], "kg")}), {"M": {"quantity_kind": "Mass"}}
    )
    data["M"].encoding = {"dtype": "int16", "scale_factor": 0.1, "_FillValue": -9999}
    data["M"].attrs["valid_range"] = np.array([0, 50], dtype="int16")
    reopened = cf_roundtrip(data)
    assert "scale_factor" in reopened["M"].encoding
    out = convert_units(reopened, {"M": "g"})
    assert list(out["M"].attrs["valid_range"]) == pytest.approx([0, 5000])


def test_range_attributes_keep_their_container():
    data = annotate(cube({"M": ([1.0], "kg")}), {"M": {"quantity_kind": "Mass"}})
    data["M"].attrs.update(
        valid_range=[0, 5], valid_min=1.0, actual_range=np.array([1.0, 2.0])
    )
    attrs = convert_units(data, {"M": "g"})["M"].attrs
    assert attrs["valid_range"] == [0.0, 5000.0] and isinstance(
        attrs["valid_range"], list
    )
    assert attrs["valid_min"] == 1000.0 and isinstance(attrs["valid_min"], float)
    assert isinstance(attrs["actual_range"], np.ndarray)


def test_dataset_input_is_not_modified():
    data = flux(cube)
    data["DEP"].encoding = {"dtype": "float32"}
    before = values(data, "DEP")
    convert_units(data, {"DEP": "kg ha-1 yr-1"})
    assert values(data, "DEP") == before
    assert record(data, "DEP")["units"] == "kg m-2 s-1"
    assert data["DEP"].encoding == {"dtype": "float32"}


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
def test_offset_units_convert(make):
    data = annotate(
        make({"T": ([0.0, 20.0], "degC")}), {"T": {"quantity_kind": "Temperature"}}
    )
    if make is cube:
        data["T"].attrs["valid_range"] = [-5, 40]
    out = convert_units(data, {"T": "K"})
    assert values(out, "T") == pytest.approx([273.15, 293.15])
    assert record(out, "T")["units"] == "K"
    if make is cube:
        assert out["T"].attrs["valid_range"] == pytest.approx([268.15, 313.15])


def test_unparseable_or_mismatched_source_units_name_the_variable():
    bad = flux(table)
    bad.attrs["variables"][0]["units"] = "kg ha-1"
    with pytest.raises(ValueError, match="'DEP' is MassPerAreaTime.*kg ha-1"):
        convert_units(bad, {"DEP": "kg ha-1 yr-1"})
    junk = flux(table)
    junk.attrs["variables"][0]["units"] = "furlongs per fortnightly"
    with pytest.raises(ValueError, match="'DEP'"):
        convert_units(junk, {"DEP": "kg ha-1 yr-1"})


# --- rate_to_amount


def test_rate_to_amount_kind_map_pairs_have_matching_dimensions():
    import re

    from varwalk import qudt

    def exponents(vector):
        return {k: int(v) for k, v in re.findall(r"([AELIMHTD])(-?\d+)", vector)}

    for rate, amount in RATE_TO_AMOUNT.items():
        r = exponents(qudt.quantity_kind(rate)["dimension_vector"])
        a = exponents(qudt.quantity_kind(amount)["dimension_vector"])
        r["T"] += 1
        r["D"] = a["D"]
        assert r == a, (rate, amount)


def test_february_2024_has_29_days():
    data = flux(cube, values_=(1.0, 1.0, 1.0))
    out = rate_to_amount(data, ["DEP"], now=NOW)
    assert values(out, "DEP") == [31 * 86400.0, 29 * 86400.0, 31 * 86400.0]
    assert record(out, "DEP")["units"] == "kg m-2"
    assert record(out, "DEP")["quantity_kind"] == "MassPerArea"
    assert out.attrs["history"].endswith(
        "rate_to_amount: DEP 'kg m-2 s-1' (MassPerAreaTime) -> 'kg m-2' (MassPerArea) over "
        "each period's own length, time + 1 MS (year setting: julian)"
    )


def test_noleap_february_has_28_days():
    pytest.importorskip("cftime")
    data = flux(cube, values_=(1.0, 1.0, 1.0), calendar="noleap")
    out = rate_to_amount(data, ["DEP"])
    assert values(out, "DEP")[1] == 28 * 86400.0


def test_periods_that_are_not_calendar_months_use_their_own_start_and_end():
    # a monthly mean built from whole weekly samples: 2018-10-02 to 2018-10-30, 28 days
    data = annotate(table({"wet": ([1.0, 2.0], "kg ha-1 d-1")}), {"wet": FLUX})
    data["startDate"] = pd.to_datetime(["2018-10-02", "2018-10-30"])
    data["endDate"] = pd.to_datetime(["2018-10-30", "2018-11-27"])
    out = rate_to_amount(data, ["wet"], period=("startDate", "endDate"))
    assert values(out, "wet") == [28.0, 56.0]
    assert record(out, "wet")["units"] == "kg ha-1"


def test_an_annual_rate_over_a_leap_year_uses_366_days():
    data = annotate(table({"DEP": ([1.0], "kg ha-1 julian_year-1")}), {"DEP": FLUX})
    data["time"] = pd.to_datetime(["2024-01-01"])
    out = rate_to_amount(data, ["DEP"], period="time", freq="YS")
    assert values(out, "DEP")[0] == pytest.approx(366 / 365.25, rel=1e-12)


def test_a_long_table_needs_freq_and_then_uses_each_row():
    data = annotate(table({"DEP": ([1.0, 1.0, 1.0, 1.0], "kg m-2 s-1")}), {"DEP": FLUX})
    data["site"] = ["A", "B", "A", "B"]
    data["time"] = pd.to_datetime(
        ["2024-02-01", "2024-02-01", "2024-03-01", "2024-03-01"]
    )
    with pytest.raises(ValueError, match="DEP.*repeats per site: give freq="):
        rate_to_amount(data, ["DEP"])
    out = rate_to_amount(data, ["DEP"], freq="MS")
    assert values(out, "DEP") == [
        29 * 86400.0,
        29 * 86400.0,
        31 * 86400.0,
        31 * 86400.0,
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"freq": "ME"}, "'DEP'.*does not label each period by its start"),
        ({"period": "when"}, "'DEP'.*'when' is not a coordinate"),
    ],
)
def test_undeterminable_periods_raise(kwargs, message):
    with pytest.raises(ValueError, match=message):
        rate_to_amount(flux(cube), ["DEP"], **kwargs)


def test_two_time_steps_are_too_few_to_infer_a_period():
    with pytest.raises(ValueError, match="DEP.*cannot determine the period length"):
        rate_to_amount(flux(cube, values_=(1.0, 1.0)), ["DEP"])


def test_an_end_before_its_start_raises():
    data = annotate(table({"wet": ([1.0], "kg ha-1 d-1")}), {"wet": FLUX})
    data["startDate"] = pd.to_datetime(["2018-10-30"])
    data["endDate"] = pd.to_datetime(["2018-10-02"])
    with pytest.raises(ValueError, match="wet.*a length is missing or <= 0"):
        rate_to_amount(data, ["wet"], period=("startDate", "endDate"))


def test_a_molar_flux_accumulates_to_a_local_amount_per_area():
    data = annotate(
        table({"N": ([1.0, 2.0], "mmol m-2 d-1")}),
        {"N": {"quantity_kind": "MolarFluxDensity"}},
    )
    data["time"] = pd.to_datetime(["2024-02-01", "2024-03-01"])
    out = rate_to_amount(data, ["N"], period="time", freq="MS")
    assert values(out, "N") == pytest.approx([29.0, 62.0])
    assert record(out, "N")["units"] == "mmol m-2"
    assert record(out, "N")["quantity_kind"] == "AmountOfSubstancePerArea"


def test_a_rate_with_no_amount_kind_is_refused():
    data = annotate(
        table({"v": ([1.0], "m s-1")}), {"v": {"quantity_kind": "Velocity"}}
    )
    with pytest.raises(ValueError, match="Velocity, which has no amount kind"):
        rate_to_amount(data, ["v"], period="time", freq="D")


# every start must sit on the freq's boundary


def test_a_start_off_the_freq_boundary_raises_naming_variable_and_start():
    data = annotate(table({"DEP": ([1.0, 1.0], "kg m-2 s-1")}), {"DEP": FLUX})
    data["time"] = pd.to_datetime(["2024-02-01", "2024-01-15"])
    with pytest.raises(ValueError, match=r"'DEP'.*2024-01-15.*period=\(start, end\)"):
        rate_to_amount(data, ["DEP"], freq="MS")


def test_on_boundary_table_starts_work():
    data = annotate(table({"DEP": ([1.0, 1.0], "kg m-2 s-1")}), {"DEP": FLUX})
    data["time"] = pd.to_datetime(["2024-01-01", "2024-02-01"])
    out = rate_to_amount(data, ["DEP"], freq="MS")
    assert values(out, "DEP") == [31 * 86400.0, 29 * 86400.0]


def test_an_off_boundary_dataset_start_raises():
    data = flux(cube, values_=(1.0, 1.0, 1.0), start="2024-01-15", freq="30D")
    with pytest.raises(ValueError, match="2024-01-15"):
        rate_to_amount(data, ["DEP"], freq="MS")


def test_a_noleap_dataset_on_boundary_still_works():
    pytest.importorskip("cftime")
    data = flux(cube, values_=(1.0, 1.0, 1.0), calendar="noleap")
    out = rate_to_amount(data, ["DEP"], freq="MS")
    assert values(out, "DEP") == [31 * 86400.0, 28 * 86400.0, 31 * 86400.0]


def test_freq_with_a_start_end_period_is_refused():
    data = annotate(table({"wet": ([1.0], "kg ha-1 d-1")}), {"wet": FLUX})
    data["startDate"] = pd.to_datetime(["2018-10-02"])
    data["endDate"] = pd.to_datetime(["2018-10-30"])
    with pytest.raises(
        ValueError, match="'wet'.*give freq= or period=\\(start, end\\), not both"
    ):
        rate_to_amount(data, ["wet"], period=("startDate", "endDate"), freq="D")


def test_an_inferred_freq_that_is_not_start_anchored_says_so():
    data = flux(cube, values_=(1.0, 1.0, 1.0), start="2024-01-07", freq="W-SUN")
    with pytest.raises(
        ValueError, match="'DEP'.*inferred freq 'W-SUN'.*freq=.*period="
    ):
        rate_to_amount(data, ["DEP"])


def test_duplicate_variable_names_are_refused():
    with pytest.raises(ValueError, match=r"duplicate variable names \['DEP'\]"):
        rate_to_amount(flux(cube), ["DEP", "DEP"])


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
def test_units_iri_is_removed_and_the_input_is_unchanged(make):
    data = annotate(
        make({"DEP": ([1.0, 2.0, 3.0], "kg m-2 s-1")}),
        {"DEP": {**FLUX, "units_iri": "KiloGM-PER-M2-SEC"}},
    )
    if make is table:
        data["time"] = pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"])
    before_values, before_record = values(data, "DEP"), record(data, "DEP")
    before_attrs = repr(data.attrs)
    out = rate_to_amount(data, ["DEP"], freq="MS")
    assert "units_iri" not in record(out, "DEP")
    assert values(data, "DEP") == before_values
    assert record(data, "DEP") == before_record
    assert record(data, "DEP")["units_iri"] == "KiloGM-PER-M2-SEC"
    assert repr(data.attrs) == before_attrs


def test_rate_to_amount_removes_range_attributes_and_says_so():
    data = flux(cube)
    data["DEP"].attrs.update(valid_min=0.0, valid_max=10.0, actual_range=[1.0, 3.0])
    out = rate_to_amount(data, ["DEP"], now=NOW)
    for attr in ("valid_min", "valid_max", "actual_range", "valid_range"):
        assert attr not in out["DEP"].attrs
    assert (
        "removed valid_min, valid_max, actual_range (each period has its own factor)"
        in (out.attrs["history"])
    )
    assert data["DEP"].attrs["valid_max"] == 10.0


# --- equivalents: every refusal's advice leads somewhere that works

EQ_ADVICE = "use chemistry.convert_amount with 'meq l-1'"


@pytest.mark.parametrize(
    ("given", "kind", "counting"),
    [
        ((40.078, "mg l-1"), "MassConcentration", "mass"),
        ((1.0, "mmol l-1"), "AmountOfSubstanceConcentration", "amount"),
    ],
    ids=["mass", "amount"],
)
def test_an_eq_target_on_another_kind_goes_to_convert_amount_and_it_works(
    given, kind, counting
):
    from varwalk.chemistry import convert_amount

    value, units = given
    data = annotate(
        table({"Ca": ([value], units)}),
        {
            "Ca": {
                "quantity_kind": kind,
                "counting": counting,
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    with pytest.raises(ValueError, match="'Ca'") as err:
        convert_units(data, {"Ca": "meq l-1"})
    assert EQ_ADVICE in str(err.value)
    assert "species' charge" in str(err.value)
    out = convert_amount(data, {"Ca": "meq l-1"})
    assert record(out, "Ca")["quantity_kind"] == "AmountOfSubstanceConcentration"
    assert record(out, "Ca")["counting"] == "equivalents"
    assert record(out, "Ca")["units"] == "mmol l-1"
    assert values(out, "Ca")[0] == pytest.approx(2.00, rel=1e-4)


def test_an_eq_target_on_a_flux_goes_to_convert_amount_and_it_works():
    from varwalk.chemistry import convert_amount

    data = annotate(
        table({"Ca": ([1.0], "kg m-2 s-1")}),
        {
            "Ca": {
                "quantity_kind": "MassFluxDensity",
                "counting": "mass",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    with pytest.raises(ValueError, match="'Ca' is counted as mass") as err:
        convert_units(data, {"Ca": "meq m-2 s-1"})
    assert "use chemistry.convert_amount with 'meq m-2 s-1'" in str(err.value)
    out = convert_amount(data, {"Ca": "meq m-2 s-1"})
    assert record(out, "Ca")["quantity_kind"] == "MolarFluxDensity"
    assert record(out, "Ca")["counting"] == "equivalents"
    assert values(out, "Ca")[0] == pytest.approx(
        2e6 / 40.078, rel=1e-4
    )  # 1 kg is 49.9 eq


def test_an_amount_variable_is_not_silently_rescaled_to_ueq():
    data = annotate(
        table({"Ca": ([1.0], "mmol l-1")}),
        {
            "Ca": {
                "quantity_kind": "AmountOfSubstanceConcentration",
                "counting": "amount",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    with pytest.raises(ValueError, match="'Ca'.*convert_amount"):
        convert_units(data, {"Ca": "ueq l-1"})


# --- refusals name the variable; arguments are checked by type first


@pytest.mark.parametrize(
    ("field", "bad", "call"),
    [
        (
            "quantity_kind",
            "NotAKind",
            lambda d: convert_units(d, {"DEP": "kg ha-1 yr-1"}),
        ),
        (
            "units",
            "furlongs per fortnightly",
            lambda d: rate_to_amount(d, ["DEP"], freq="MS"),
        ),
    ],
    ids=["convert_units-kind", "rate_to_amount-units"],
)
def test_a_lookup_or_parse_failure_names_the_variable(field, bad, call):
    data = flux(table)
    data.attrs["variables"][0][field] = bad
    with pytest.raises(ValueError, match=f"^'DEP': {field} '{bad}'"):
        call(data)


def monthly_table():
    data = flux(table)
    data["start"] = pd.date_range("2024-01-01", periods=3, freq="MS")
    data["end"] = data["start"] + pd.offsets.MonthBegin(1)
    return data


@pytest.mark.parametrize(
    ("period", "freq", "message"),
    [
        (["start", "end"], "MS", "not both"),
        (["start", "end", "x"], None, "period is a name or a"),
        (("start",), None, "period is a name or a"),
        (3, None, "period is a name or a"),
    ],
    ids=["list-with-freq", "three-names", "one-tuple", "not-a-name"],
)
def test_a_period_that_is_not_a_name_or_a_pair_is_refused_naming_the_variable(
    period, freq, message
):
    with pytest.raises(ValueError, match=f"^'DEP': .*{message}"):
        rate_to_amount(monthly_table(), ["DEP"], period=period, freq=freq)


def test_a_two_item_list_period_works_like_a_tuple():
    data = monthly_table()
    by_list = rate_to_amount(data, ["DEP"], period=["start", "end"])
    by_tuple = rate_to_amount(data, ["DEP"], period=("start", "end"))
    assert values(by_list, "DEP") == values(by_tuple, "DEP")
    assert values(by_list, "DEP")[1] == pytest.approx(2.0 * 29 * 86400)


def test_period_may_be_an_index_level():
    data = flux(table)
    data.index = pd.MultiIndex.from_arrays(
        [["a", "a", "b"], pd.to_datetime(["2024-01-01", "2024-02-01", "2024-02-01"])],
        names=["site", "time"],
    )
    out = rate_to_amount(data, ["DEP"], period="time", freq="MS")
    assert values(out, "DEP") == pytest.approx(
        [31 * 86400, 2 * 29 * 86400, 3 * 29 * 86400]
    )


# --- counting is kept, and an eq target is judged by counting, not by the kind


def test_convert_units_keeps_counting_and_judges_an_eq_target_by_it():
    data = annotate(
        table({"ANC": ([120.0], "umol l-1")}),
        {
            "ANC": {
                "quantity_kind": "AmountOfSubstanceConcentration",
                "counting": "equivalents",
            }
        },
    )
    out = convert_units(data, {"ANC": "mmol l-1"})
    assert values(out, "ANC") == pytest.approx([0.12])
    assert record(out, "ANC")["counting"] == "equivalents"
    with pytest.raises(ValueError, match="'ANC': target 'meq l-1': UDUNITS has no eq"):
        convert_units(data, {"ANC": "meq l-1"})


def test_an_equivalents_units_iri_is_dropped_when_the_scale_changes():
    data = annotate(
        table({"ANC": ([120.0], "mmol l-1")}),
        {
            "ANC": {
                "quantity_kind": "AmountOfSubstanceConcentration",
                "counting": "equivalents",
                "units_iri": "MilliEQ-PER-L",
            }
        },
    )
    kept = convert_units(
        data, {"ANC": "mol m-3"}
    )  # the same scale: MilliEQ-PER-L still fits
    assert record(kept, "ANC")["units_iri"] == "MilliEQ-PER-L"
    dropped = convert_units(data, {"ANC": "umol l-1"})
    assert "units_iri" not in record(dropped, "ANC")


def test_convert_units_rescales_a_flux_counted_as_equivalents():
    data = annotate(
        table({"Ca": ([1.0], "mmol m-2 s-1")}),
        {
            "Ca": {
                "quantity_kind": "MolarFluxDensity",
                "counting": "equivalents",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    out = convert_units(
        data, {"Ca": "umol m-2 d-1"}
    )  # meq m-2 s-1 -> ueq m-2 d-1, in mol
    assert values(out, "Ca")[0] == pytest.approx(1000 * 86400, rel=1e-12)
    assert record(out, "Ca")["units"] == "umol d-1 m-2"
    assert record(out, "Ca")["counting"] == "equivalents"
    assert record(out, "Ca")["quantity_kind"] == "MolarFluxDensity"
    with pytest.raises(
        ValueError, match="'Ca': target 'ueq m-2 d-1': UDUNITS has no eq"
    ) as err:
        convert_units(data, {"Ca": "ueq m-2 d-1"})
    assert "'umol d-1 m-2'" in str(err.value)  # its own target, written in mol
    assert "'mmol l-1'" not in str(err.value)


def test_rate_to_amount_keeps_counting():
    data = annotate(
        table({"Ca": ([1.0], "mmol m-2 d-1")}),
        {
            "Ca": {
                "quantity_kind": "MolarFluxDensity",
                "counting": "equivalents",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    data["time"] = pd.to_datetime(["2024-02-01"])
    out = rate_to_amount(data, ["Ca"], period="time", freq="MS")
    assert values(out, "Ca") == pytest.approx([29.0])
    assert record(out, "Ca")["quantity_kind"] == "AmountOfSubstancePerArea"
    assert record(out, "Ca")["counting"] == "equivalents"


# --- counting on input is checked, never trusted


def invalid_calcium(counting, kind="EquivalentConcentration"):
    data = cube({"Ca": ([1.0], "mmol l-1")})
    data["Ca"].attrs.update(
        quantity_kind=kind, counting=counting, species="Ca+2", basis="Ca"
    )
    return data


@pytest.mark.parametrize(
    ("counting", "kind", "message"),
    [
        (
            "amount",
            "EquivalentConcentration",
            "quantity_kind EquivalentConcentration counts equivalents, so",
        ),
        ("moles", "AmountOfSubstanceConcentration", "counting 'moles' is not one of"),
    ],
    ids=["conflict", "unknown"],
)
def test_an_invalid_counting_on_input_is_refused_by_every_converter(
    counting, kind, message
):
    from varwalk.chemistry import convert_amount, convert_basis

    data = invalid_calcium(counting, kind)
    calls = [
        lambda: convert_amount(data, {"Ca": "mg l-1"}),
        lambda: convert_units(data, {"Ca": "umol l-1"}),
        lambda: convert_basis(data, {"Ca": "Ca+2"}),
    ]
    for call in calls:
        with pytest.raises(ValueError, match=f"^'Ca': {message}"):
            call()


def test_an_invalid_counting_on_a_rate_is_refused():
    data = annotate(
        table({"Ca": ([1.0], "mmol m-2 d-1")}),
        {"Ca": {"quantity_kind": "MolarFluxDensity", "counting": "amount"}},
    )
    data.attrs["variables"][0]["counting"] = "moles"
    data["time"] = pd.to_datetime(["2024-02-01"])
    with pytest.raises(ValueError, match="^'Ca': counting 'moles' is not one of"):
        rate_to_amount(data, ["Ca"], period="time", freq="MS")


# --- a dimensionless kind keeps its numerator: mass fraction <-> mole fraction is refused


@pytest.mark.parametrize(
    ("units", "kind", "counting", "target"),
    [
        ("mg kg-1", "MassFraction", "mass", "mmol mol-1"),
        ("umol mol-1", "MoleFraction", "amount", "mg kg-1"),
        ("mg kg-1", "MassFraction", None, "mmol mol-1"),
        ("1", "MassFraction", None, "mmol mol-1"),
    ],
    ids=["mass-fraction", "mole-fraction", "no-counting", "bare-1"],
)
def test_a_dimensionless_target_with_another_numerator_is_refused(
    units, kind, counting, target
):
    fields = {"quantity_kind": kind}
    if counting is not None:
        fields["counting"] = counting
    data = annotate(table({"X": ([1.0], units)}), {"X": fields})
    with pytest.raises(
        ValueError, match=f"^'X' is {kind} .*molar masses of both"
    ) as err:
        convert_units(data, {"X": target})
    assert "matrix" in str(err.value)
    assert "convert_amount" not in str(err.value)  # it would refuse too: no pointer


@pytest.mark.parametrize(
    ("units", "kind", "target", "expected"),
    [
        ("mg kg-1", "MassFraction", "ug g-1", 1.0),
        ("mg kg-1", "MassFraction", "percent", 1e-4),
        ("umol mol-1", "MoleFraction", "mmol mol-1", 1e-3),
        ("1", "MoleFraction", "umol mol-1", 1e6),
    ],
)
def test_a_dimensionless_target_with_the_same_numerator_converts(
    units, kind, target, expected
):
    data = annotate(table({"X": ([1.0], units)}), {"X": {"quantity_kind": kind}})
    assert values(convert_units(data, {"X": target}), "X")[0] == pytest.approx(expected)


def test_a_source_written_in_eq_is_told_its_own_units_in_mol():
    data = annotate(
        table({"DEP": ([1.0], "mmol m-2 d-1")}),
        {"DEP": {"quantity_kind": "MolarFluxDensity"}},
    )
    data.attrs["variables"][0]["units"] = (
        "meq m-2 d-1"  # written by hand, past annotate
    )
    with pytest.raises(
        ValueError, match="^'DEP': units 'meq m-2 d-1': UDUNITS has no eq"
    ) as err:
        convert_units(data, {"DEP": "umol m-2 d-1"})
    assert "'mmol d-1 m-2'" in str(err.value)
    assert "'mmol l-1'" not in str(err.value)
