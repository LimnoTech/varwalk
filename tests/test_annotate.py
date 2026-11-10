"""Annotations: annotate, read_table, validate_annotations. See
docs/units.md section 5."""

from __future__ import annotations

import pytest

pytest.importorskip("pint")
pytest.importorskip("molmass")

import pandas as pd  # noqa: E402
from fixtures import NOW, STAMP, cube, record, table  # noqa: E402

from varwalk import annotate as an  # noqa: E402
from varwalk.registry import get_registry  # noqa: E402
from varwalk.variables import (  # noqa: E402
    variables_frame,
    variables_to_records,
)

NITRATE = {
    "quantity_kind": "MassConcentration",
    "counting": "mass",
    "species": "NO3-",
    "basis": "N",
}


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
def test_annotate_adds_fields_and_history_without_touching_the_input(make):
    data = make({"NO3": ([1.0, 2.0], "mg l-1")})
    out = an.annotate(data, {"NO3": NITRATE}, now=NOW)
    assert {k: record(out, "NO3")[k] for k in NITRATE} == NITRATE
    assert (
        out.attrs["history"]
        == f"{STAMP} varwalk: annotate: ['NO3'] (year setting: julian)"
    )
    assert "quantity_kind" not in record(data, "NO3")
    assert "history" not in data.attrs


def test_quantity_kind_is_required():
    data = table({"NO3": ([1.0], "mg l-1")})
    with pytest.raises(ValueError, match="NO3: quantity_kind is required"):
        an.annotate(data, {"NO3": {"species": "NO3-", "basis": "N"}})


def test_conflicting_reannotation_raises_and_the_same_value_is_a_no_op():
    data = an.annotate(table({"NO3": ([1.0], "mg l-1")}), {"NO3": NITRATE})
    again = an.annotate(data, {"NO3": NITRATE})
    assert record(again, "NO3")["basis"] == "N"
    with pytest.raises(
        ValueError,
        match=r"already annotated basis='N'; refusing to change it to 'NO3-'",
    ):
        an.annotate(data, {"NO3": {"basis": "NO3-"}})


def test_an_annotation_corrects_a_wrong_unit_and_records_it():
    # a hand-built dictionary whose units holds kg-N/ha (a unit UDUNITS
    # reads as something else)
    data = table({"n_dw": ([3.0], "kg-N/ha")})
    out = an.annotate(
        data,
        {
            "n_dw": {
                "units": "kg ha-1",
                "quantity_kind": "MassPerArea",
                "counting": "mass",
                "species": "N",
                "basis": "N",
            }
        },
        now=NOW,
    )
    assert record(out, "n_dw")["units"] == "kg ha-1"
    assert record(out, "n_dw")["source_units"] == "kg-N/ha"
    assert out.attrs["history"] == (
        f"{STAMP} varwalk: annotate: ['n_dw']; "
        "replaced n_dw units 'kg-N/ha' -> 'kg ha-1' (year setting: julian)"
    )


def test_a_replacement_unit_is_normalized_and_a_refused_one_names_the_variable():
    data = table({"n_dw": ([3.0], "kg-N/ha/yr")})
    out = an.annotate(
        data,
        {"n_dw": {"units": "kg ha-1 yr-1", "quantity_kind": "MassPerAreaTime"}},
        now=NOW,
    )
    assert record(out, "n_dw")["units"] == "kg ha-1 julian_year-1"
    assert "-> 'kg ha-1 julian_year-1'" in out.attrs["history"]
    with pytest.raises(ValueError, match="n_dw"):
        an.annotate(
            data, {"n_dw": {"units": "kg-N/ha", "quantity_kind": "MassPerArea"}}
        )


@pytest.mark.parametrize("bad", ["NO3", 42, ["NO3"]])
def test_annotations_of_the_wrong_type_raise_value_error(bad):
    with pytest.raises(ValueError, match="mapping or a DataFrame"):
        an.annotate(table({"NO3": ([1.0], "mg l-1")}), bad)


def test_data_that_is_not_a_table_or_dataset_is_a_type_error():
    with pytest.raises(TypeError):
        an.annotate([1, 2], {"NO3": NITRATE})


def test_an_annotation_never_relabels_values_at_another_scale():
    data = table({"P": ([5.0], "ug l-1")})
    with pytest.raises(ValueError, match="use convert_units"):
        an.annotate(
            data, {"P": {"units": "mg l-1", "quantity_kind": "MassConcentration"}}
        )


def test_a_basis_written_into_the_unit_is_caught():
    data = table({"NO3": ([1.0], "mg l-1")})
    with pytest.raises(
        ValueError, match=r"has dimensions A0E0L-3I0M1H0T0D0, but MassPerArea"
    ):
        an.annotate(data, {"NO3": {"quantity_kind": "MassPerArea"}})


def test_equivalents_must_be_written_as_moles():
    data = table({"Ca": ([1.0], "meq/L")})
    with pytest.raises(ValueError, match="UDUNITS has no eq"):
        an.annotate(data, {"Ca": {"quantity_kind": "EquivalentConcentration"}})
    ok = an.annotate(
        table({"Ca": ([1.0], "mmol l-1")}),
        {
            "Ca": {
                "quantity_kind": "EquivalentConcentration",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    assert record(ok, "Ca")["quantity_kind"] == "EquivalentConcentration"
    assert record(ok, "Ca")["counting"] == "equivalents"


def test_deprecated_quantity_kind_is_flagged_with_its_replacement():
    data = table({"SC": ([100.0], "uS cm-1")})
    with pytest.raises(
        ValueError,
        match=(
            "quantity_kind Conductivity is deprecated in QUDT; use ElectricConductivity"
        ),
    ):
        an.annotate(data, {"SC": {"quantity_kind": "Conductivity"}})


@pytest.mark.parametrize(
    ("units", "kind", "iri", "message"),
    [
        ("kg ha-1 julian_year-1", "MassPerAreaTime", "KiloGM-PER-HA-YR", None),
        ("kg ha-1 julian_year-1", "MassFluxDensity", "KiloGM-PER-HA-YR", None),
        (
            "kg ha-1 common_year-1",
            "MassPerAreaTime",
            "KiloGM-PER-HA-YR",
            "3.16881e-12 SI units",
        ),
        (
            "mmol m-2 d-1",
            "MolarFluxDensity",
            "MilliMOL-PER-M2-DAY",
            "PhotosyntheticPhotonFluxDensity",
        ),
        ("mg l-1", "MassConcentration", "MilliGM-PER-L", None),
        ("mg l-1", "MassConcentration", "NOT-A-UNIT", "not a QUDT unit"),
        # QUDT lists MilliMOL-PER-M2 under no kind it has; a local kind
        # matches by dimension
        ("mmol m-2", "AmountOfSubstancePerArea", "MilliMOL-PER-M2", None),
        ("kg ha-1", "MassPerArea", "MilliMOL-PER-M2", "not of MassPerArea"),
        (
            "mmol m-2",
            "AmountOfSubstancePerArea",
            "KiloGM-PER-HA",
            "units_iri KiloGM-PER-HA has dimensions A0E0L-2I0M1H0T0D0, but "
            "AmountOfSubstancePerArea has A1E0L-2I0M0H0T0D0",
        ),
    ],
)
def test_units_iri_checks(units, kind, iri, message):
    registry = get_registry()
    if message is None:
        assert an.iri_fits(units, iri, kind, registry)
    else:
        assert not an.iri_fits(units, iri, kind, registry)
        with pytest.raises(ValueError, match=message):
            an.annotate(
                table({"X": ([1.0], units)}),
                {"X": {"quantity_kind": kind, "units_iri": iri}},
                registry=registry,
            )


def test_a_local_quantity_kind_annotates_an_amount_per_area():
    out = an.annotate(
        table({"Ca": ([0.05], "kmol ha-1")}),
        {"Ca": {"quantity_kind": "AmountOfSubstancePerArea"}},
    )
    assert record(out, "Ca")["quantity_kind"] == "AmountOfSubstancePerArea"
    with pytest.raises(
        ValueError, match="'AmountOfSubstancePerAera' is not a QUDT quantity kind"
    ):
        an.annotate(
            table({"Ca": ([0.05], "kmol ha-1")}),
            {"Ca": {"quantity_kind": "AmountOfSubstancePerAera"}},
        )


def test_qudt_month_is_the_synodic_month():
    registry = get_registry("tropical")
    assert not an.iri_fits("month", "MO", "Time", registry)
    with pytest.raises(ValueError, match="units_iri MO is 2.55144e"):
        an.annotate(
            cube({"T": ([1.0], "month")}),
            {"T": {"quantity_kind": "Time", "units_iri": "MO"}},
            registry=registry,
        )


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"species": "NO3-"}, "species and basis go together; only species is given"),
        (
            {"species": "NO3-", "basis": "Nx"},
            "basis 'Nx' is not a formula molmass can read",
        ),
        ({"species": "NH4+", "basis": "S"}, "species 'NH4\\+' contains no S"),
        ({"process": "deposition"}, "process 'deposition' is not one of"),
    ],
)
def test_chemistry_and_process_fields_are_checked(fields, message):
    data = table({"X": ([1.0], "mg l-1")})
    with pytest.raises(ValueError, match=message):
        an.annotate(data, {"X": {"quantity_kind": "MassConcentration", **fields}})


def test_validate_annotations_lists_every_problem_at_once():
    data = table({"A": ([1.0], "mg l-1"), "B": ([1.0], "mg l-1")})
    data.attrs["variables"][0]["quantity_kind"] = "NotAKind"
    data.attrs["variables"][1]["process"] = "fog"
    with pytest.raises(ValueError) as info:
        an.validate_annotations(data)
    text = str(info.value)
    assert "- A: quantity_kind 'NotAKind' is not a QUDT quantity kind" in text
    assert "- B: quantity_kind is required" in text
    assert "- B: process 'fog'" in text


def test_unannotated_variables_are_not_checked():
    an.validate_annotations(table({"site": ([1.0], None)}))


def test_unknown_variable_and_unknown_field_raise():
    data = table({"NO3": ([1.0], "mg l-1")})
    with pytest.raises(ValueError, match="'NO4' is not a column"):
        an.annotate(data, {"NO4": NITRATE})
    with pytest.raises(
        ValueError, match=r"unknown annotation field\(s\) \['speciation'\]"
    ):
        an.annotate(data, {"NO3": {"speciation": "N"}})


def test_annotated_variables_keeps_the_shared_schema_and_adds_the_fields():
    from varwalk.variables import VARIABLE_COLUMNS

    out = an.annotate(table({"NO3": ([1.0], "mg l-1")}), {"NO3": NITRATE})
    frame = an.annotated_variables(out)
    assert list(frame.columns) == [*VARIABLE_COLUMNS, *an.ANNOTATION_FIELDS]
    assert frame.loc["NO3", "basis"] == "N"
    an.validate_annotations(frame)
    cube_frame = an.annotated_variables(
        an.annotate(cube({"NO3": ([1.0], "mg l-1")}), {"NO3": NITRATE})
    )
    assert cube_frame.loc["NO3", "species"] == "NO3-"


def test_the_shared_schema_carries_annotation_fields():
    from varwalk.variables import variables_frame

    frame = variables_frame([{"name": "NO3", "quantity_kind": "MassConcentration"}])
    assert frame.loc["NO3", "quantity_kind"] == "MassConcentration"


def read_csv_table(tmp_path, text: str, stem: str = "demo"):
    """A curated table written to ``tmp_path`` and read with
    ``read_table``."""
    path = tmp_path / f"{stem}.csv"
    path.write_text(text, encoding="utf-8")
    return an.read_table(path)


# --- read_table: curated tables written to tmp_path


def test_read_table_reads_a_curated_table(tmp_path):
    frame = read_csv_table(
        tmp_path,
        "name,units,quantity_kind,counting,species,basis,process\n"
        "n_dw,kg ha-1,MassPerArea,mass,N,N,dry_deposition\n"
        "n_ww,kg ha-1,MassPerArea,mass,N,N,\n",
    )
    assert list(frame.index) == ["n_dw", "n_ww"]
    assert frame.loc["n_dw", "process"] == "dry_deposition"
    data = table({"n_dw": ([1.0], "kg-N/ha"), "n_ww": ([2.0], "kg-N/ha")})
    out = an.annotate(data, frame)
    assert "process" not in record(out, "n_ww")
    assert record(out, "n_ww")["units"] == "kg ha-1"


def test_read_table_rejects_unknown_columns(tmp_path):
    with pytest.raises(ValueError, match=r"unknown column\(s\) \['speciation'\]"):
        read_csv_table(tmp_path, "name,speciation\nn_dw,N\n")


def test_a_curated_table_without_quantity_kind_is_refused(tmp_path):
    with pytest.raises(ValueError, match="nokind.*quantity_kind"):
        read_csv_table(
            tmp_path, "name,units,species,basis\nx,mg l-1,NO3-,Nx\n", "nokind"
        )
    frame = pd.DataFrame(
        {"units": ["mg l-1"], "species": ["NO3-"], "basis": ["Nx"]},
        index=pd.Index(["x"], name="name"),
    )
    with pytest.raises(ValueError, match="- x: quantity_kind is required"):
        an.validate_annotations(frame)


def test_read_table_reads_with_the_pyarrow_engine(tmp_path, monkeypatch):
    seen = {}
    real = pd.read_csv

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", spy)
    read_csv_table(tmp_path, "name,units,quantity_kind\nx,mg l-1,MassConcentration\n")
    assert seen["engine"] == "pyarrow"


def test_read_table_reads_a_file_once_per_path(tmp_path):
    path = tmp_path / "demo.csv"
    path.write_text("name,quantity_kind\nx,Length\n", encoding="utf-8")
    an.read_table.cache_clear()
    assert an.read_table(path) is an.read_table(path)
    an.read_table.cache_clear()


def test_a_units_only_correction_still_needs_a_quantity_kind():
    data = table({"n_dw": ([3.0], "kg-N/ha")})
    with pytest.raises(ValueError, match="n_dw: quantity_kind is required"):
        an.annotate(data, {"n_dw": {"units": "kg ha-1"}})


def test_refusals_name_what_failed():
    import pandas as pd

    data = table({"A": ([1.0], "mg l-1"), "B": ([1.0], "mg l-1")})
    dup = pd.DataFrame(
        {"quantity_kind": ["MassConcentration"] * 2},
        index=pd.Index(["A", "A"], name="name"),
    )
    with pytest.raises(ValueError, match=r"more than once: \['A'\]"):
        an.annotate(data, dup)
    with pytest.raises(ValueError, match=r"'A': units: the values are in"):
        an.annotate(
            data, {"A": {"units": "ug l-1", "quantity_kind": "MassConcentration"}}
        )


# --- a curated table covers a whole dataset; a mapping names what
#     the caller means

AMMONIUM = {
    "quantity_kind": "MassConcentration",
    "counting": "mass",
    "species": "NH4+",
    "basis": "N",
}


def curated():
    import pandas as pd

    return pd.DataFrame.from_dict(
        {"NO3": NITRATE, "NH4": AMMONIUM}, orient="index"
    ).rename_axis("name")


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
def test_a_curated_table_skips_variables_the_data_does_not_hold(make):
    out = an.annotate(make({"NO3": ([1.0], "mg l-1")}), curated(), now=NOW)
    assert record(out, "NO3")["species"] == "NO3-"
    assert (
        out.attrs["history"]
        == f"{STAMP} varwalk: annotate: ['NO3'] (year setting: julian)"
    )


def test_a_mapping_still_refuses_a_variable_the_data_does_not_hold():
    data = table({"NO3": ([1.0], "mg l-1")})
    with pytest.raises(ValueError, match="'NH4' is not a column"):
        an.annotate(data, {"NO3": NITRATE, "NH4": AMMONIUM})


# --- counting: what a chemical value counts


def test_counting_is_required_wherever_species_is_set():
    data = table({"NO3": ([1.0], "mg l-1")})
    fields = {"quantity_kind": "MassConcentration", "species": "NO3-", "basis": "N"}
    with pytest.raises(
        ValueError, match="NO3: counting is required wherever species is set"
    ):
        an.annotate(data, {"NO3": fields})
    out = an.annotate(data, {"NO3": {**fields, "counting": "mass"}})
    assert record(out, "NO3")["counting"] == "mass"


def test_counting_takes_mass_amount_or_equivalents_only():
    data = table({"NO3": ([1.0], "mg l-1")})
    with pytest.raises(ValueError, match="counting 'moles' is not one of"):
        an.annotate(data, {"NO3": {**NITRATE, "counting": "moles"}})


@pytest.mark.parametrize(
    ("units", "kind", "counting", "message"),
    [
        (
            "mg l-1",
            "MassConcentration",
            "amount",
            "counting 'amount' needs a unit in mol",
        ),
        (
            "mg l-1",
            "MassConcentration",
            "equivalents",
            "counting 'equivalents' needs a unit in mol",
        ),
        (
            "mmol l-1",
            "AmountOfSubstanceConcentration",
            "mass",
            "counting 'mass' needs a unit",
        ),
        ("mmol l-1", "AmountOfSubstanceConcentration", "amount", None),
        ("mmol l-1", "AmountOfSubstanceConcentration", "equivalents", None),
        ("meq/L", "AmountOfSubstanceConcentration", "equivalents", "UDUNITS has no eq"),
        ("mmol m-2 d-1", "MolarFluxDensity", "equivalents", None),
        ("kmol ha-1", "AmountOfSubstancePerArea", "equivalents", None),
        # a mass fraction (USGS 00621, nitrate in sediment as N): no
        # mass in the dimension, but QUDT's MassFraction has a mass
        # numerator
        ("mg kg-1", "MassFraction", "mass", None),
        # a mole fraction is the same shape counting moles: no amount in
        # the dimension, but QUDT's MoleFraction has an amount of
        # substance in its numerator
        ("mol mol-1", "MoleFraction", "amount", None),
        ("mol mol-1", "MoleFraction", "equivalents", None),
        ("mol mol-1", "MoleFraction", "mass", "counting 'mass' needs a unit with mass"),
        ("mg kg-1", "MassFraction", "amount", "counting 'amount' needs a unit in mol"),
        ("1", "Dimensionless", "amount", "counting 'amount' needs a unit in mol"),
    ],
)
def test_counting_is_checked_against_the_units_dimension(
    units, kind, counting, message
):
    data = table({"Ca": ([1.0], units)})
    fields = {
        "quantity_kind": kind,
        "counting": counting,
        "species": "Ca+2",
        "basis": "Ca",
    }
    if message is None:
        assert record(an.annotate(data, {"Ca": fields}), "Ca")["counting"] == counting
    else:
        with pytest.raises(ValueError, match=message):
            an.annotate(data, {"Ca": fields})


def test_equivalents_of_an_uncharged_species_are_refused():
    data = table({"N": ([1.0], "mmol m-2 d-1")})
    fields = {"quantity_kind": "MolarFluxDensity", "species": "N", "basis": "N"}
    with pytest.raises(ValueError, match="needs a charged species; 'N' has no charge"):
        an.annotate(data, {"N": {**fields, "counting": "equivalents"}})
    an.annotate(data, {"N": {**fields, "counting": "amount"}})


def test_equivalent_concentration_implies_equivalents_and_a_conflict_raises():
    data = table({"Ca": ([1.0], "mmol l-1")})
    kind = {
        "quantity_kind": "EquivalentConcentration",
        "species": "Ca+2",
        "basis": "Ca",
    }
    out = an.annotate(data, {"Ca": kind})
    assert record(out, "Ca")["counting"] == "equivalents"
    again = an.annotate(out, {"Ca": {**kind, "counting": "equivalents"}})  # a no-op
    assert record(again, "Ca") == record(out, "Ca")
    with pytest.raises(
        ValueError, match="EquivalentConcentration counts equivalents, so counting"
    ):
        an.annotate(data, {"Ca": {**kind, "counting": "amount"}})


def test_counting_may_be_given_without_a_species():
    # acid-neutralizing capacity counts equivalents of no single species
    data = table({"ANC": ([120.0], "umol l-1")})
    out = an.annotate(
        data,
        {
            "ANC": {
                "quantity_kind": "AmountOfSubstanceConcentration",
                "counting": "equivalents",
            }
        },
    )
    assert record(out, "ANC")["counting"] == "equivalents"


def test_a_curated_table_row_with_a_species_and_no_counting_is_reported(tmp_path):
    frame = read_csv_table(
        tmp_path,
        "name,units,quantity_kind,counting,species,basis\n"
        "ca,keq ha-1,AmountOfSubstancePerArea,,Ca+2,Ca\n",
    )
    with pytest.raises(
        ValueError, match="- ca: counting is required wherever species is set"
    ):
        an.validate_annotations(frame)


@pytest.mark.parametrize(
    ("units", "kind", "counting", "iri", "message"),
    [
        (
            "mmol l-1",
            "AmountOfSubstanceConcentration",
            "equivalents",
            "MilliEQ-PER-L",
            None,
        ),
        ("mmol l-1", "EquivalentConcentration", None, "MilliEQ-PER-L", None),
        (
            "mmol l-1",
            "AmountOfSubstanceConcentration",
            "amount",
            "MilliMOL-PER-L",
            None,
        ),
        (
            "mmol l-1",
            "AmountOfSubstanceConcentration",
            "equivalents",
            "MilliMOL-PER-L",
            "count moles of a substance, but the variable counts equivalents",
        ),
        (
            "mmol l-1",
            "AmountOfSubstanceConcentration",
            "amount",
            "MilliEQ-PER-L",
            "is a unit of \\['EquivalentConcentration'\\], not of",
        ),
        (
            "mmol m-2 d-1",
            "MolarFluxDensity",
            "equivalents",
            "MilliMOL-PER-M2-DAY",
            "but the variable counts equivalents",
        ),
        (
            "mol",
            "AmountOfSubstance",
            "equivalents",
            "MilliEQ-PER-L",
            "has dimensions A1E0L-3",
        ),
    ],
)
def test_a_units_iri_on_equivalents_must_be_an_equivalents_unit(
    units, kind, counting, iri, message
):
    registry = get_registry()
    assert an.iri_fits(units, iri, kind, registry, counting=counting) is (
        message is None
    )
    if message is not None:
        fields = {"quantity_kind": kind, "units_iri": iri}
        if counting is not None:
            fields["counting"] = counting
        with pytest.raises(ValueError, match=message):
            an.annotate(table({"X": ([1.0], units)}), {"X": fields}, registry=registry)


def test_molar_equivalent_implies_equivalents_too():
    data = table({"Ca": ([2.0], "mmol")})
    kind = {"quantity_kind": "MolarEquivalent", "species": "Ca+2", "basis": "Ca"}
    assert record(an.annotate(data, {"Ca": kind}), "Ca")["counting"] == "equivalents"
    with pytest.raises(
        ValueError, match="MolarEquivalent counts equivalents, so counting"
    ):
        an.annotate(data, {"Ca": {**kind, "counting": "amount"}})


def test_iri_fits_derives_counting_from_an_equivalents_kind(monkeypatch):
    seen = []
    real = an._iri_problems

    def spy(*args, **kwargs):
        seen.append(kwargs.get("counting"))
        return real(*args, **kwargs)

    monkeypatch.setattr(an, "_iri_problems", spy)
    registry = get_registry()
    assert an.iri_fits("mmol l-1", "MilliEQ-PER-L", "EquivalentConcentration", registry)
    assert not an.iri_fits(
        "mmol l-1", "MilliMOL-PER-L", "EquivalentConcentration", registry
    )
    assert an.iri_fits(
        "mmol l-1", "MilliMOL-PER-L", "AmountOfSubstanceConcentration", registry
    )
    # an explicit counting wins over the kind's
    assert an.iri_fits(
        "mmol l-1",
        "MilliMOL-PER-L",
        "AmountOfSubstanceConcentration",
        registry,
        counting="amount",
    )
    assert seen == ["equivalents", "equivalents", None, "amount"]


# --- a dimensionless kind is judged by its unit's numerator; three more
#     equivalents kinds


@pytest.mark.parametrize(
    ("units", "kind", "counting", "message"),
    [
        ("mg kg-1", "MoleFraction", "amount", "counting 'amount' needs a unit in mol"),
        (
            "mg kg-1",
            "MoleFraction",
            "equivalents",
            "counting 'equivalents' needs a unit in mol",
        ),
        (
            "mmol mol-1",
            "MassFraction",
            "mass",
            "counting 'mass' needs a unit with mass",
        ),
        # a numerator with neither falls back to the kind's own
        # numerator
        ("1", "MoleFraction", "amount", None),
        ("percent", "MassFraction", "mass", None),
        ("percent", "MassFraction", "amount", "counting 'amount' needs a unit in mol"),
        ("umol mol-1", "MoleFraction", "amount", None),
    ],
)
def test_a_dimensionless_kind_is_judged_by_the_units_numerator(
    units, kind, counting, message
):
    data = table({"X": ([1.0], units)})
    fields = {"quantity_kind": kind, "counting": counting}
    if message is None:
        assert record(an.annotate(data, {"X": fields}), "X")["counting"] == counting
    else:
        with pytest.raises(ValueError, match=message):
            an.annotate(data, {"X": fields})


def test_the_equivalents_kinds_are_the_qudt_roots_and_every_kind_specializing_one():
    from varwalk import chemistry, qudt
    from varwalk.dictionary import equivalent_kinds

    assert chemistry.EQUIVALENT_KINDS == equivalent_kinds()
    assert equivalent_kinds() == {
        "EquivalentConcentration",
        "MolarEquivalent",
        "ReactiveCharge",
        "ReactiveChargePerMass",
        "CationExchangeCapacity",
    }
    kinds = qudt.quantity_kinds_table()
    for name in equivalent_kinds():
        parents = set(kinds.loc[name, "specialization_of"])
        roots = {"EquivalentConcentration", "MolarEquivalent", "ReactiveChargePerMass"}
        assert name in roots or parents & equivalent_kinds()


def test_a_cation_exchange_capacity_counts_equivalents_and_fits_its_qudt_unit():
    registry = get_registry()
    assert an.iri_fits(
        "cmol kg-1",
        "MilliEQ-PER-HectoGM",
        "CationExchangeCapacity",
        registry,
        counting="equivalents",
    )
    assert an.iri_fits(
        "cmol kg-1", "MilliEQ-PER-HectoGM", "CationExchangeCapacity", registry
    )
    out = an.annotate(
        table({"CEC": ([12.0], "cmol kg-1")}),
        {
            "CEC": {
                "quantity_kind": "CationExchangeCapacity",
                "units_iri": "MilliEQ-PER-HectoGM",
            }
        },
    )
    assert record(out, "CEC")["counting"] == "equivalents"


def test_a_reactive_charge_counted_as_an_amount_conflicts():
    data = table({"Q": ([1.0], "mmol")})
    with pytest.raises(
        ValueError, match="ReactiveCharge counts equivalents, so counting 'amount'"
    ):
        an.annotate(
            data, {"Q": {"quantity_kind": "ReactiveCharge", "counting": "amount"}}
        )
    with pytest.raises(
        ValueError, match="ReactiveCharge counts equivalents, so counting 'amount'"
    ):
        an.iri_fits(
            "mmol", "MilliEQ", "ReactiveCharge", get_registry(), counting="amount"
        )
    with pytest.raises(ValueError, match="counting 'moles' is not one of"):
        an.iri_fits(
            "mmol l-1",
            "MilliMOL-PER-L",
            "AmountOfSubstanceConcentration",
            counting="moles",
        )


def test_a_flux_written_in_eq_is_told_its_own_units_in_mol():
    data = table({"Ca": ([1.0], "meq m-2 d-1")})
    with pytest.raises(
        ValueError, match="units 'meq m-2 d-1': UDUNITS has no eq"
    ) as err:
        an.annotate(data, {"Ca": {"quantity_kind": "MolarFluxDensity"}})
    assert "'mmol d-1 m-2'" in str(err.value)
    assert "'mmol l-1'" not in str(err.value)


# --- source_units: which row of a curated table fits the data


def _source_table(units: str | None, source: str) -> pd.DataFrame:
    """A table as a source attaches it: ``units`` (what UDUNITS
    accepted, or None) beside the published ``source_units``."""
    frame = pd.DataFrame({"Ca": pd.array([1.0], dtype="Float64")})
    rows = [{"name": "Ca", "source_units": source, "units": units}]
    frame.attrs["variables"] = variables_to_records(variables_frame(rows))
    return frame


MEANS_CSV = (
    "name,source_units,units,quantity_kind,counting,units_iri,species,basis,process\n"
    "Ca,mg/L,mg l-1,MassConcentration,mass,MilliGM-PER-L,Ca+2,Ca,none\n"
    "Ca,ueq/L,umol l-1,EquivalentConcentration,equivalents,MicroEQ-PER-L,Ca+2,Ca,none\n"
    "Ca,kg/ha,kg ha-1,MassPerArea,mass,KiloGM-PER-HA,Ca+2,Ca,wet_deposition\n"
)


@pytest.fixture
def means_table(tmp_path):
    return read_csv_table(tmp_path, MEANS_CSV, "demo_means")


@pytest.mark.parametrize(
    ("units", "source", "expected", "kind"),
    [
        ("mg/L", "mg/L", "mg l-1", "MassConcentration"),
        (None, "ueq/L", "umol l-1", "EquivalentConcentration"),
        ("kg/ha", "kg/ha", "kg ha-1", "MassPerArea"),
    ],
)
def test_a_name_takes_the_row_of_the_unit_its_source_published(
    means_table, units, source, expected, kind
):
    out = an.annotate(_source_table(units, source), means_table)
    assert record(out, "Ca")["units"] == expected
    assert record(out, "Ca")["quantity_kind"] == kind
    assert record(out, "Ca")["source_units"] == source
    assert "source_units" not in an.ANNOTATION_FIELDS


def test_a_published_unit_no_row_names_raises(means_table):
    with pytest.raises(
        ValueError, match=r"Ca: the source published it in 'ug/L'.*no row"
    ):
        an.annotate(_source_table("ug/L", "ug/L"), means_table)


def test_reannotating_with_the_same_table_is_a_no_op(means_table):
    once = an.annotate(_source_table(None, "ueq/L"), means_table, now=NOW)
    twice = an.annotate(once, means_table, now=NOW)
    assert twice.attrs["variables"] == once.attrs["variables"]
    assert twice.attrs["history"] == once.attrs["history"]


def test_a_table_never_matches_by_its_current_units(means_table):
    # another product published in kg ha-1 (source_units 'kg ha-1', not
    # the table's 'kg/ha'): only a Dataset falls back to the current
    # units, so a table record must raise
    with pytest.raises(
        ValueError, match=r"Ca: the source published it in 'kg ha-1'.*no row"
    ):
        an.annotate(_source_table("kg ha-1", "kg ha-1"), means_table)


def test_a_dataset_is_matched_by_its_units_attribute(means_table):
    out = an.annotate(cube({"Ca": ([1.0, 2.0], "mg/L")}), means_table)
    assert record(out, "Ca")["quantity_kind"] == "MassConcentration"
    again = an.annotate(
        out, means_table
    )  # units now 'mg l-1': matched as a re-annotation
    assert record(again, "Ca")["units"] == "mg l-1"
    assert again["Ca"].attrs == out["Ca"].attrs
    assert again.attrs.get("history") == out.attrs.get("history")


def test_a_fresh_dataset_in_moles_never_takes_an_equivalents_row(means_table):
    # umol l-1 is what the equivalents row writes its units as, but the
    # data is not that row's
    with pytest.raises(
        ValueError, match=r"Ca: the source published it in 'umol l-1'.*no row"
    ):
        an.annotate(cube({"Ca": ([1.0, 2.0], "umol l-1")}), means_table)


def test_a_dataset_matches_by_current_units_only_when_it_carries_the_rows_kind(
    tmp_path,
):
    csv = (
        "name,source_units,units,quantity_kind\n"
        "Ca,mg/L,mg l-1,MassConcentration\n"
        "Ca,mg l-1,mg l-1,MassConcentration\n"
    )
    table_ = read_csv_table(tmp_path, csv, "demo_dup")
    once = an.annotate(
        cube({"Ca": ([1.0, 2.0], "mg/L")}), table_
    )  # first row, by source_units
    # now units 'mg l-1' and kind MassConcentration: the first row
    # (re-annotation, by units) and the second (by the published unit)
    # both fit
    with pytest.raises(ValueError, match=r"Ca: .*more than one row"):
        an.annotate(once, table_)


def test_a_blank_source_units_row_matches_any_published_unit(tmp_path):
    csv = "name,source_units,quantity_kind\nCa,,MassConcentration\n"
    frame = read_csv_table(tmp_path, csv, "demo_blank")
    out = an.annotate(_source_table("mg/L", "anything"), frame)
    assert record(out, "Ca")["quantity_kind"] == "MassConcentration"


def test_a_blank_source_units_attribute_falls_back_to_units():
    from varwalk.dictionary import source_units

    data = cube({"Ca": ([1.0, 2.0], "mg/L")})
    data["Ca"].attrs["source_units"] = ""
    assert source_units(data, "Ca") == "mg/L"


def test_validate_annotations_refuses_a_repeated_name_in_a_frame_without_source_units():
    frame = pd.DataFrame(
        {"quantity_kind": ["MassConcentration", "MassPerArea"]},
        index=pd.Index(["Ca", "Ca"], name="name"),
    )
    with pytest.raises(ValueError, match=r"names a variable more than once: \['Ca'\]"):
        an.validate_annotations(frame)


def test_validate_annotations_checks_every_row_of_a_repeated_name(tmp_path):
    bad = MEANS_CSV.replace("kg ha-1,MassPerArea", "kg ha-1,MassConcentration")
    frame = read_csv_table(tmp_path, bad, "demo_means")
    with pytest.raises(
        ValueError, match=r"Ca \[kg/ha\]: units 'kg ha-1' has dimensions"
    ):
        an.validate_annotations(frame)


@pytest.mark.parametrize(
    ("csv", "match"),
    [
        (
            "name,source_units,quantity_kind\nCa,mg/L,MassConcentration\nCa,mg/L,MassConcentration\n",
            r"names a variable and source_units more than once: \[\('Ca', 'mg/L'\)\]",
        ),
        (
            "name,source_units,quantity_kind\nCa,,MassConcentration\nCa,kg/ha,MassPerArea\n",
            r"several rows for \['Ca'\], so each must state its source_units",
        ),
    ],
)
def test_read_table_refuses_ambiguous_rows(tmp_path, csv, match):
    with pytest.raises(ValueError, match=match):
        read_csv_table(tmp_path, csv)


def test_a_unit_set_where_the_source_had_none_names_the_published_string():
    # what a data dictionary holds when UDUNITS refuses the published
    # unit: no units, kg-N/ha published
    data = _source_table(None, "kg-N/ha").rename(columns={"Ca": "n_dw"})
    data.attrs["variables"][0]["name"] = "n_dw"
    out = an.annotate(
        data,
        {
            "n_dw": {
                "units": "kg ha-1",
                "quantity_kind": "MassPerArea",
                "counting": "mass",
                "species": "N",
                "basis": "N",
            }
        },
        now=NOW,
    )
    assert record(out, "n_dw")["units"] == "kg ha-1"
    assert out.attrs["history"] == (
        f"{STAMP} varwalk: annotate: ['n_dw']; "
        "set n_dw units 'kg ha-1' (source_units 'kg-N/ha') (year setting: julian)"
    )


# --- a published unit that mislabels its values is corrected, and the
#     label kept


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
def test_a_mislabelled_unit_is_corrected_and_the_label_kept(make):
    # a variable published as 'ft' whose values are metres: the source
    # labelled it wrongly. A curated row for source_units 'ft' states
    # the unit the values are in.
    if make is table:
        data = _source_table(None, "ft").rename(columns={"Ca": "h"})
        data.attrs["variables"][0]["name"] = "h"
        data["h"] = pd.array([1.0], dtype="Float64")
    else:
        data = cube({"h": ([1.0], None)})
        data["h"].attrs["source_units"] = "ft"
    curated_ = pd.DataFrame(
        {"source_units": ["ft"], "units": ["m"], "quantity_kind": ["Length"]},
        index=pd.Index(["h"], name="name"),
    )
    out = an.annotate(data, curated_, now=NOW)
    assert record(out, "h")["units"] == "m"
    assert record(out, "h")["source_units"] == "ft"
    assert record(out, "h")["quantity_kind"] == "Length"
    assert list(map(float, out["h"].to_numpy())) == list(
        map(float, data["h"].to_numpy())
    )
    assert out.attrs["history"] == (
        f"{STAMP} varwalk: annotate: ['h']; "
        "set h units 'm' (source_units 'ft') (year setting: julian)"
    )
