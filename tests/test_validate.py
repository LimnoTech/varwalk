"""QUDT dimension vectors from pint units, and quantity-kind checks. docs/units.md section 6."""

from __future__ import annotations

import pytest

pytest.importorskip("pint")

from varwalk import qudt  # noqa: E402
from varwalk.validate import check_quantity_kind, dimension_vector  # noqa: E402


@pytest.mark.parametrize(
    ("units", "expected"),
    [
        ("uS/cm", "A0E2L-3I0M-1H0T3D0"),
        ("kg/ha/yr", "A0E0L-2I0M1H0T-1D0"),
        ("mg l-1", "A0E0L-3I0M1H0T0D0"),
        ("umol/L", "A1E0L-3I0M0H0T0D0"),
        ("degC", "A0E0L0I0M0H1T0D0"),
        ("percent", "A0E0L0I0M0H0T0D1"),
        ("1", "A0E0L0I0M0H0T0D1"),
    ],
)
def test_dimension_vector_matches_qudt_notation(units, expected):
    assert dimension_vector(units) == expected


@pytest.mark.parametrize(
    ("units", "qudt_unit"),
    [
        ("mg/L", "MilliGM-PER-L"),
        ("uS/cm", "MicroS-PER-CentiM"),
        ("kg/ha/yr", "KiloGM-PER-HA-YR"),
    ],
)
def test_dimension_vector_agrees_with_the_shipped_subset(units, qudt_unit):
    assert dimension_vector(units) == qudt.unit(qudt_unit)["dimension_vector"]


def test_fractional_exponent_raises():
    with pytest.raises(ValueError, match="non-integer"):
        dimension_vector("m**0.5")


def test_matching_quantity_kind_passes():
    check_quantity_kind("mg l-1", "MassConcentration")
    check_quantity_kind("kg ha-1 julian_year-1", "MassPerAreaTime")


def test_basis_in_a_unit_string_is_caught():
    # pint reads "N" as newton, so the dimensions are wrong for a mass per area
    with pytest.raises(ValueError, match="MassPerArea"):
        check_quantity_kind("g N m-2", "MassPerArea")


def test_unknown_quantity_kind_raises():
    with pytest.raises(ValueError, match="NotAQuantityKind"):
        check_quantity_kind("mol m-3", "NotAQuantityKind")


def test_unparseable_string_in_dimension_vector_raises_value_error():
    with pytest.raises(ValueError, match="mg/L as Nx"):
        dimension_vector("mg/L as Nx")


def test_dimension_vector_accepts_a_unit_from_another_year_setting():
    from varwalk.registry import get_registry

    common = get_registry("common").Unit("kg/ha")
    assert dimension_vector(common, get_registry("julian")) == "A0E0L-2I0M1H0T0D0"


def test_a_local_kind_is_checked_like_a_qudt_one():
    check_quantity_kind("kmol ha-1", "AmountOfSubstancePerArea")
    check_quantity_kind("mmol m-2", "AmountOfSubstancePerArea")
    with pytest.raises(
        ValueError, match="but AmountOfSubstancePerArea has A1E0L-2I0M0H0T0D0"
    ):
        check_quantity_kind("kg ha-1", "AmountOfSubstancePerArea")
