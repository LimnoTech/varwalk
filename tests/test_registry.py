"""The private pint registry: year settings, CF output, isolation. See docs/units.md section 4."""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap

import pytest

pint = pytest.importorskip("pint")
cf_units = pytest.importorskip("cf_units")

from varwalk import registry as reg  # noqa: E402

DAYS = {"julian": 365.25, "common": 365.0, "tropical": 365.242198781}


@pytest.mark.parametrize("setting", ["julian", "common", "tropical"])
def test_year_and_month_follow_the_setting(setting):
    u = reg.make_registry(setting)
    assert u.Quantity(1, "year").to("day").magnitude == pytest.approx(
        DAYS[setting], rel=1e-15
    )
    assert u.Quantity(1, "yr").to("day").magnitude == pytest.approx(
        DAYS[setting], rel=1e-15
    )
    assert u.Quantity(1, "years").to("day").magnitude == pytest.approx(
        DAYS[setting], rel=1e-15
    )
    assert u.Quantity(1, "month").to("day").magnitude == pytest.approx(
        DAYS[setting] / 12, rel=1e-15
    )


@pytest.mark.parametrize("setting", ["julian", "common", "tropical"])
def test_explicit_year_names_never_change(setting):
    u = reg.make_registry(setting)
    assert u.Quantity(1, "julian_year").to("day").magnitude == 365.25
    assert u.Quantity(1, "common_year").to("day").magnitude == 365.0


@pytest.mark.parametrize(
    ("alias", "setting"), [("noleap", "common"), ("udunits", "tropical")]
)
def test_aliases(alias, setting):
    assert reg.normalize_year(alias) == setting
    assert reg.get_registry(alias) is reg.get_registry(setting)


def test_unknown_year_setting_raises():
    with pytest.raises(ValueError, match="year"):
        reg.make_registry("gregorian")


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("julian", "kg ha-1 julian_year-1"),
        ("common", "kg common_year-1 ha-1"),
        ("tropical", "kg ha-1 year-1"),
    ],
)
def test_format_units_writes_explicit_udunits_year_names(setting, expected):
    u = reg.make_registry(setting)
    assert reg.format_units("kg/ha/yr", u) == expected


@pytest.mark.parametrize("setting", ["julian", "common", "tropical"])
def test_written_strings_mean_the_same_to_cf_units(setting):
    u = reg.make_registry(setting)
    written = reg.format_units("kg/ha/yr", u)
    by_pint = u.Quantity(1.0, "kg/ha/yr").to("kg m-2 s-1").magnitude
    by_cf_units = cf_units.Unit(written).convert(1.0, cf_units.Unit("kg m-2 s-1"))
    assert by_pint == pytest.approx(by_cf_units, rel=1e-12)


@pytest.mark.parametrize(
    ("setting", "text", "target"),
    [
        ("tropical", "kg/month", "kg s-1"),
        ("julian", "mmol m-2 d-1", "mol m-2 s-1"),
        ("common", "mmol m-2 d-1", "mol m-2 s-1"),
        ("tropical", "mmol m-2 d-1", "mol m-2 s-1"),
    ],
)
def test_more_written_strings_mean_the_same_to_cf_units(setting, text, target):
    u = reg.make_registry(setting)
    written = reg.format_units(text, u)
    by_pint = u.Quantity(1.0, text).to(target).magnitude
    by_cf_units = cf_units.Unit(written).convert(1.0, cf_units.Unit(target))
    assert by_pint == pytest.approx(by_cf_units, rel=1e-12)


@pytest.mark.parametrize(
    "setting", ["julian", "common", "noleap", "tropical", "udunits"]
)
def test_force_ndarray_like_is_set(setting):
    assert reg.make_registry(setting).force_ndarray_like


def test_foreign_registry_unit_is_refused():
    foreign = pint.UnitRegistry().Unit("kg/ha/year")
    with pytest.raises(ValueError, match="same registry"):
        reg.format_units(foreign, reg.get_registry("tropical"))


@pytest.mark.parametrize("text", ["kyr", "kiloyear", "Myr", "ka"])
def test_prefixed_year_tokens_are_refused(text):
    with pytest.raises(ValueError, match="year"):
        reg.format_units(text)


@pytest.mark.parametrize("text", ["per year", "mg/L as Nx"])
def test_unparseable_string_raises_value_error(text):
    with pytest.raises(ValueError, match="as Nx|per year"):
        reg.format_units(text)


def test_degrees_celsius_written_as_degc():
    assert reg.format_units("degC") == "degC"
    assert reg.format_units("degF") == "degF"


def test_format_units_writes_cf_style_and_micro_is_ascii_u():
    assert reg.format_units("mg/L") == "mg l-1"
    assert reg.format_units("umol/L") == "umol l-1"


def test_format_units_writes_an_angle_as_udunits_degree():
    # pint's cf format prints "deg", which UDUNITS-2 does not know (a source may publish "degree")
    assert reg.format_units("degree") == "degree"
    assert reg.format_units("degree s-1") == "degree s-1"


@pytest.mark.parametrize("setting", ["julian", "common"])
def test_per_month_units_refused_outside_tropical(setting):
    with pytest.raises(ValueError, match="per day"):
        reg.format_units("kg/month", reg.make_registry(setting))


def test_per_month_units_written_under_tropical():
    assert reg.format_units("kg/month", reg.make_registry("tropical")) == "kg month-1"


def test_standalone_a_token_is_refused():
    with pytest.raises(ValueError, match="are"):
        reg.get_registry().Unit("kg ha-1 a-1")


def test_equivalent_is_an_amount():
    u = reg.get_registry()
    assert u.Quantity(1, "meq/L").to("mmol/L").magnitude == 1.0


def test_first_use_leaves_the_callers_application_registry_alone():
    """cf_xarray.units replaces pint's application registry on import; the layer must put the
    caller's back. Needs a fresh interpreter: cf_xarray.units must not be imported yet."""
    code = """
        import sys
        import pint
        assert "cf_xarray.units" not in sys.modules
        mine = pint.UnitRegistry()
        pint.set_application_registry(mine)
        from varwalk import registry
        registry.format_units("kg/ha/yr")
        assert "cf_xarray.units" in sys.modules
        assert pint.get_application_registry().get() is mine
    """
    subprocess.run([sys.executable, "-c", textwrap.dedent(code)], check=True)


def test_cf_xarray_registry_is_left_untouched():
    import cf_xarray.units as cfu

    reg.make_registry("common")
    assert cfu.units.Quantity(1, "yr").to("day").magnitude == 365.25


def test_year_setting_is_recorded():
    assert reg.year_setting(reg.make_registry("noleap")) == "common"


def test_ureg_is_the_default_registry():
    assert reg.ureg is reg.get_registry("julian")


def test_building_a_registry_does_not_log_redefinitions_of_our_names(caplog):
    with caplog.at_level(logging.WARNING, logger="pint.util"):
        reg.make_registry("tropical")
    ours = ("udunits_year", "common_month", "udunits_month", "equivalent")
    assert not [
        r for r in caplog.records if any(name in r.getMessage() for name in ours)
    ]


def test_parse_unit_refuses_a_quantity_even_from_the_same_registry():
    u = reg.get_registry()
    with pytest.raises(ValueError, match="not a Quantity"):
        reg.parse_unit(u.Quantity(1, "m"), u)


@pytest.mark.parametrize("text", ["kg-N/ha", "m + s", "2 m"])
def test_parse_unit_raises_value_error_for_every_unparseable_string(text):
    with pytest.raises(ValueError):
        reg.parse_unit(text, reg.get_registry())


@pytest.mark.parametrize(
    ("text", "reading"),
    [
        ("kyr", "a multiple of the tropical year"),
        ("Myr", "a multiple of the tropical year"),
        ("ka", "a prefixed are"),
    ],
)
def test_prefixed_year_message_names_what_udunits_reads(text, reading):
    with pytest.raises(
        ValueError,
        match=f"'{text}' is a prefixed year, which UDUNITS reads as {reading}",
    ):
        reg.format_units(text)


def test_format_units_writes_the_micro_prefix_in_ascii():
    from varwalk.variables import check_udunits

    assert reg.format_units("ug/L") == "ug l-1"
    assert reg.format_units("μmol/L") == "umol l-1"
    for text in ("ug l-1", "umol l-1"):
        assert check_udunits(text) is not None
