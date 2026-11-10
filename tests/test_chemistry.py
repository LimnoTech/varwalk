"""convert_basis and convert_amount. See docs/units.md section 5."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pint")
molmass = pytest.importorskip("molmass")

from fixtures import NOW, STAMP, cube, record, table, values  # noqa: E402

from varwalk.annotate import annotate  # noqa: E402
from varwalk.chemistry import convert_amount, convert_basis  # noqa: E402


def mass(formula: str) -> float:
    return molmass.Formula(formula).mass


def nitrate(
    make=table, units="umol l-1", kind="AmountOfSubstanceConcentration", basis="N"
):
    fields = {
        "quantity_kind": kind,
        "counting": "amount",
        "species": "NO3-",
        "basis": basis,
    }
    return annotate(make({"NO3": ([100.0], units)}), {"NO3": fields})


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
def test_100_umol_per_litre_nitrate_is_1_40_mg_per_litre_as_n(make):
    out = convert_amount(nitrate(make), {"NO3": "mg l-1"}, now=NOW)
    assert round(values(out, "NO3")[0], 2) == 1.40
    assert values(out, "NO3")[0] == pytest.approx(100e-3 * mass("N"), rel=1e-12)
    assert record(out, "NO3")["units"] == "mg l-1"
    assert record(out, "NO3")["quantity_kind"] == "MassConcentration"
    assert out.attrs["history"].endswith(
        f"{STAMP} varwalk: convert_amount: NO3 'umol l-1' "
        "(AmountOfSubstanceConcentration, amount) -> 'mg l-1' (MassConcentration, "
        "mass) as N, "
        "species NO3-, x0.0140067 (year setting: julian)"
    )


def test_and_6_20_mg_per_litre_as_nitrate():
    as_n = convert_amount(nitrate(), {"NO3": "mg l-1"})
    as_no3 = convert_basis(as_n, {"NO3": "NO3-"})
    assert round(values(as_no3, "NO3")[0], 2) == 6.20
    assert record(as_no3, "NO3")["basis"] == "NO3-"
    assert record(as_no3, "NO3")["units"] == "mg l-1"
    direct = convert_amount(nitrate(basis="NO3-"), {"NO3": "mg l-1"})
    assert values(direct, "NO3")[0] == pytest.approx(
        values(as_no3, "NO3")[0], rel=1e-12
    )


def test_ammonium_to_nitrogen_and_back():
    data = annotate(
        table({"NH4": ([1.0], "mg l-1")}),
        {
            "NH4": {
                "quantity_kind": "MassConcentration",
                "counting": "mass",
                "species": "NH4+",
                "basis": "NH4+",
            }
        },
    )
    as_n = convert_basis(data, {"NH4": "N"})
    assert values(as_n, "NH4")[0] == pytest.approx(mass("N") / mass("NH4+"), rel=1e-12)
    assert values(as_n, "NH4")[0] == pytest.approx(0.7765, abs=1e-4)
    back = convert_basis(as_n, {"NH4": "NH4+"})
    assert values(back, "NH4")[0] == pytest.approx(1.0, rel=1e-12)


@pytest.mark.parametrize(
    ("name", "species", "basis", "mg_per_meq"),
    [("Ca", "Ca+2", "Ca", 40.078 / 2), ("SO4", "SO4-2", "S", 32.0648 / 2)],
)
def test_milliequivalents_to_milligrams_and_back_are_positive(
    name, species, basis, mg_per_meq
):
    data = annotate(
        table({name: ([1.0], "mmol l-1")}),
        {
            name: {
                "quantity_kind": "EquivalentConcentration",
                "species": species,
                "basis": basis,
            }
        },
    )
    as_mg = convert_amount(data, {name: "mg l-1"})
    assert values(as_mg, name)[0] == pytest.approx(mg_per_meq, rel=1e-4)
    assert values(as_mg, name)[0] > 0
    back = convert_amount(as_mg, {name: "meq l-1"})
    assert values(back, name)[0] == pytest.approx(1.0, rel=1e-12)
    assert record(back, name)["units"] == "mmol l-1"
    assert record(back, name)["quantity_kind"] == "AmountOfSubstanceConcentration"
    assert record(back, name)["counting"] == "equivalents"


def test_a_basis_the_species_lacks_raises():
    data = annotate(
        table({"NH4": ([1.0], "mg l-1")}),
        {
            "NH4": {
                "quantity_kind": "MassConcentration",
                "counting": "mass",
                "species": "NH4+",
                "basis": "N",
            }
        },
    )
    with pytest.raises(ValueError, match="species 'NH4\\+' contains no S"):
        convert_basis(data, {"NH4": "S"})


def test_species_and_basis_are_required():
    data = annotate(
        table({"NO3": ([1.0], "mg l-1")}),
        {"NO3": {"quantity_kind": "MassConcentration"}},
    )
    with pytest.raises(ValueError, match="'NO3' has no species or basis"):
        convert_amount(data, {"NO3": "umol l-1"})


def test_equivalents_of_an_uncharged_species_raise():
    data = annotate(
        table({"N": ([1.0], "mg l-1")}),
        {
            "N": {
                "quantity_kind": "MassConcentration",
                "counting": "mass",
                "species": "N",
                "basis": "N",
            }
        },
    )
    with pytest.raises(ValueError, match="has no charge"):
        convert_amount(data, {"N": "meq l-1"})


def test_same_counting_is_convert_units_work():
    with pytest.raises(ValueError, match="already counted as amount"):
        convert_amount(nitrate(), {"NO3": "mmol l-1"})


def test_a_mass_per_area_converts_to_a_local_amount_per_area():
    data = annotate(
        table({"N": ([1.0], "kg ha-1")}),
        {
            "N": {
                "quantity_kind": "MassPerArea",
                "counting": "mass",
                "species": "N",
                "basis": "N",
            }
        },
    )
    out = convert_amount(data, {"N": "mmol m-2"})
    assert values(out, "N")[0] == pytest.approx(
        100.0 / mass("N"), rel=1e-12
    )  # 100 mg m-2
    assert record(out, "N")["quantity_kind"] == "AmountOfSubstancePerArea"
    assert record(out, "N")["units"] == "mmol m-2"


def test_a_deposition_flux_converts_to_mmol_per_m2_per_day():
    data = annotate(
        table({"N": ([1.0], "kg ha-1 julian_year-1")}),
        {
            "N": {
                "quantity_kind": "MassPerAreaTime",
                "counting": "mass",
                "species": "N",
                "basis": "N",
            }
        },
    )
    out = convert_amount(data, {"N": "mmol m-2 d-1"})
    expected = 1e6 / 1e4 / mass("N") / 365.25  # mg/m2/yr -> mmol/m2/d
    assert values(out, "N")[0] == pytest.approx(expected, rel=1e-12)
    assert record(out, "N")["quantity_kind"] == "MolarFluxDensity"
    assert record(out, "N")["units"] == "mmol d-1 m-2"


def test_same_counting_advice_is_convert_units_and_it_works():
    from varwalk.convert import convert_units

    with pytest.raises(ValueError, match="'NO3'.*convert_units"):
        convert_amount(nitrate(), {"NO3": "mmol l-1"})
    out = convert_units(nitrate(), {"NO3": "mmol l-1"})
    assert values(out, "NO3")[0] == pytest.approx(0.1, rel=1e-12)


def test_equivalents_to_equivalents_does_not_send_a_meq_target_to_convert_units():
    data = annotate(
        table({"Ca": ([1.0], "mmol l-1")}),
        {
            "Ca": {
                "quantity_kind": "EquivalentConcentration",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    with pytest.raises(ValueError, match="'Ca'.*already counted as equivalent") as err:
        convert_amount(data, {"Ca": "meq l-1"})
    assert "mmol l-1" in str(err.value)


def test_mass_to_amount_is_never_sent_to_convert_units():
    data = annotate(
        table({"N": ([1.0], "mg l-1")}),
        {
            "N": {
                "quantity_kind": "MassConcentration",
                "counting": "mass",
                "species": "N",
                "basis": "N",
            }
        },
    )
    out = convert_amount(data, {"N": "umol l-1"})
    assert record(out, "N")["units"] == "umol l-1"


@pytest.mark.parametrize(
    "call",
    [
        lambda d: convert_basis(d, {"NO3": "S"}),
        lambda d: convert_amount(d, {"NO3": "not a unit"}),
        lambda d: convert_amount(d, {"NO3": "m"}),
    ],
    ids=["basis", "unparsable", "dimension"],
)
def test_every_refusal_names_the_variable(call):
    with pytest.raises(ValueError, match="'NO3'"):
        call(nitrate())


# --- range attributes follow the values


def test_packed_valid_max_follows_convert_basis_then_convert_amount():
    data = annotate(
        cube({"NH4": ([10.0, 20.0, 30.0], "mg l-1")}),
        {
            "NH4": {
                "quantity_kind": "MassConcentration",
                "counting": "mass",
                "species": "NH4+",
                "basis": "NH4+",
            }
        },
    )
    data["NH4"].encoding = {"dtype": "int16", "scale_factor": 0.1}
    data["NH4"].attrs["valid_max"] = 1000  # packed: 100 mg/L of NH4+
    as_n = convert_basis(data, {"NH4": "N"})
    assert as_n["NH4"].attrs["valid_max"] == pytest.approx(
        100.0 * mass("N") / mass("NH4+")
    )
    assert as_n["NH4"].encoding == {}
    as_umol = convert_amount(as_n, {"NH4": "umol l-1"})
    expected = 100.0 / mass("NH4+") * 1000  # umol/L of N in 100 mg/L of NH4+
    assert as_umol["NH4"].attrs["valid_max"] == pytest.approx(expected, rel=1e-12)
    assert values(as_umol, "NH4")[2] == pytest.approx(
        30.0 / mass("NH4+") * 1000, rel=1e-12
    )
    assert data["NH4"].attrs["valid_max"] == 1000


def test_convert_amount_scales_an_unpacked_range_and_keeps_its_container():
    data = nitrate(cube)
    data["NO3"].attrs.update(
        valid_range=[0, 200], actual_range=np.array([100.0, 100.0])
    )
    out = convert_amount(data, {"NO3": "mg l-1"})
    per_umol = 1e-3 * mass("N")
    assert out["NO3"].attrs["valid_range"] == pytest.approx([0.0, 200 * per_umol])
    assert isinstance(out["NO3"].attrs["valid_range"], list)
    assert isinstance(out["NO3"].attrs["actual_range"], np.ndarray)
    assert out["NO3"].attrs["actual_range"] == pytest.approx([100 * per_umol] * 2)


# --- refusals, history, inputs, and amount <-> equivalents


def test_a_new_basis_that_is_not_a_string_is_refused_naming_the_variable():
    with pytest.raises(ValueError, match="^'NO3': the new basis must be a string"):
        convert_basis(nitrate(), {"NO3": ["N"]})


def test_a_message_naming_the_species_still_gets_the_variable_prefix():
    data = annotate(
        table({"N": ([1.0], "mg l-1")}),
        {
            "N": {
                "quantity_kind": "MassConcentration",
                "counting": "mass",
                "species": "N",
                "basis": "N",
            }
        },
    )
    with pytest.raises(ValueError, match="^'N': species 'N' contains no S"):
        convert_basis(data, {"N": "S"})


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
def test_convert_basis_writes_history_on_both_paths(make):
    data = annotate(
        make({"NH4": ([1.0, 2.0, 3.0], "mg l-1")}),
        {
            "NH4": {
                "quantity_kind": "MassConcentration",
                "counting": "mass",
                "species": "NH4+",
                "basis": "NH4+",
            }
        },
    )
    out = convert_basis(data, {"NH4": "N"}, now=NOW)
    factor = mass("N") / mass("NH4+")
    assert values(out, "NH4") == pytest.approx(
        [factor, 2 * factor, 3 * factor], rel=1e-12
    )
    assert record(out, "NH4")["basis"] == "N"
    assert record(out, "NH4")["units"] == "mg l-1"
    assert out.attrs["history"].endswith(
        f"{STAMP} varwalk: convert_basis: NH4 (NH4+) as NH4+ -> as N, "
        f"x{factor:.6g} (year setting: julian)"
    )


@pytest.mark.parametrize("make", [table, cube], ids=["table", "dataset"])
@pytest.mark.parametrize(
    "call",
    [
        lambda d: convert_basis(d, {"NO3": "NO3-"}),
        lambda d: convert_amount(d, {"NO3": "mg l-1"}),
    ],
    ids=["convert_basis", "convert_amount"],
)
def test_chemistry_never_modifies_its_input(make, call):
    data = nitrate(make)
    before_values, before_record = values(data, "NO3"), record(data, "NO3")
    before_history = data.attrs.get("history")
    call(data)
    assert values(data, "NO3") == before_values
    assert record(data, "NO3") == before_record
    assert data.attrs.get("history") == before_history


def test_millimoles_of_sulfate_are_twice_as_many_milliequivalents():
    data = annotate(
        table({"SO4": ([1.0], "mmol l-1")}),
        {
            "SO4": {
                "quantity_kind": "AmountOfSubstanceConcentration",
                "counting": "amount",
                "species": "SO4-2",
                "basis": "S",
            }
        },
    )
    out = convert_amount(data, {"SO4": "meq l-1"})
    assert values(out, "SO4")[0] == pytest.approx(2.0, rel=1e-12)
    assert record(out, "SO4")["quantity_kind"] == "AmountOfSubstanceConcentration"
    assert record(out, "SO4")["counting"] == "equivalents"
    assert record(out, "SO4")["units"] == "mmol l-1"
    back = convert_amount(out, {"SO4": "mmol l-1"})
    assert values(back, "SO4")[0] == pytest.approx(1.0, rel=1e-12)
    assert record(back, "SO4")["quantity_kind"] == "AmountOfSubstanceConcentration"
    assert record(back, "SO4")["counting"] == "amount"


# --- counting decides what a value counts, not the quantity kind


def test_convert_amount_writes_the_counting_it_converts_to():
    as_mass = convert_amount(nitrate(), {"NO3": "mg l-1"})
    assert record(as_mass, "NO3")["counting"] == "mass"
    as_eq = convert_amount(nitrate(), {"NO3": "meq l-1"})
    assert record(as_eq, "NO3")["counting"] == "equivalents"
    assert record(as_eq, "NO3")["units"] == "mmol l-1"
    assert values(as_eq, "NO3")[0] == pytest.approx(
        0.1, rel=1e-12
    )  # NO3-: one N, charge 1


def test_a_variable_without_counting_is_refused_by_name():
    data = nitrate()
    data.attrs["variables"][0].pop("counting")
    with pytest.raises(ValueError, match="'NO3' has no counting"):
        convert_amount(data, {"NO3": "mg l-1"})
    with pytest.raises(ValueError, match="'NO3' has no counting"):
        convert_basis(data, {"NO3": "NO3-"})


# --- equivalents in any dimension


def test_convert_amount_reads_counting_not_the_quantity_kind():
    data = annotate(
        table({"Ca": ([2.0], "mmol l-1")}),
        {
            "Ca": {
                "quantity_kind": "AmountOfSubstanceConcentration",
                "counting": "equivalents",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    out = convert_amount(data, {"Ca": "mg l-1"})
    assert values(out, "Ca")[0] == pytest.approx(
        mass("Ca"), rel=1e-12
    )  # 2 meq = 1 mmol
    assert record(out, "Ca")["counting"] == "mass"


def calcium_flux(units="mmol m-2 d-1", counting="amount", kind="MolarFluxDensity"):
    fields = {
        "quantity_kind": kind,
        "counting": counting,
        "species": "Ca+2",
        "basis": "Ca",
    }
    return annotate(table({"Ca": ([1.0], units)}), {"Ca": fields})


def test_a_millimole_flux_of_calcium_is_two_milliequivalents_and_back():
    as_eq = convert_amount(calcium_flux(), {"Ca": "meq m-2 d-1"}, now=NOW)
    assert values(as_eq, "Ca")[0] == pytest.approx(2.0, rel=1e-12)
    assert record(as_eq, "Ca")["units"] == "mmol d-1 m-2"
    assert record(as_eq, "Ca")["quantity_kind"] == "MolarFluxDensity"
    assert record(as_eq, "Ca")["counting"] == "equivalents"
    assert as_eq.attrs["history"].endswith(
        f"{STAMP} varwalk: convert_amount: Ca 'mmol m-2 d-1' (MolarFluxDensity, "
        "amount) -> 'mmol d-1 m-2' (MolarFluxDensity, equivalents) as Ca, species "
        "Ca+2, x2 "
        "(year setting: julian)"
    )
    back = convert_amount(as_eq, {"Ca": "mmol m-2 d-1"})
    assert values(back, "Ca")[0] == pytest.approx(1.0, rel=1e-12)
    assert record(back, "Ca")["quantity_kind"] == "MolarFluxDensity"
    assert record(back, "Ca")["counting"] == "amount"


def test_sulfate_deposition_in_equivalents_is_positive():
    data = annotate(
        table({"SO4": ([1.0], "kg ha-1 julian_year-1")}),
        {
            "SO4": {
                "quantity_kind": "MassPerAreaTime",
                "counting": "mass",
                "species": "SO4-2",
                "basis": "SO4-2",
            }
        },
    )
    out = convert_amount(data, {"SO4": "eq ha-1 julian_year-1"})
    assert values(out, "SO4")[0] == pytest.approx(2 * 1000 / mass("SO4-2"), rel=1e-12)
    assert values(out, "SO4")[0] > 0
    assert record(out, "SO4")["quantity_kind"] == "MolarFluxDensity"


def test_keq_per_hectare_of_calcium_and_kg_per_hectare_as_calcium():
    # a base-cation deposition published in keq/ha; it is written in
    # kmol ha-1
    data = calcium_flux("kmol ha-1", "equivalents", "AmountOfSubstancePerArea")
    as_kg = convert_amount(data, {"Ca": "kg ha-1"})
    assert values(as_kg, "Ca")[0] == pytest.approx(
        mass("Ca") / 2, rel=1e-12
    )  # 1 keq = 0.5 kmol
    assert record(as_kg, "Ca")["quantity_kind"] == "MassPerArea"
    assert record(as_kg, "Ca")["counting"] == "mass"
    back = convert_amount(as_kg, {"Ca": "keq ha-1"})
    assert values(back, "Ca")[0] == pytest.approx(1.0, rel=1e-12)
    assert record(back, "Ca")["units"] == "kmol ha-1"
    assert record(back, "Ca")["quantity_kind"] == "AmountOfSubstancePerArea"
    assert record(back, "Ca")["counting"] == "equivalents"


def test_an_equivalent_concentration_is_written_in_its_dimensional_kind():
    data = annotate(
        table({"Ca": ([2.0], "mmol l-1")}),
        {
            "Ca": {
                "quantity_kind": "EquivalentConcentration",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    out = convert_amount(data, {"Ca": "mmol l-1"})
    assert values(out, "Ca")[0] == pytest.approx(1.0, rel=1e-12)
    assert record(out, "Ca")["quantity_kind"] == "AmountOfSubstanceConcentration"
    assert record(out, "Ca")["counting"] == "amount"


def test_a_molar_equivalent_is_written_in_its_dimensional_kind():
    data = annotate(
        table({"Ca": ([2.0], "mmol")}),
        {"Ca": {"quantity_kind": "MolarEquivalent", "species": "Ca+2", "basis": "Ca"}},
    )
    out = convert_amount(data, {"Ca": "mg"})
    assert values(out, "Ca")[0] == pytest.approx(
        mass("Ca"), rel=1e-12
    )  # 2 meq = 1 mmol
    assert record(out, "Ca")["quantity_kind"] == "Mass"
    assert record(out, "Ca")["counting"] == "mass"


def test_a_mass_amount_change_without_a_paired_kind_is_refused():
    data = annotate(
        table({"Ca": ([1.0], "mg kg-1")}),
        {
            "Ca": {
                "quantity_kind": "MassFraction",
                "counting": "mass",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    with pytest.raises(ValueError) as err:
        convert_amount(data, {"Ca": "mmol kg-1"})
    assert str(err.value) == (
        "'Ca' is MassFraction counted as mass; convert_amount moves mass <-> amount "
        "for "
        "['Mass', 'MassConcentration', 'MassFlowRate', 'MassFluxDensity', "
        "'MassPerArea', "
        "'MassPerAreaTime', 'MassPerTime']"
    )


def test_an_equivalents_target_of_an_area_variable_suggests_its_own_unit():
    data = annotate(
        table({"Ca": ([1.0], "kmol ha-1")}),
        {
            "Ca": {
                "quantity_kind": "AmountOfSubstancePerArea",
                "counting": "equivalents",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    with pytest.raises(ValueError) as err:
        convert_amount(data, {"Ca": "keq ha-1"})
    assert str(err.value) == (
        "'Ca' is already counted as equivalents; rescale it with convert_units, "
        "writing the "
        "target in moles (for example 'kmol ha-1'), not eq"
    )


def test_a_target_of_the_wrong_dimensions_names_the_variable_and_the_kind_it_would_be():
    data = annotate(
        table({"N": ([1.0], "mg l-1")}),
        {
            "N": {
                "quantity_kind": "MassConcentration",
                "counting": "mass",
                "species": "N",
                "basis": "N",
            }
        },
    )
    with pytest.raises(ValueError) as err:
        convert_amount(data, {"N": "mmol m-2"})
    assert str(err.value) == (
        "'N': the amount form of MassConcentration would be "
        "AmountOfSubstanceConcentration "
        "(A1E0L-3I0M0H0T0D0), which does not match the dimensions of the target 'mmol "
        "m-2' "
        "(A1E0L-2I0M0H0T0D0)"
    )


@pytest.mark.parametrize("counting", ["amount", "equivalents"])
def test_convert_basis_keeps_counting(counting):
    data = annotate(
        table({"NH4": ([1.0], "mmol l-1")}),
        {
            "NH4": {
                "quantity_kind": "AmountOfSubstanceConcentration",
                "counting": counting,
                "species": "NH4+",
                "basis": "NH4+",
            }
        },
    )
    out = convert_basis(data, {"NH4": "N"})
    assert values(out, "NH4")[0] == pytest.approx(1.0, rel=1e-12)
    assert record(out, "NH4")["counting"] == counting
    assert record(out, "NH4")["basis"] == "N"


# --- the other QUDT equivalents kinds, dimensionless targets, n != 1


def test_a_cation_exchange_capacity_converts_to_an_amount_per_mass():
    data = annotate(
        table({"CEC": ([10.0], "cmol kg-1")}),
        {
            "CEC": {
                "quantity_kind": "CationExchangeCapacity",
                "species": "Ca+2",
                "basis": "Ca",
                "units_iri": "MilliEQ-PER-HectoGM",
            }
        },
    )
    out = convert_amount(data, {"CEC": "mmol kg-1"})
    assert values(out, "CEC")[0] == pytest.approx(
        50.0, rel=1e-12
    )  # 10 cmolc/kg of Ca+2
    assert record(out, "CEC")["quantity_kind"] == "AmountOfSubstancePerMass"
    assert record(out, "CEC")["counting"] == "amount"
    assert "units_iri" not in record(out, "CEC")


def test_a_reactive_charge_is_written_as_an_amount_of_substance():
    data = annotate(
        table({"Q": ([2.0], "mmol")}),
        {"Q": {"quantity_kind": "ReactiveCharge", "species": "Ca+2", "basis": "Ca"}},
    )
    assert record(data, "Q")["counting"] == "equivalents"
    out = convert_amount(data, {"Q": "mmol"})
    assert values(out, "Q")[0] == pytest.approx(1.0, rel=1e-12)
    assert record(out, "Q")["quantity_kind"] == "AmountOfSubstance"


def mole_fraction():
    fields = {"quantity_kind": "MoleFraction", "counting": "amount", "species": "Ca+2"}
    return annotate(
        table({"Ca": ([1.0], "umol mol-1")}), {"Ca": {**fields, "basis": "Ca"}}
    )


def test_a_mole_fraction_counts_equivalents_in_a_dimensionless_eq_target():
    out = convert_amount(mole_fraction(), {"Ca": "ueq mol-1"})
    assert values(out, "Ca")[0] == pytest.approx(2.0, rel=1e-12)
    assert record(out, "Ca")["counting"] == "equivalents"
    assert record(out, "Ca")["quantity_kind"] == "MoleFraction"
    assert record(out, "Ca")["units"] == "umol mol-1"


def test_a_dimensionless_mass_target_is_a_mass_refused_without_a_paired_kind():
    with pytest.raises(
        ValueError, match="^'Ca' is MoleFraction counted as amount; convert_amount"
    ):
        convert_amount(mole_fraction(), {"Ca": "mg kg-1"})


def dichromate(units="mmol l-1", counting="amount"):
    fields = {"quantity_kind": "AmountOfSubstanceConcentration", "counting": counting}
    return annotate(
        table({"Cr": ([1.0], units)}),
        {"Cr": {**fields, "species": "Cr2O7-2", "basis": "Cr"}},
    )


def test_amount_and_equivalents_with_two_of_the_basis_per_species():
    # 1 mmol of Cr is 0.5 mmol of Cr2O7-2, which carries 2 x 0.5 = 1 meq
    as_eq = convert_amount(dichromate(), {"Cr": "meq l-1"})
    assert values(as_eq, "Cr")[0] == pytest.approx(1.0, rel=1e-12)
    as_mg = convert_amount(dichromate(counting="equivalents"), {"Cr": "mg l-1"})
    assert values(as_mg, "Cr")[0] == pytest.approx(mass("Cr"), rel=1e-12)
    assert values(as_mg, "Cr")[0] == pytest.approx(51.996, abs=1e-3)


def test_a_dataset_range_follows_amount_to_equivalents():
    data = annotate(
        cube({"Ca": ([1.0], "mmol l-1")}),
        {
            "Ca": {
                "quantity_kind": "AmountOfSubstanceConcentration",
                "counting": "amount",
                "species": "Ca+2",
                "basis": "Ca",
            }
        },
    )
    data["Ca"].attrs["valid_max"] = 10.0
    out = convert_amount(data, {"Ca": "meq l-1"})
    assert out["Ca"].attrs["valid_max"] == pytest.approx(20.0, rel=1e-12)
    assert values(out, "Ca")[0] == pytest.approx(2.0, rel=1e-12)


def test_every_equivalents_kind_has_a_dimensional_kind_of_its_dimensions():
    from varwalk import chemistry, qudt

    assert set(chemistry._DIMENSIONAL_KIND) == chemistry.EQUIVALENT_KINDS
    for kind, dimensional in chemistry._DIMENSIONAL_KIND.items():
        vector = qudt.quantity_kind(kind)["dimension_vector"]
        assert qudt.quantity_kind(dimensional)["dimension_vector"] == vector


def test_formula_helpers_are_public_through_chemistry():
    from varwalk import _formula, chemistry

    for name in ("formula", "molar_mass", "charge", "basis_count"):
        assert getattr(chemistry, name) is getattr(_formula, name)
        assert name in chemistry.__all__
