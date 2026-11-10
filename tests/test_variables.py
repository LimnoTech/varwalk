"""The variable model: the data dictionary, check_udunits and describe_variables."""

from __future__ import annotations

import json

import pandas as pd
import pytest
import xarray as xr

from varwalk.variables import (
    ANNOTATION_COLUMNS,
    VARIABLE_COLUMNS,
    check_udunits,
    describe_variables,
    validate_variables_df,
    variables_frame,
    variables_of,
    variables_to_records,
)


def test_variables_frame_has_the_schema_columns_and_index():
    variables_df = variables_frame([{"name": "00060", "source_units": "ft^3/s"}])
    assert variables_df.index.name == "name"
    assert list(variables_df.columns) == [*VARIABLE_COLUMNS, *ANNOTATION_COLUMNS]
    assert variables_df.loc["00060", "source_units"] == "ft^3/s"
    assert pd.isna(variables_df.loc["00060", "standard_name"])
    assert variables_df.loc["00060", "aliases"] == {}


def test_an_empty_data_dictionary_keeps_its_schema():
    variables_df = variables_frame([])
    assert len(variables_df) == 0
    assert variables_df.index.name == "name"
    assert list(variables_df.columns) == [*VARIABLE_COLUMNS, *ANNOTATION_COLUMNS]


def test_variables_frame_rejects_an_unknown_column():
    with pytest.raises(
        ValueError, match=r"unknown data-dictionary column\(s\) \['colour'\]"
    ):
        variables_frame([{"name": "a", "colour": "red"}])


def test_variables_frame_rejects_a_row_without_a_name():
    with pytest.raises(ValueError, match="needs a 'name'"):
        variables_frame([{"source_units": "m"}])


def test_bare_list_aliases_are_rejected():
    with pytest.raises(ValueError, match="must map vocabulary to term"):
        variables_frame([{"name": "a", "aliases": ["temp"]}])


def test_duplicate_variable_names_are_rejected():
    with pytest.raises(ValueError, match=r"duplicated: \['a'\]"):
        variables_frame([{"name": "a"}, {"name": "a"}])


def test_validate_rejects_a_frame_indexed_by_something_else():
    with pytest.raises(ValueError, match="indexed by 'name'"):
        validate_variables_df(pd.DataFrame(columns=list(VARIABLE_COLUMNS)))


def test_records_round_trip_through_json():
    variables_df = variables_frame(
        [
            {
                "name": "00010",
                "source_long_name": "Temperature, water",
                "source_units": "degC",
                "units": "degC",
                "aliases": {"usgs_pcode": "00010", "wqx": "Temperature, water"},
                "crosswalk_source": "source",
            },
            {"name": "00060"},
        ]
    )
    records = variables_to_records(variables_df)
    assert records[1] == {
        "name": "00060",
        **dict.fromkeys(VARIABLE_COLUMNS),
        "aliases": {},
    }
    assert not set(ANNOTATION_COLUMNS) & set(records[1])
    rebuilt = variables_frame(json.loads(json.dumps(records)))
    pd.testing.assert_frame_equal(rebuilt, variables_df)


def test_a_data_dictionary_has_the_annotation_columns_after_the_shared_ones():
    df = variables_frame([{"name": "00060"}])
    assert list(df.columns) == [*VARIABLE_COLUMNS, *ANNOTATION_COLUMNS]
    assert (
        df["quantity_kind"].isna().all() and str(df["quantity_kind"].dtype) == "string"
    )


def test_annotation_fields_round_trip_through_records():
    df = variables_frame(
        [
            {
                "name": "n_dw",
                "source_units": "kg-N/ha",
                "units": "kg ha-1",
                "quantity_kind": "MassPerArea",
                "counting": "mass",
            }
        ]
    )
    records = variables_to_records(df)
    assert records[0]["quantity_kind"] == "MassPerArea" and "species" not in records[0]
    assert variables_frame(records).equals(df)


def test_an_unknown_column_is_still_refused():
    with pytest.raises(ValueError, match="unknown data-dictionary column"):
        variables_frame([{"name": "x", "colour": "red"}])


def test_variables_of_a_table_without_a_dictionary_is_empty_with_every_column():
    out = variables_of(pd.DataFrame({"x": [1.0]}))
    assert len(out) == 0 and out.index.name == "name"
    assert list(out.columns) == [*VARIABLE_COLUMNS, *ANNOTATION_COLUMNS]


def test_variables_of_a_dataset_reads_its_variable_attributes():
    ds = xr.Dataset(
        {"n": ("t", [1.0], {"units": "kg ha-1", "quantity_kind": "MassPerArea"})}
    )
    out = variables_of(ds)
    assert out.loc["n", "quantity_kind"] == "MassPerArea"
    assert list(out.columns) == [*VARIABLE_COLUMNS, *ANNOTATION_COLUMNS]


@pytest.mark.parametrize(
    ("units", "expected"),
    [
        ("degC", "degC"),
        ("ft^3/s", "ft^3/s"),
        ("kg ha-1 julian_year-1", "kg ha-1 julian_year-1"),
        ("μmol l-1", "μmol l-1"),
        ("cubic feet per second", None),
        ("psu", None),  # cf-units rejects it; cfunits accepted it
        # a basis written into the unit: UDUNITS-2 parses each as other units: newton, kelvin,
        # centiare, nano-hours, attosecond-newton
        ("kg-N/ha", None),
        ("kg-K/ha", None),
        ("kg-ca/ha", None),
        ("kg-nh4/ha", None),
        ("mg/l as N", None),
        ("mg/kg as N", None),
        # a hyphen before a digit is an exponent
        ("m-2", "m-2"),
        ("kg m-2 s-1", "kg m-2 s-1"),
        ("mol-1", "mol-1"),
        ("1e-3", "1e-3"),
        # a known limit: a basis set off by a space still reads as a newton; only an
        # annotation's quantity_kind exposes it
        ("mg N/L", "mg N/L"),
        ("unknown", None),
        ("", None),
        (None, None),
    ],
)
def test_check_udunits_returns_valid_units_unchanged(units, expected):
    pytest.importorskip("cf_units")
    assert check_udunits(units) == expected


def test_describe_variables_reads_the_sources_own_attrs():
    ds = xr.Dataset(
        {"T2": ("time", [280.0]), "flag": ("time", [1])}, coords={"time": [0]}
    )
    ds["T2"].attrs = {
        "long_name": "Temperature at 2 m",
        "description": "2-meter air temperature",
        "units": "K",
        "standard_name": "air_temperature",
    }
    expected = variables_frame(
        [
            {
                "name": "T2",
                "source_long_name": "Temperature at 2 m",
                "source_description": "2-meter air temperature",
                "source_units": "K",
                "standard_name": "air_temperature",
                "units": "K",
                "crosswalk_source": "source",
            },
            {"name": "flag"},
        ]
    )
    pd.testing.assert_frame_equal(describe_variables(ds), expected)


def test_describe_variables_of_an_empty_dataset_keeps_the_schema():
    described = describe_variables(xr.Dataset())
    assert len(described) == 0
    assert described.index.name == "name"


def test_describe_variables_rejects_non_json_aliases_by_name():
    ds = xr.Dataset({"T2": ("time", [280.0])})
    ds["T2"].attrs = {"aliases": "foo bar"}
    with pytest.raises(ValueError, match="'T2'.*'aliases'.*'foo bar'"):
        describe_variables(ds)


def test_describe_variables_does_not_credit_aliases_alone():
    ds = xr.Dataset({"flow": ("time", [1.0])}, coords={"time": [0]})
    ds["flow"].attrs = {"aliases": '{"usgs_pcode": "00060"}'}
    described = describe_variables(ds)
    assert described.loc["flow", "aliases"] == {"usgs_pcode": "00060"}
    assert pd.isna(described.loc["flow", "crosswalk_source"])


def test_describe_variables_reads_annotation_attributes_and_source_units():
    ds = xr.Dataset(
        {
            "n": (
                "t",
                [1.0],
                {
                    "units": "kg ha-1",
                    "source_units": "kg-N/ha",
                    "quantity_kind": "MassPerArea",
                },
            )
        }
    )
    row = describe_variables(ds).loc["n"]
    assert (row["source_units"], row["units"], row["quantity_kind"]) == (
        "kg-N/ha",
        "kg ha-1",
        "MassPerArea",
    )


def test_describe_variables_keeps_a_non_udunits_unit_unknown_even_with_source_units():
    ds = xr.Dataset(
        {"n": ("t", [1.0], {"units": "kg-N/ha", "source_units": "kg-N/ha"})}
    )
    row = describe_variables(ds).loc["n"]
    assert row["source_units"] == "kg-N/ha" and pd.isna(row["units"])


def test_variables_of_a_table_rebuilds_its_records():
    dictionary = variables_frame([{"name": "x", "quantity_kind": "MassPerArea"}])
    df = pd.DataFrame({"x": [1.0]})
    df.attrs["variables"] = variables_to_records(dictionary)
    assert variables_of(df).equals(dictionary)
    assert variables_of(df).loc["x", "quantity_kind"] == "MassPerArea"


def test_describe_variables_reads_back_what_a_dictionary_describes():
    ds = xr.Dataset({"T2": ("time", [280.0])}, coords={"time": [0]})
    ds["T2"].attrs = {
        "units": "K",
        "standard_name": "air_temperature",
        "aliases": json.dumps({"hydromt": "temp", "wqx": "Temperature, air"}),
        "crosswalk_source": "curator",
        "crosswalk_reference": "https://example.org/crosswalk",
    }
    expected = variables_frame(
        [
            {
                "name": "T2",
                "source_units": "K",
                "standard_name": "air_temperature",
                "units": "K",
                "aliases": {"hydromt": "temp", "wqx": "Temperature, air"},
                "crosswalk_source": "curator",
                "crosswalk_reference": "https://example.org/crosswalk",
            }
        ]
    )
    pd.testing.assert_frame_equal(describe_variables(ds), expected)


# --- crosswalk_sources: the values a caller allows for crosswalk_source


def test_crosswalk_sources_none_accepts_any_value():
    for who in ("someone", "source", "an organization's curators"):
        frame = variables_frame([{"name": "a", "crosswalk_source": who}])
        assert frame.loc["a", "crosswalk_source"] == who
        assert variables_to_records(frame)[0]["crosswalk_source"] == who
    ds = xr.Dataset({"T": ("t", [1.0], {"standard_name": "air_temperature"})})
    ds["T"].attrs["crosswalk_source"] = "anyone"
    assert describe_variables(ds).loc["T", "crosswalk_source"] == "anyone"


def test_crosswalk_sources_none_refuses_a_blank_value():
    with pytest.raises(
        ValueError, match="crosswalk_source for 'a' must be a non-empty string"
    ):
        variables_frame([{"name": "a", "crosswalk_source": " "}])


def test_crosswalk_sources_refuses_a_value_not_listed():
    allowed = {"source", "curator"}
    ok = variables_frame(
        [{"name": "a", "crosswalk_source": "curator"}], crosswalk_sources=allowed
    )
    assert ok.loc["a", "crosswalk_source"] == "curator"
    with pytest.raises(
        ValueError, match=r"crosswalk_source for 'a' must be one of \['curator'"
    ):
        variables_frame(
            [{"name": "a", "crosswalk_source": "someone"}], crosswalk_sources=allowed
        )
    with pytest.raises(ValueError, match="crosswalk_source for 'a'"):
        validate_variables_df(
            variables_frame([{"name": "a", "crosswalk_source": "someone"}]),
            crosswalk_sources=allowed,
        )
    with pytest.raises(ValueError, match="crosswalk_source for 'a'"):
        variables_to_records(
            variables_frame([{"name": "a", "crosswalk_source": "someone"}]),
            crosswalk_sources=allowed,
        )
    df = pd.DataFrame({"a": [1.0]})
    df.attrs["variables"] = [{"name": "a", "crosswalk_source": "someone"}]
    with pytest.raises(ValueError, match="crosswalk_source for 'a'"):
        variables_of(df, crosswalk_sources=allowed)
    ds = xr.Dataset({"T": ("t", [1.0], {"crosswalk_source": "someone"})})
    with pytest.raises(ValueError, match="crosswalk_source for 'T'"):
        describe_variables(ds, crosswalk_sources=allowed)
