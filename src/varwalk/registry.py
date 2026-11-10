"""The private pint registry: a switchable year, CF-formatted output,
never pint's global.

The registry is a deep copy of ``cf_xarray.units.units`` (the pattern
xclim uses), so it reads UDUNITS strings such as ``kg m-2 s-1`` and
writes CF ones, without altering cf_xarray's own registry. It is
**never** made pint's application registry here; see
:func:`use_as_application_registry`. Importing ``cf_xarray.units`` makes
*cf_xarray's* registry pint's application registry, so
:func:`make_registry` restores the caller's application registry around
that import (when it is the first import). Importing ``cf_xarray.units``
yourself still has cf_xarray's own effect.

**The year is a setting** (docs/units.md section 4): ``julian`` (365.25
d, the default, what USGS software and pint use), ``common`` /
``noleap`` (365 d, what Deltares engines use) and ``tropical`` /
``udunits`` (365.242198781 d, UDUNITS' year). Month is always year / 12.

pint fixes ``year``, ``yr``, ``a`` and ``julian_year`` as aliases when a
registry is built, so redefining ``year`` does nothing. Instead a
preprocessor rewrites incoming ``year``/``yr``/ ``month`` tokens to the
setting's unit, and :func:`format_units` writes them back with explicit
UDUNITS names -- ``julian_year``, ``common_year`` or ``year`` -- so
every CF tool reads the number that was computed. A standalone ``a`` is
refused: pint reads it as a year, UDUNITS as the *are* (100 m2). A unit
prefix on a year (``kyr``, ``ka``, ``Myr``) is refused on input and on
output: UDUNITS reads ``a`` as the are and ``kyr`` as a
kilo-tropical-year, so no string that means the same to every CF tool
can be written for one.
"""

from __future__ import annotations

import copy
import re
import sys
import warnings
from functools import cache
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import pint

__all__ = [
    "format_units",
    "get_registry",
    "make_registry",
    "normalize_year",
    "parse_unit",
    "use_as_application_registry",
    "year_setting",
]

YearSetting = Literal["julian", "common", "tropical"]

_SETTINGS: dict[str, YearSetting] = {
    "julian": "julian",
    "common": "common",
    "noleap": "common",
    "tropical": "tropical",
    "udunits": "tropical",
}
# the registry unit each setting reads `year`/`yr`/`month` as
_YEAR_UNIT = {
    "julian": "julian_year",
    "common": "common_year",
    "tropical": "udunits_year",
}
_MONTH_UNIT = {"julian": "month", "common": "common_month", "tropical": "udunits_month"}

_WORD = r"(?<![A-Za-z_]){}(?![A-Za-z_])"
_YEAR_IN = re.compile(_WORD.format(r"(?:years?|yrs?)"))
_MONTH_IN = re.compile(_WORD.format(r"months?"))
_ARE_OR_YEAR = re.compile(_WORD.format("a"))
_TOKEN = re.compile(r"[A-Za-zµμ_]+")
# a prefixed year: SI prefix + yr/year(s), or kilo/mega/giga-annum
# (`ka`, `Ma`, `Ga`)
_PREFIXED_YEAR = re.compile(
    r"^(?:(?:da|[YZEPTGMkhcmuµμnpfazyd])(?:yr|years?)|[kMG]a"
    r"|(?:deca|hecto|kilo|mega|giga|tera|peta|exa|milli|micro|nano|pico)(?:yr|years?))$"
)
# tokens pint's cf formatter can emit for years and months, and their
# UDUNITS names
_TIME_OUT = re.compile(
    _WORD.format(
        r"(yr|julian_year|common_year|udunits_year|month|common_month|udunits_month)"
    )
)
_WRITTEN = {
    "yr": "julian_year",
    "julian_year": "julian_year",
    "common_year": "common_year",
    "udunits_year": "year",
    "udunits_month": "month",
}


def normalize_year(year: str) -> YearSetting:
    """The canonical year setting for ``year`` (``julian``, ``common``
    or ``tropical``)."""
    try:
        return _SETTINGS[year]
    except KeyError:
        raise ValueError(
            f"unknown year setting {year!r}; choose one of {sorted(_SETTINGS)}"
        ) from None


def _refuse_prefixed_years(text: str) -> None:
    for token in _TOKEN.findall(text):
        if _PREFIXED_YEAR.match(token):
            reading = (
                "a prefixed are (100 m2)"
                if token.endswith("a")
                else "a multiple of the tropical year"
            )
            raise ValueError(
                f"{text!r}: {token!r} is a prefixed year, which UDUNITS reads as "
                f"{reading}, so no string means the same to every CF tool -- multiply "
                "by 365.25 (or the setting's days) and write days instead"
            )


def make_registry(year: str = "julian") -> pint.UnitRegistry:
    """A new private registry with the given year setting. Prefer
    :func:`get_registry`, which builds each setting once."""
    setting = normalize_year(year)
    import pint

    # cf_xarray.units sets pint's application registry on first import;
    # put the caller's back
    first_import = "cf_xarray.units" not in sys.modules
    saved = pint.get_application_registry().get() if first_import else None
    try:
        with warnings.catch_warnings():
            # cf_xarray warns at import when matplotlib is absent;
            # varwalk never plots
            warnings.filterwarnings(
                "ignore",
                message=r"Import\(s\) unavailable to set up matplotlib support",
                category=UserWarning,
            )
            import cf_xarray.units as cfxr_units
    finally:
        if first_import:
            pint.set_application_registry(saved)

    registry = copy.deepcopy(cfxr_units.units)
    registry.define("udunits_year = 365.242198781 * day")
    registry.define("common_month = common_year / 12")
    registry.define("udunits_month = udunits_year / 12")
    registry.define("equivalent = mole = eq")

    year_unit, month_unit = _YEAR_UNIT[setting], _MONTH_UNIT[setting]

    def _time_tokens(text: str) -> str:
        if _ARE_OR_YEAR.search(text):
            raise ValueError(
                f"{text!r}: a standalone 'a' is ambiguous -- pint reads it as a year, "
                "UDUNITS as the are (100 m2); write 'year' or 'are'"
            )
        _refuse_prefixed_years(text)
        return _MONTH_IN.sub(month_unit, _YEAR_IN.sub(year_unit, text))

    registry.preprocessors.insert(0, _time_tokens)
    registry.formatter.default_format = "cf"
    registry._varwalk_year = setting  # pyrefly: ignore[missing-attribute]
    return registry


def get_registry(year: str = "julian") -> pint.UnitRegistry:
    """The shared registry for a year setting, built once. Aliases share
    it (``get_registry("noleap") is get_registry("common")``). Do not
    modify it: every caller sees the change."""
    return _get_registry_cached(year)


@cache
def _get_registry_cached(year: str) -> pint.UnitRegistry:
    """The cached implementation of get_registry."""
    setting = normalize_year(year)
    if setting != year:
        return _get_registry_cached(setting)
    return make_registry(setting)


def year_setting(registry: Any) -> YearSetting:
    """The year setting a registry from this module was built with."""
    try:
        return registry._varwalk_year
    except AttributeError:
        raise ValueError("not a registry from varwalk.registry") from None


def parse_unit(unit: Any, registry: pint.UnitRegistry) -> Any:
    """``unit`` as a Unit of ``registry``. A string is parsed; a pint
    Unit must come from the same registry. A Quantity is refused, even
    from the same registry: it carries a magnitude, and a caller passing
    one where a unit belongs has made a mistake. Raises ``ValueError``
    for an unparsable string (including those pint rejects with a
    ``TypeError``, such as ``kg-N/ha``), a Quantity, or a foreign Unit.
    """
    import pint

    if isinstance(unit, str):
        try:
            return registry.Unit(unit)
        except (pint.errors.PintError, TypeError, AttributeError) as err:
            raise ValueError(
                f"{unit!r} is not a unit this registry can parse: {err}"
            ) from err
    if not isinstance(unit, pint.Unit):
        raise ValueError(
            f"{unit!r} is not a unit: pass a string or a pint Unit, not a "
            f"{type(unit).__name__}"
        )
    if getattr(unit, "_REGISTRY", None) is not registry:
        raise ValueError(
            f"{unit!r} belongs to a different registry, whose year may differ; pass a "
            "string or a Unit from the same registry"
        )
    return unit


_MICRO_PREFIX = re.compile(r"[µμ](?=[A-Za-z])")
_PINT_DEGREE = re.compile(
    r"(?<![A-Za-z])deg(?![A-Za-z])"
)  # pint's cf symbol; UDUNITS says degree


def format_units(unit: Any, registry: pint.UnitRegistry | None = None) -> str:
    """``unit`` (a string or pint Unit) as a CF/UDUNITS string, with
    years written by their explicit UDUNITS name for the registry's
    setting and the micro prefix as ASCII ``u`` (``umol l-1``,
    ``ug l-1``) whichever micro sign went in. Raises ``ValueError`` for
    a per-month unit outside the tropical setting (UDUNITS' month is the
    tropical year / 12), and for any string UDUNITS rejects."""
    from .variables import check_udunits

    registry = registry if registry is not None else get_registry()
    setting = year_setting(registry)
    parsed = parse_unit(unit, registry)
    text = format(parsed, "cf").replace("°C", "degC").replace("°F", "degF")
    text = _MICRO_PREFIX.sub(
        "u", text
    )  # UDUNITS' ASCII micro prefix, never U+03BC / U+00B5
    text = _PINT_DEGREE.sub("degree", text)

    def _swap(match: re.Match[str]) -> str:
        token = match.group(1)
        if token in _WRITTEN:
            return _WRITTEN[token]
        raise ValueError(
            f"{text!r}: a per-month unit has no UDUNITS name under the {setting!r} "
            "year; express it per day, or use rate_to_amount for monthly totals"
        )

    written = _TIME_OUT.sub(_swap, text)
    _refuse_prefixed_years(written)
    if _ARE_OR_YEAR.search(written):
        raise ValueError(f"{written!r}: a standalone 'a' is ambiguous (year or are)")
    if check_udunits(written) is None:
        raise ValueError(f"{written!r} is not a unit UDUNITS-2 accepts")
    return written


def use_as_application_registry(registry: pint.UnitRegistry) -> None:
    """Opt in to making ``registry`` pint's global (application)
    registry. Never called by this package: other libraries (MetPy,
    xclim) also set it, and the last import wins (docs/units.md section
    3)."""
    import pint

    pint.set_application_registry(registry)


def __getattr__(name: str) -> Any:
    if name == "ureg":
        return get_registry()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
