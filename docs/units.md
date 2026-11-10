# Units: pint, CF, QUDT and the length of a year

**Revision 4, 2026-10-19; amended 2026-10-21 and 2026-11-09.** The history of revisions is in [Appendix A](#appendix-a-revision-history).

What we know about units for varwalk's unit conversion, and the decisions it rests on. It covers six questions:

- what CF asks of a unit, and what a unit string cannot say;
- how related packages handle units;
- the traps in pint registries;
- the length of a year;
- how units fit the decomposition of a variable into core concepts, including what a value
  counts: a mass, an amount of substance, or equivalents;
- how the QUDT and ODM2 vocabularies relate to the systems that deliver data.

It is written for data scientists who convert units in this package, and for anyone choosing
a units library or vocabulary for another package.

Researched on 2026-10-05; what a value counts and the local quantity kinds on 2026-10-07.

- **Probes** ran in throwaway `pixi exec` and `uvx` environments with pint 0.26.1, pint-xarray
  0.6.1, pint-pandas 0.8.0, cf_xarray 0.11.3, cfunits 3.3.7, cf-units 3.3.1, MetPy 1.7.1,
  xclim 0.62.0, xarray 2026.9.0 and rdflib.
- **Source code** was read at the commits given in the references.
- **Markers:** [V] verified in source, documentation or a probe; [I] inferred; [U]
  unverified.
- **Citations** are footnotes, numbered in order of first use, with the reference list at the
  end. Web pages and repositories were accessed on 2026-10-05, and the CF standard name table
  and an NADP map PDF on 2026-10-07.

## 1. What CF asks of units, and what a unit string cannot say

The CF Conventions[^cf] put units in a variable's `units` attribute, as a string
UDUNITS-2[^udunits] can parse: `kg m-2 s-1`, `mg l-1`, `umol l-1`.

**A unit string gives dimension and scale, nothing more.** It cannot say five things:

- **The quantity kind.** Mass concentration, density and absolute humidity all share
  kg m⁻³.
- **The substance measured.**
- **The basis it is counted as**, for example nitrate counted as nitrogen.
- **What a mole counts**: moles of the substance, or moles of its charge (equivalents).
  `mmol m-2 d-1` and `meq m-2 d-1` have the same dimension.
- **The medium it is measured in.**

CF folds all five into the standard name instead[^cf-sn] [V]. For example,
`mole_concentration_of_nitrate_in_sea_water` carries the quantity kind
(`mole_concentration_of`), the substance (`nitrate`) and the medium (`in_sea_water`).

- Of the 5,097 names in table version 95, 383 add `_expressed_as_<X>`. Most give a basis: 137
  for carbon, 65 for nitrogen, 9 for phosphorus and 5 for silicon. An example is
  `soil_mass_content_of_inorganic_ammonium_expressed_as_nitrogen`. Seven are
  `_expressed_as_mole_equivalent`, which says what the moles count (section 5).
- There are few inland-water names: 23 contain river, lake or fresh.
- A standard name's canonical units fix only dimension.

**Element symbols in a unit string are read as units** [V]:

| String | Read as |
| --- | --- |
| `g N m-2` (ISIMIP's own unit) | gram · **newton** per m², by pint[^pint] and by both UDUNITS wrappers[^cf-units][^cfunits] |
| `kg-N/ha` (TDep's own unit) | kg · **newton** per ha. Both UDUNITS wrappers call it valid. |
| `mg/L as N` | valid to UDUNITS (atto-second, newton) |
| `mg{N}/L` (UCUM) | parsed by ucumvert[^ucumvert], then the `{N}` is dropped silently |

So quantity kind, substance, basis and medium are stored as metadata beside the unit (section
5). A check that a unit string is valid UDUNITS cannot catch a basis error. Comparing the
unit's dimensions with those of its declared quantity kind can.

## 2. How related packages handle units

| Package | Units approach | What we take |
| --- | --- | --- |
| cf_xarray[^cf-xarray] | A pint registry that parses UDUNITS strings and writes them back (`format="cf"`) [V] | The base of our registry |
| pint-xarray[^pint-xarray] | `quantify`/`dequantify` through the `units` attribute. The registry must have `force_ndarray_like` [V] | How we convert datacubes |
| xclim[^xclim][^xclim-src] (Apache-2.0) | `deepcopy(cf_xarray.units.units)`, extended with a `hydro` context that is switched on only when `standard_name` says the variable is liquid water [V] | Copying the registry rather than editing cf_xarray's; letting metadata decide which context applies. Copied code carries an attribution header. |
| MetPy[^metpy][^metpy-src] (BSD-3) | Adds its definitions to pint's global (application) registry; has its own xarray accessor [V] | Nothing we need: cf_xarray already carries MetPy's string preprocessors |
| HydroMT v1.4.1[^hydromt][^hydromt-adapters] | No pint. Catalogs carry hand-entered `unit_mult`/`unit_add` per variable [V] | The idea of declaring a conversion. Our factors come from pint, not by hand. |
| pywatershed 3.0.0[^pywatershed] | Free-text units in YAML ("inches", "decimal fraction", "Langleys"). A three-entry pint mapping is marked "work in progress" [V] | A warning: a unit vocabulary nobody can check by machine |
| imod-python[^imod] | No unit library. `attrs["units"]` is a plot label only. MODFLOW 6 time units are fixed at `"days"`, and stress-period lengths come from datetime differences [V] | Confirms the approach in section 4: refuse `month` and `year` as time units, and take period lengths from dates |
| xugrid[^xugrid] | No unit handling. `attrs["units"]` is a plot label only, and its pint support is commented out [V] | Nothing to conflict with |
| pyEQL 1.6.5[^pyeql] | Its own registry. Equivalents by replacing `eq` with `mol` in the string, signed by charge, so anions come out negative [V] | Nothing. It is heavy (pymatgen) and PyPI-only. |
| molmass[^molmass] (BSD-3) | Molar mass and charge from a formula: `NH4+` → 18.0379, +1; `PO4-3` → −3 [V] | Molar masses and charges for basis conversion |
| ucumvert 0.3.2[^ucumvert] | Converts UCUM[^ucum] to pint in yet another registry; drops `{…}` annotations [V] | Its definition of `equivalent`, which pint lacks |
| WaterTAP 1.8.0[^watertap] | Pyomo units, pinned `pint<0.25` [V] | Note only: it can't share an environment with pint 0.26 |
| pyet[^pyet], uxarray[^uxarray], climpred[^climpred] | No pint (searched their released wheels) [V] | — |

Details for imod-python:

- It hard-codes `"time_units": "days"` (`imod/mf6/timedis.py:79`).
- It computes stress periods as `timedelta.days + timedelta.seconds/86400.0`
  (`imod/util/time.py:99-121`).
- Reading output, it refuses "month" or "year" because they "do not represent unambiguous
  timedelta values" (`imod/mf6/simulation.py:512`).
- MODFLOW 6's `length_units` is a template slot that no code sets.

**Validators.** SciTools cf-units[^cf-units] (from the Iris project) and NCAS cfunits[^cfunits]
both wrap UDUNITS-2 and parse the same way [V].

- **cf-units** is actively maintained, with conda-forge builds and PyPI wheels for Linux,
  macOS and Windows.
- **cfunits** last released in April 2024, ships no PyPI wheels, and is `noarch` on
  conda-forge, loading the C library through ctypes.

This package uses cf-units.

## 3. Registry traps

1. **pint refuses to combine quantities from different registries** ("Cannot operate with
   Quantity and Quantity of different registries")[^pint] [V].
2. **pint's global registry is whatever was imported last** [V].
   - cf_xarray[^cf-xarray] and xclim[^xclim-src] both call `pint.set_application_registry`
     when they are imported. MetPy[^metpy-src] adds its definitions to whichever registry is
     global at that moment.
   - Importing xclim after MetPy therefore makes `units('dBz')` raise, and quantities created
     before the import can no longer be combined with new ones.
3. **`dequantify()` without a format writes pint's long names** (`kilogram / hectare / year`),
   which are not CF style[^pint-xarray]. Pass `format="cf"`, or set the registry's default
   format [V].
4. **HydroMT keeps the old `units` attribute after converting**[^hydromt-adapters] [V]. A
   converted variable has to have its `units` rewritten, or it lies.

**What this package does about them:**

- It builds a private copy of the registry and passes it explicitly every time.
- It never makes that registry pint's global one when imported. Doing so is opt-in.
- It crosses library boundaries as plain numbers (`q.m_as(...)`).
- It sets the default format to CF and rewrites `units` on every conversion.

## 4. The length of a year

Four kinds of year are in use. Even the tropical year has several published values.

| Name | Days | Seconds | Defined by |
| --- | --- | --- | --- |
| Julian | 365.25 | 31,557,600 | pint `year`/`julian_year`[^pint]; QUDT `unit:YR`[^qudt]; UCUM `a`[^ucum]; UDUNITS `julian_year`[^udunits-xml] |
| Common (no leap) | 365 | 31,536,000 | pint and UDUNITS `common_year`; QUDT `unit:YR_Common`; cftime `noleap`[^cftime] |
| Tropical | 365.242198781 | 31,556,925.9747 | UDUNITS `year` and `yr`[^udunits-xml]; cf-units and cfunits |
| Tropical | 365.24219 | 31,556,925.216 | QUDT `unit:YR_TROPICAL` |
| Tropical | 365.242190402 | 31,556,925.2507 | pint `tropical_year` |
| Actual | 365 or 366 | — | USGS data reports, NADP/TDep annual sums |

All values [V].

**QUDT gets one UDUNITS code wrong** [V]. It gives `unit:YR` (Julian) the `udunitsCode` "yr",
but UDUNITS' `yr` is the tropical year. So QUDT's UDUNITS codes are not used as join keys.

What each organisation actually uses for rates, checked in source:

| Org / package | Year | Evidence | |
| --- | --- | --- | --- |
| USGS EGRET (WRTDS loads) | 365.25 | `unitFactor = 365.25` for kg/yr[^egret][^egret-src] | [V] |
| USGS MODFLOW 6 | 365.25 | `DSECPERYR = 3.1557600e7`, "used in tdis"[^mf6][^mf6-src] | [V] |
| USGS water-data reports | actual days | Annual totals are sums of daily values[^usgs-adr] | [V] |
| USGS Water-Supply Paper 425-C (legacy tables) | 365, ×1.00274 for 366 | "for a year of 365 days … 723.966942 acre-feet"[^wsp425c] | [V] |
| USGS PRMS / pywatershed | 365.242 / 365.25 | Sun-angle maths and stream temperature, not rate conversion[^prms] | [V] |
| Deltares Delft3D / D-Flow FM | 365 | `yearsec = 365.0*24*60*60 !< … (non-leap)`[^delft3d] | [V] |
| Deltares D-Water Quality (DELWAQ) | 365, 30-day months | "years of 365 days assumed"[^delwaq] | [V] |
| Deltares hydromt_wflow | 365 | `precip * area / (86400 * 365)`[^hydromt-wflow] | [V] |
| Deltares HydroMT core | none for rates | Catalogs hold only hourly or daily factors; 365.25 appears only in return-period counting[^hydromt-extremes] | [V] |
| Deltares imod-python | none | Period lengths from datetimes; refuses `month` and `year`[^imod] | [V] |

**CF itself advises against `year` and `month` as units**, because UDUNITS' year is a tropical
year, not a calendar year[^cf-ch4] [V].

**The trap when writing.** In a per-year unit string, `yr` and `year` mean the tropical year to
every UDUNITS tool. A file computed with a Julian year but labelled `kg ha-1 yr-1` is read
2.1 × 10⁻⁵ off.

UDUNITS has explicit names for the other years [V, cf-units probe]:

| String | UDUNITS reads it as |
| --- | --- |
| `kg ha-1 julian_year-1` | 365.25 d per year |
| `kg ha-1 common_year-1` | 365 d per year |
| `kg ha-1 year-1` (and `yr`) | the tropical year |
| `kg ha-1 a-1` | refused: `a` is the *are* (100 m²) |

pint knows `julian_year` and `common_year` as well.

**What this package does:**

- **The year is a setting:**
  - `"julian"` (365.25 d) is the default. It is what USGS software uses, and it matches pint's
    and QUDT's `year`.
  - `"common"` (alias `"noleap"`) is 365 d, for exchanging rates with Deltares engines.
  - `"tropical"` (alias `"udunits"`) is UDUNITS' 365.242198781 d, for exact round-trips with
    UDUNITS-2 tools.
  - Month is always year/12.
- **Per-year units are written with the explicit UDUNITS name of the active year**:
  `julian_year`, `common_year` or `year`. Every CF tool then reads the number that was
  computed, and the unit string shows which year was used. Each conversion also records the
  setting in the result's `history` attribute.
- **The setting affects only rate conversions**, such as `kg m-2 s-1` → `kg ha-1 julian_year-1`.
- **Converting a rate to an amount over a dated period uses that period's actual length**, read
  from the time coordinate and its calendar.
  - This is how USGS computes its own annual totals[^usgs-adr], how xclim's `rate2amount`
    works[^xclim-src], and how imod-python builds MODFLOW stress periods[^imod].
  - For example, a MERRA-2 monthly mean flux times the seconds in that month gives the
    monthly total.
  - TDep and NADP annual values are already calendar-year sums and need no conversion.

## 5. Units within a variable's core concepts

Variable names from different data systems pack several concepts into one name. A USGS
parameter name, for example, combines constituent, matrix, sample attributes, method and
units: "00618: Nitrate, water, filtered, milligrams per liter as nitrogen".

The crosswalk approach of Aufdenkampe *et al.*[^xwalk-doc] decomposes a variable into core
concepts drawn from controlled vocabularies. Its main point is that a variable is the sum of
those parts: "all variable names or parameter names from any data system could be broken down
into terms belonging to different core atomic concept vocabularies", and "[c]onversely any
variable or parameter name could be constructed by concatenating terms from these same core
atomic concept CVs" [V]. It groups the parts under two abstractions from CSDMS Standard
Names, the object type and the quantity type, and places them in two ways [V]:

- **Its draft composition**: "CSN Object Type = ODM2 Medium Type + TaxonomicClassifier(Species)
  + [Fraction]  + [ODM2 SamplingFeatureType] + [O&M Features of Interest Type]" and "CSN
  Quantity Type = QuantityKind (ODM2 UnitsType) + [ODM2 Units] + [ODM2 Speciation] + [CSN
  Process] + [CSN OperationName] + [CSN OperationModifier/Assumptions]". Its section headed
  "CSN Quantity Type = Quantity Kind (ODM2 UnitsType) + [ODM2 Units] + [ODM2 Speciation]"
  defines Speciation as "Speciation of the quantity that is quantified in the numerator of the
  given concentration unit", with the example "Nitrate as mg/L of Nitrogen (or mg of nitrogen
  per L of water)".
- **Its final proposal**: "CSN Object Type = ODM2 Medium Type + TaxonomicClassifier(Species) +
  [ODM2 Speciation] + [ODM2 SamplingFeatureType] + [O&M Features of Interest Type]" and "CSN
  Quantity Type = ODM2 UnitsType + [ODM2 Units]". Speciation has moved to the object type.

The approach builds on CSDMS Standard Names and the ODM2 controlled vocabularies[^odm2].
I-ADOPT[^iadopt] later formalised nearly the same decomposition: Property, ObjectOfInterest,
Matrix, ContextObject, Constraint and StatisticalModifier. I-ADOPT has no slot for a unit or a
basis [V]; a basis fits as a Constraint, or as the numerator entity of a ratio [I].

Units are one concept among several. Converting them correctly needs four of the others:

- **quantity kind**, to know which conversions are meaningful;
- **species**, for molar mass and charge;
- **basis**, to know which mass the number counts;
- **counting**, to know whether the number counts a mass, an amount of substance, or
  equivalents.

**Where the three chemical fields sit.** The lines between the two abstractions are fuzzy,
and the crosswalk document itself places Speciation differently in its draft and its final
proposal. This package reads its three chemical fields this way [I]:

- `species`, the chemical form measured (nitrate, Ca²⁺), sits with the **object type**, as the
  document's TaxonomicClassifier(Species) does in both placements.
- `basis` ("as N") and `counting` (mass, amount or equivalents) sit with the **quantity type**,
  beside the quantity kind and the units. Both say how the number expresses the substance, and
  both are tied to the unit's dimension: a mass needs a molar mass to become an amount, and
  equivalents need the species' charge. ODM2's Speciation terms are each defined as "Expressed
  as …" (section 7), which is what `basis` holds, so `basis` follows the draft composition's
  placement of Speciation, and `counting` sits beside it.

**Fraction.** The draft composition's "[Fraction]" has no field in this package yet. The
crosswalk document also lists it, in its later section, among the "CSN Object Modifiers" as
"Fraction (i.e. within USGS “Limited methodology”?)", "Presently handled in ODM2 as
relationships between Sampling Features", with the examples "Size fraction: i.e.
filtered/dissolved, 63-2000 µm (sand sized)" and "Extract: i.e. acid soluble, semi-volatile,
total lipid extract" [V].[^xwalk-doc] USGS's "00618: Nitrate, water, filtered" carries one in
its name ("filtered"), and MERRA-2's dust and sea salt deposition comes in five bins of dry
particle radius [I], whose sum is the group's total [I]. A fraction is part of what a value is a
quantity of, like `species` and `medium`, and not part of its unit [I]. MERRA-2's bins are the
tidy case; a fraction is in general defined by what a lab can separate, so fractions can nest
or overlap rather than sum to a whole, and the quantity of interest is often a difference
between two of them, such as particulate as unfiltered minus filtered [I]. The fields that would carry it are future work.

Whatever the placement, a variable is composed of all the parts under both abstractions. That
is why this package carries them as separate fields, and never parses them from a variable name
or a unit string.

How each concept appears across the vocabularies and systems involved:

| Concept | Data-dictionary field | CF | QUDT (current) | I-ADOPT | ODM2 2.0 | ODM2.1 draft | UDUNITS / pint | NERC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Medium | `medium` | `_in_sea_water` etc. in the standard name | — | Matrix | Results.SampledMediumCV | Variables.SampledMediumCV | — | S26 |
| Fraction | none yet (future work) | not checked [U] | not checked [U] | Constraint [I] | relationships between sampling features, per the crosswalk document [V]; not checked in the ODM2 schema [U] | not checked [U] | — | not checked [U] |
| Species | `species` | substance term in the standard name | — | ObjectOfInterest | Results.TaxonomicClassifierID | Variables.TaxonomicClassifierID | — (molmass) | S27 (→ ChEBI) |
| Speciation (basis) | `basis` | `_expressed_as_<X>` | only 4 ad hoc ContextualUnits (`GM_Nitrogen`, …) | Constraint [I] | Variables.SpeciationCV | Variables.SpeciationID → TaxonomicClassifiers | none (`g N` is gram·newton) | P01 label text only |
| Counting | `counting` | `_expressed_as_mole_equivalent` | `EquivalentConcentration`, `MolarEquivalent` and `ReactiveChargePerMass`, with their specializations, only | Constraint [I] | not checked [U] | 2018 workbook: equivalents as electric charge (section 7) | none: UDUNITS and pint have no `eq` | not checked [U] |
| Quantity kind | `quantity_kind` | quantity term (`mass_concentration_of`, `_flux`) | `quantitykind:*` | Property | Units.UnitsTypeCV | Variables.QuantityKindCV | — | S06 |
| Dimension | `dimension_vector` | canonical units | `hasDimensionVector` | — | — | CV_QuantityKind dimension columns | unit algebra / `.dimensionality` | P24 |
| Units | `units`, `units_iri` | `units` attribute | `unit:*`, `ucumCode` | — | Units.UnitsAbbreviation, UnitsLink | CV_Units | parser and converter | P06 (`owl:sameAs` QUDT) |
| Statistic | (outside this layer) | `cell_methods` | — | StatisticalModifier | AggregationStatisticCV | same | — | S07 |

Sources for the table: CF[^cf-sn], QUDT[^qudt], I-ADOPT[^iadopt], ODM2 2.0[^odm2-schema], the
ODM2.1 draft[^odm2-1-dev] and NERC[^nerc-nvs].

**What a mole counts.** A unit and a quantity kind both carry dimension, so they tell a mass
from an amount of substance, but not moles of a substance from moles of its charge:

- **CF qualifies a name; it defines no quantity.** Its seven `_expressed_as_mole_equivalent`
  names, all for sea-water alkalinity, have canonical units in mol: `mol m-3` for the
  concentration, `mol kg-1` per unit mass, `mol m-3 s-1` for a tendency and `mol m-2 s-1` for a
  depth-integrated tendency[^cf-sn] [V]. So CF writes equivalents in moles in any dimension,
  and says in the name that the moles are equivalents.
- **QUDT has three equivalents kinds and two specializations of them**:
  `EquivalentConcentration` (`A1E0L-3I0M0H0T0D0`, units `MilliEQ-PER-L` and seven others),
  `MolarEquivalent` (`A1E0L0I0M0H0T0D0`, units `EQ`, `MilliEQ`, `MicroEQ`, `NanoEQ`) and
  `ReactiveChargePerMass` (`A1E0L0I0M-1H0T0D0`, unit `MilliEQ-PER-HectoGM`, 0.01 mol/kg);
  `ReactiveCharge` specializes `MolarEquivalent`, and `CationExchangeCapacity` specializes
  `ReactiveChargePerMass`, neither with a unit of its own[^qudt] [V]. It has none for a flux
  or an amount per area.
- **The deposition sources publish equivalents per area.** NADP's TDep base cations `bc_*` and
  its `ns_tw`, "the equivalent N plus S total", are in keq/ha [I]. NTN's `SplusN_dep` gradient
  grid is in eq/ha, as the legend of NADP's map PDF for it prints[^ntn-map-legend] [V]; the
  GeoTIFF itself carries no unit [I].
- Lakes and models use equivalent concentrations and fluxes alike (alkalinity in µeq/L, a base
  cation flux in meq m⁻² d⁻¹) [I].

So what a value counts is a concept of its own, independent of dimension, as CF's qualifier is
independent of its name's quantity.

**What this package does:**

- **The data dictionary carries these concepts as separate fields.** For tables that means
  `variables_df` columns; for datacubes, variable attributes. They are never parsed from a
  unit string or a name.
  A caller fills them from curated annotation tables (`annotate.read_table`); converting units
  or basis is a separate, later step.

  | Field | Required | Example | Vocabulary |
  | --- | --- | --- | --- |
  | `units` | yes | `mg l-1` | UDUNITS/CF string, validated by cf-units |
  | `quantity_kind` | **yes, for every variable** | `MassConcentration` | current QUDT quantity-kind local name, whose IRI is the namespace plus this name; or a local kind (section 6), which has no IRI |
  | `counting` | **yes, wherever `species` is set** | `equivalents` | `mass`, `amount` or `equivalents` |
  | `dimension_vector` | computed | `A0E0L-3I0M1H0T0D0` | QUDT notation, computed by pint and checked against `quantity_kind` |
  | `units_iri` | where curated | `unit:MilliGM-PER-L` | current QUDT |
  | `species` | where chemical | `NO3-` | formula with charge, readable by molmass |
  | `basis` | where chemical | `N` | chemical formula readable by molmass, usually an element |
  | `medium` | where known | `liquidAqueous` | ODM2 Medium CV |
  | `standard_name` | where one exists | | CF |

- **A conversion refuses what its metadata cannot support.** For example, it won't convert a
  mass concentration into a density, or convert an ion to an element without `species` and
  `basis`.
- **`species` and `basis` are both chemical formulas that molmass reads**, so each has a molar
  mass, and `species` also has a charge. The basis decides which molar mass turns an amount
  into a mass. For example, 100 µmol/L of nitrate is 1.40 mg/L as N (nitrogen, 14.007 g/mol)
  but 6.20 mg/L as NO3⁻ (nitrate, 62.00 g/mol).
- **`counting` says what the value counts, and is never guessed.**
  - `mass` counts grams of the basis; the unit has mass and no amount of substance.
  - `amount` counts moles of the basis; `equivalents` counts moles of charge, |charge| per mole
    of the species, so it needs a charged species. Both need a unit in mol.
  - A dimensionless unit is judged by its numerator: mg/kg as N counts a mass (`MassFraction`),
    µmol/mol an amount or equivalents (`MoleFraction`). Only a numerator holding neither (`1`,
    `percent`) falls back to the quantity kind's. No function here turns mg/kg into mmol/mol:
    that needs the molar masses of both the substance and its matrix.
  - It is required wherever `species` is set, with no default, so a value in moles is never
    read as an amount when it is equivalents. An equivalents kind on input (`EQUIVALENT_KINDS`:
    the QUDT kinds above, with their specializations) implies `equivalents`. A `counting`
    outside the three, or a different one beside an equivalents kind, is refused by every
    function that reads it, so a value written by hand is checked, not trusted.
- **Equivalents are written in moles**, as CF writes them: `meq m-2 d-1` is stored as
  `mmol d-1 m-2` with `counting` `equivalents`, because UDUNITS has no `eq`. The layer defines
  `eq` = `mol` for reading targets, which neither pint nor UDUNITS has. `convert_amount` writes
  the dimensional quantity kind (`AmountOfSubstanceConcentration`, `MolarFluxDensity`,
  `AmountOfSubstancePerArea`, `AmountOfSubstancePerMass` for a cation exchange capacity) with
  the `counting` it converts to, one form for every dimension.
- **Equivalents convert in any dimension.** Amount ↔ equivalents changes only `counting`, never
  the quantity kind: 1 mmol m⁻² d⁻¹ of Ca²⁺ is 2 meq m⁻² d⁻¹, both `MolarFluxDensity`.
  Rescaling within one counting keeps it.

## 6. QUDT

QUDT[^qudt] (Quantities, Units, Dimensions and Types) is the vocabulary of quantity kinds and
units this package draws on. The latest release is v3.5.2 (2026-09-22), licensed CC BY 4.0,
with attribution to QUDT.org [V].

### The model

- **Units:** a `qudt:Unit` links to its quantity kinds through `qudt:unitForQuantityKind`
  [V]. Every one of the 2,936 units has `hasDimensionVector` and `conversionMultiplier`
  (relative to the SI coherent unit). `conversionOffset` is stated only where it is non-zero
  (`DEG_C`: 273.15).
- **Codes:** 2,434 units carry a `ucumCode`, and only 97 a `udunitsCode` (see section 4 for
  one that is wrong).
- **Not convertible:** a `conversionMultiplier` of 0.0 marks a unit that cannot be converted
  (NTU, PSU, OSM), not a factor of zero.
- **Quantity kinds:** 1,225 of them, related by `qudt:specializationOf`. For example,
  `MassConcentration` is a specialisation of `Density`, and `MassFluxDensity` of
  `MassPerAreaTime`. Seventy-seven carry `qkdvNumerator`/`qkdvDenominator`, which separate
  ratios with identical overall dimensions: `MassFraction` is M/M, `VolumetricFlux` is
  L³T⁻¹/L².
- **Dimension vectors:** written `A{n}E{n}L{n}I{n}M{n}H{n}T{n}D{n}`[^qudt-changelog] [V].

  | Letter | Dimension | pint |
  | --- | --- | --- |
  | A | amount of substance | `[substance]` |
  | E | electric current | `[current]` |
  | L | length | `[length]` |
  | I | luminous intensity | `[luminosity]` |
  | M | mass | `[mass]` |
  | H | thermodynamic temperature | `[temperature]` |
  | T | time | `[time]` |
  | D | 1 if every other exponent is 0, else 0 | — |

  - Computing a QUDT dimension vector from a pint unit is exact. For example, `uS/cm` gives
    `A0E2L-3I0M-1H0T3D0`, as QUDT has for `unit:MicroS-PER-CentiM` [V].
  - The exponents are read from the vector's name, because QUDT almost never states them as
    separate triples.
- **No species or basis concept** in the quantity kinds [V]. Four `ContextualUnit`s
  (`GM_Carbon`, `GM_Nitrogen` and their per-m²-per-day forms) encode a basis ad hoc, and this
  package does not model basis that way.

**Quantity kinds share dimension vectors**, so a unit cannot determine its quantity kind [V]:

| Dimension vector | Quantity kinds that share it |
| --- | --- |
| `A0E0L-3I0M1H0T0D0` | `Density`, `MassDensity`, `MassConcentration`, `MassConcentrationOfWater`, `AbsoluteHumidity`, … |
| `A0E0L-2I0M1H0T-1D0` | `MassPerAreaTime`, `MassFluxDensity`, and several acoustic impedances |
| `A1E0L-3I0M0H0T0D0` | `Concentration`, `AmountOfSubstanceConcentration`, `EquivalentConcentration`, `IonConcentration`, … |

**Matching a unit to a QUDT unit IRI** by dimension vector and multiplier is ambiguous [V].
`mg/L` matches `GM-PER-M3`, `MicroGM-PER-MilliL`, `MilliGM-PER-L` and `NanoGM-PER-MicroL`; `mol
m-3` also matches `MilliEQ-PER-L`. A match is settled by the variable's quantity kind and a
preferred unit, and checked against the offset. UCUM codes match almost one to one, but pint
cannot write UCUM.

Terms relevant to deposition and water quality, all [V]:

| Quantity kind | Example units (multiplier) |
| --- | --- |
| `MassConcentration` | `MilliGM-PER-L` (1e-3), `MicroGM-PER-L` (1e-6) |
| `AmountOfSubstanceConcentration` | none of its own; `MilliMOL-PER-L` (1) and `MicroMOL-PER-L` (1e-3) are filed under its parent `Concentration` |
| `EquivalentConcentration` | `MilliEQ-PER-L` (1), `MicroEQ-PER-L` (1e-3) |
| `MassPerAreaTime` / `MassFluxDensity` | `KiloGM-PER-M2-SEC` (1), `KiloGM-PER-HA-YR` (3.1688e-12) |
| `MassPerArea` | `KiloGM-PER-HA` (1e-4) |
| `Depth` (a `Length`) | `MilliM` |
| `ElectrolyticConductivity` | `MicroS-PER-CentiM` |

QUDT has no quantity kind for precipitation or deposition. It files `MilliM-PER-DAY` under
velocity.

### QUDT 1.x and current QUDT

Vocabularies built around 2014–2016, including the ODM2 controlled vocabularies, cite QUDT 1.x
[V]. Since then:

- **The IRIs changed.** `http://qudt.org/vocab/unit#MilligramPerLiter` became
  `http://qudt.org/vocab/unit/MilliGM-PER-L`. The `quantity#` namespace became `quantitykind/`,
  and the schema moved to `http://qudt.org/schema/qudt/`.
- **Old IRIs no longer resolve to their terms.** Unit IRIs redirect to the whole vocabulary,
  and quantity IRIs return 404.
- **QUDT publishes no mapping from old IRIs to new.** The request has been open since 2019[^qudt-19].
- **What was added:** dimension-vector IRIs; numerator and denominator vectors;
  specialisation between quantity kinds; contextual units; UCUM, UDUNITS, UNECE and IEC codes;
  and deprecation with `isReplacedBy`.

Matching old terms to current ones by label works for most of them [V]. Of the 740 QUDT 1.x
unit links in the 2018 ODM2.1 draft workbook (section 7):

- 631 map uniquely (`KilogramPerCubicMeter` → `KiloGM-PER-M3`, `DegreeCelsius` → `DEG_C`);
- 6 are ambiguous;
- 103 do not match, mostly BTU and abvolt variants.

Of its 153 QUDT-sourced quantity kinds, 132 map by name. The rest need review: for example,
`AmountOfSubstancePerUnitVolume` is today `AmountOfSubstanceConcentration`.

### What this package does

- **It ships a pre-extracted QUDT subset:** about 2,900 units and 1,200 quantity kinds, as
  versioned Parquet with a CSV copy.
  - It is built from the v3.5.2 release with rdflib. rdflib is needed only to rebuild the
    subset, not at runtime.
  - The release, its date and the CC BY 4.0 attribution travel with the files.
  - Parsing the three Turtle files the subset is built from takes about a second: units
    3.2 MB, quantity kinds 1.2 MB, dimension vectors 0.1 MB [V].
- **Current QUDT is the vocabulary for `quantity_kind` and `units_iri`.**
- **Local quantity kinds name quantities QUDT has no kind for.** A small curated vocabulary
  ships beside the subset, with the QUDT kinds' columns plus a definition. Today it holds two
  kinds: `AmountOfSubstancePerArea` (`A1E0L-2I0M0H0T0D0`), for amounts and equivalents per area
  such as keq/ha and mmol m⁻², and `DirectionalVarianceSpectralDensity` (`A0E0L2I0M0H0T1D0`),
  for a wave spectrum per frequency and direction (WIS's `directionalWaveEnergyDensity`, in
  m2 s rad-1; CF `sea_surface_wave_directional_variance_spectral_density`).
  - No QUDT 3.5.2 quantity kind has `AmountOfSubstancePerArea`'s dimension vector [V]. Four
    QUDT units do (`MOL-PER-M2`, `MilliMOL-PER-M2`, `MicroMOL-PER-M2` and the Dobson unit
    `DU`), and QUDT files all four under the kind `Unknown` [V]. So a `units_iri` on a
    local kind is matched by dimension vector, not by a kind QUDT cannot list.
  - `DirectionalVarianceSpectralDensity` shares its vector with a QUDT kind: `AreaTime` is the
    only QUDT 3.5.2 kind with `A0E0L2I0M0H0T1D0` [V] (the shipped subset's
    `data/qudt/quantity_kinds.csv`, read 2026-10-21), and it is a different quantity.
    The local kind lists `AreaTime` in `specialization_of`, and the vocabulary test accepts a
    shared vector only with that statement.
  - Lookups search QUDT first, then the local kinds. A local kind has no QUDT IRI, and a local name that QUDT also defines stops the vocabulary loading, so a
    QUDT release that adds the kind is noticed.
- **A `units_iri` on a value counted as equivalents is one of QUDT's equivalents units**, with
  the variable's dimension vector: `MilliEQ-PER-L` describes `mmol l-1` of
  `AmountOfSubstanceConcentration` counted as equivalents, and `MilliMOL-PER-L` does not. (As an
  amount, `MilliMOL-PER-L` fits: the check walks a kind's parents, and QUDT files it under
  `Concentration`, the parent of that kind.) A flux counted as equivalents has no QUDT unit IRI.
- **Conversion factors come from pint.** QUDT multipliers are used to cross-check them, never
  to replace them.

## 7. ODM2

ODM2[^odm2] (Observations Data Model 2) is an information model for observation databases.

**ODM2 2.0** is the official schema; v2.0.1 (2020-03-18) is the last release[^odm2-schema] [V].
In it:

- `Variables` carries `VariableTypeCV`, `VariableCode`, `VariableNameCV`, `SpeciationCV` and
  `NoDataValue`.
- `Units` carries `UnitsTypeCV`, `UnitsAbbreviation`, `UnitsName` and `UnitsLink`.
- `Results` carries `UnitsID`, `TaxonomicClassifierID` and `SampledMediumCV`.

**ODM2 2.1 exists only as the unreleased `ODM2.1_dev` branch** (last commit
2022-03-04)[^odm2-1-dev] [V]. Its changes:

- `Variables` gains `SampledMediumCV`, `TaxonomicClassifierID`, `SpeciationID` and
  `QuantityKindCV`.
- `SpeciationID` is a foreign key into the same `TaxonomicClassifiers` table as the species. So
  the measured species and its basis come from one chemical-entity vocabulary, the model used
  in section 5.
- `UnitsType` is renamed `QuantityKind`.
- A `CV_Units` table holds conversion multipliers and offsets.

**The ODM2 controlled vocabularies** are served at vocabulary.odm2.org[^odm2-cv], as JSON
(`/api/v1/<cv>/?format=json`) or SKOS [V].

- The service is live but unreliable: the units endpoint returned HTTP 500. Vocabularies are
  fetched and cached, never called at runtime.
- **Speciation** has 145 terms, each defined as "Expressed as …": N, P, NO3, NH4, PO4, SiO2,
  CaCO3, HCO3, and others.
  - Its terms carry no charge (`NH4`, not `NH4+`), and some are not chemical formulas at all
    (`TA`, `EC`, `pH`, `deltaN15`). So they are not the vocabulary for `species` or `basis`,
    which need a molar mass and a charge.
  - The scheme's own description is a copy-paste error ("type of SpatialOffset").
- **UnitsType** has 180 terms. Some merge what current QUDT separates:
  `concentrationOrDensityMassPerVolume` covers both `MassConcentration` and `Density`. The
  terms' provenance links point to QUDT 1.x.

**The 2018 ODM2.1 draft workbook**[^odm2-1-sheet] holds the controlled vocabularies, as
downloaded on 2018-08-30, for loading into a blank ODM2.1 database. It is background to this
package, not a source for it [V]:

- **Its quantity kinds** carry dimension exponents in letters of their own: U unitless,
  N amount, Θ, J.
- **Some QUDT 1.x links are mismatched.** `count` is linked to amount of substance, whereas
  QUDT's `Count` is dimensionless.
- **It treats equivalents as electric charge**, scaled by the Faraday constant (96485.3365), not
  as an amount.
- **About 13% of its conversion multipliers disagree with current QUDT** (76 of 575
  comparable units), some by a factor of 10⁶ or more:

  | Unit | Workbook | Current QUDT |
  | --- | --- | --- |
  | µg/L | 1e-3 | 1e-6 |
  | ng/L | 1e-6 | 1e-9 |
  | g/m³ | 1000 | 1e-3 |
  | mol/L | 1e-3 | 1000 |
  | µmol/L | 1e-9 | 1e-3 |
  | nmol/L | 1e7 | 1e-6 |
  | mL/L | 1000 | 1e-3 |

**What this package does:**

- **It uses current QUDT terms, not ODM2 terms, for quantity kind and units.**
- **`species` and `basis` are molmass formulas, not ODM2 Speciation terms.**
- **It never imports the 2018 workbook's numbers.**
- **Exporting a data dictionary to ODM2 terms is left for future work.**

## Appendix A: Revision history

Each revision is a full review of the document, so the sections above state only the current
understanding.

| Revision | Date | Changes |
| --- | --- | --- |
| 1 | 2026-10-05 | First version: CF and unit strings, a survey of unit handling in related packages, registry traps, and the length of a year in USGS and Deltares practice. |
| 2 | 2026-10-05 | Added imod-python and xugrid to the survey. Added the QUDT, pint and UDUNITS values of the year, and the rule of writing per-year units with explicit UDUNITS names. Added sections 5 (units within a variable's core concepts, with a crosswalk across CF, QUDT, ODM2, UDUNITS, pint, I-ADOPT and NERC), 6 (QUDT: model, dimension vectors, 1.x versus current, the shipped subset) and 7 (ODM2 2.0, the 2.1 draft and its 2018 workbook). Corrected the citation for `_expressed_as_` names (the CF standard name table, not CF chapter 4). Set `species` and `basis` as molmass formulas. Footnotes use descriptive labels. |
| 3 | 2026-10-07 | Added what a value counts (`counting`: mass, amount or equivalents) as a concept of its own, in section 1's list, the section 5 crosswalk table and field table, with CF's `_expressed_as_mole_equivalent` names and their units, QUDT's equivalents kinds, and the deposition sources' equivalents per area. Quoted the crosswalk document's draft composition and final proposal, stated its main point, and placed `species` with the object type and `basis` and `counting` with the quantity type. Added the local quantity kinds to section 6 (`AmountOfSubstancePerArea`, with the four QUDT units filed under `Unknown`) and how a `units_iri` fits a value counted as equivalents. Widened `mass` to admit mass fractions (`MassFraction`, mg/kg as N). Cited NTN's `SplusN_dep` unit (eq/ha) to the legend of NADP's map PDF [V]. Equivalents now convert in any dimension, not only as a concentration. Admitted `MoleFraction` for `amount` and `equivalents`. Listed all three of QUDT's equivalents kinds (`EquivalentConcentration`, `MolarEquivalent`, `ReactiveChargePerMass`) and their two specializations (`ReactiveCharge`, `CationExchangeCapacity`), where an earlier draft of this revision named two kinds [V]. A dimensionless unit is now judged by its numerator, not the kind's, and a `counting` written by hand is checked by every function that reads it. |
| 4 | 2026-10-19 | Added Fraction (by size or by extraction), a part of the crosswalk document's draft composition with no field here yet, in section 5's text and crosswalk table, with MERRA-2's size bins as the first case; the fields are future work. |
| 4, amended | 2026-10-21 | Amendment, not a new revision or a full review: the rest is as of revision 4. Section 5 says the annotation fields are filled from curated tables, with conversion a separate, later step. Section 6 adds the second local quantity kind, `DirectionalVarianceSpectralDensity`, for WIS's directional wave spectrum, and the check that `AreaTime` is the only QUDT kind with its dimension vector [V]. |
| 4, amended | 2026-11-09 | Amendment, not a new revision or a full review: the rest is as of revision 4. Moved with the units layer into varwalk. Internal references were reworded neutrally: the deposition guide's citations became [I] where the guide was the only source (the TDep unit and MERRA-2's bins), and two internal links (the crosswalk document, the ODM2.1 workbook) were dropped, keeping their citations. |

## References

<!-- Footnote definitions, in order of first use. -->

[^cf]: Eaton, B. et al. *NetCDF Climate and Forecast (CF) Metadata Conventions*, version 1.11 (2023). <https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html>
[^udunits]: Unidata. *UDUNITS-2*. UCAR/NSF Unidata Program Center. <https://docs.unidata.ucar.edu/udunits/current/>
[^cf-sn]: CF Standard Name Table, version 95 (2026-09-16). <https://cfconventions.org/Data/cf-standard-names/current/build/cf-standard-name-table.html>
[^pint]: Grecco, H. E. et al. *Pint: makes units easy*, version 0.26.1. <https://pint.readthedocs.io/en/stable/>; source <https://github.com/hgrecco/pint>
[^cf-units]: SciTools. *cf-units*, version 3.3.1. <https://github.com/SciTools/cf-units>; documentation <https://cf-units.readthedocs.io/>
[^cfunits]: NCAS-CMS. *cfunits*, version 3.3.7. <https://github.com/NCAS-CMS/cfunits>
[^ucumvert]: ucumvert, version 0.3.2. <https://github.com/dalito/ucumvert>
[^cf-xarray]: cf_xarray, version 0.11.3, `cf_xarray/units.py`. <https://github.com/xarray-contrib/cf-xarray/blob/main/cf_xarray/units.py>
[^pint-xarray]: pint-xarray, version 0.6.1. <https://pint-xarray.readthedocs.io/>; source <https://github.com/xarray-contrib/pint-xarray>
[^xclim]: Bourgault, P. et al. xclim: xarray-based climate data analytics. *J. Open Source Softw.* **8**, 5415 (2023). <https://doi.org/10.21105/joss.05415>
[^xclim-src]: xclim, version 0.62.0, `src/xclim/core/units.py`. <https://github.com/Ouranosinc/xclim/blob/main/src/xclim/core/units.py>
[^metpy]: May, R. M. et al. MetPy: a meteorological Python library for data analysis and visualization. *Bull. Am. Meteorol. Soc.* **103**, E2273–E2284 (2022). <https://doi.org/10.1175/BAMS-D-21-0125.1>
[^metpy-src]: MetPy, version 1.7.1, `src/metpy/units.py`. <https://github.com/Unidata/MetPy/blob/main/src/metpy/units.py>
[^hydromt]: Eilander, D. et al. HydroMT: automated and reproducible model building and analysis. *J. Open Source Softw.* **8**, 4897 (2023). <https://doi.org/10.21105/joss.04897>
[^hydromt-adapters]: HydroMT, version 1.4.1, `hydromt/data_catalog/adapters/` (`_apply_unit_conversion`). <https://github.com/Deltares/hydromt>
[^pywatershed]: pywatershed, version 3.0.0 (U.S. Geological Survey), `pywatershed/base/meta.py` and `pywatershed/static/metadata/`. <https://github.com/EC-USGS/pywatershed>
[^imod]: imod-python (Deltares), commit 85c6f14: `imod/mf6/timedis.py` line 79, `imod/util/time.py` lines 99–121, `imod/mf6/simulation.py` line 512, `imod/visualize/spatial.py` line 198, `imod/templates/mf6/gwf-dis.j2` line 2. <https://github.com/Deltares/imod-python>
[^xugrid]: xugrid (Deltares), commit e34e459: `xugrid/plot/utils.py` lines 401–412, `xugrid/ugrid/conventions.py` lines 59–100. <https://github.com/Deltares/xugrid>
[^pyeql]: pyEQL, version 1.6.5, `src/pyEQL/solution.py`. <https://github.com/KingsburyLab/pyEQL>
[^molmass]: Gohlke, C. *molmass*, version 2026.8.15. <https://github.com/cgohlke/molmass>
[^ucum]: Schadow, G. & McDonald, C. J. *The Unified Code for Units of Measure* (UCUM). Regenstrief Institute. <https://ucum.org/ucum>
[^watertap]: WaterTAP, version 1.8.0. <https://github.com/watertap-org/watertap>
[^pyet]: pyet, version 1.5.0. <https://github.com/pyet-org/pyet>
[^uxarray]: uxarray, version 2026.9.1. <https://github.com/UXARRAY/uxarray>
[^climpred]: climpred, version 2.6.0. <https://github.com/pangeo-data/climpred>
[^qudt]: QUDT.org. *Quantities, Units, Dimensions and Types (QUDT)*, release v3.5.2 (2026-09-22), CC BY 4.0. <https://qudt.org>; source <https://github.com/qudt/qudt-public-repo> (commit 9a2f71f): `src/main/rdf/schema/SCHEMA_QUDT.ttl`, `src/main/rdf/vocab/unit/VOCAB_QUDT-UNITS-ALL.ttl`, `src/main/rdf/vocab/quantitykinds/VOCAB_QUDT-QUANTITY-KINDS-ALL.ttl`, `src/main/rdf/vocab/dimensionvectors/VOCAB_QUDT-DIMENSION-VECTORS.ttl`
[^udunits-xml]: UDUNITS-2, `lib/udunits2-common.xml` (`year`, `tropical_year`, `common_year`, `julian_year`). <https://github.com/Unidata/UDUNITS-2/blob/master/lib/udunits2-common.xml>
[^cftime]: cftime, `src/cftime/_cftime.pyx` (`year_units`, allowed only for the `365_day`/`noleap` calendars). <https://github.com/Unidata/cftime>
[^egret]: Hirsch, R. M. & De Cicco, L. A. *User guide to Exploration and Graphics for RivEr Trends (EGRET) and dataRetrieval: R packages for hydrologic data*, version 2.0. U.S. Geological Survey Techniques and Methods 4-A10 (2015). <https://doi.org/10.3133/tm4A10>
[^egret-src]: EGRET, commit b5eb22c, `R/objectDefinitions.R`, line 182. <https://github.com/DOI-USGS/EGRET/blob/b5eb22c/R/objectDefinitions.R#L182>
[^mf6]: Langevin, C. D. et al. *Documentation for the MODFLOW 6 Groundwater Flow Model*. U.S. Geological Survey Techniques and Methods 6-A55 (2017). <https://doi.org/10.3133/tm6A55>
[^mf6-src]: MODFLOW 6, commit 7455d83, `src/Utilities/Constants.f90`, lines 99–101. <https://github.com/MODFLOW-ORG/modflow6/blob/7455d83/src/Utilities/Constants.f90#L99-L101>
[^usgs-adr]: U.S. Geological Survey. *Definition of terms used in annual water-data reports* (2005). <https://water.usgs.gov/ADR_Defs_2005.pdf>
[^wsp425c]: U.S. Geological Survey Water-Supply Paper 425-C (hydraulic conversion tables). <https://pubs.usgs.gov/wsp/0425c/report.pdf>
[^prms]: PRMS 5.2.1 as shipped in pywatershed, commit b3b6d0c, `prms_src/prms5.2.1/prms/prms_constants.f90`, lines 22–24. <https://github.com/EC-USGS/pywatershed/blob/b3b6d0c/prms_src/prms5.2.1/prms/prms_constants.f90#L22-L24>
[^delft3d]: Delft3D, commit 38d26033e6, `src/utils_lgpl/deltares_common/packages/deltares_common/src/mathconsts.f90`, line 68. <https://github.com/Deltares/Delft3D/blob/38d26033e6/src/utils_lgpl/deltares_common/packages/deltares_common/src/mathconsts.f90#L68>
[^delwaq]: Delft3D (D-Water Quality), commit 38d26033e6, `src/engines_gpl/waq/waq_utils_f/date_time_utils.f90`, line 157. <https://github.com/Deltares/Delft3D/blob/38d26033e6/src/engines_gpl/waq/waq_utils_f/date_time_utils.f90#L157>
[^hydromt-wflow]: hydromt_wflow, commit 93be348, `hydromt_wflow/workflows/river.py`, line 608. <https://github.com/Deltares/hydromt_wflow/blob/93be348/hydromt_wflow/workflows/river.py#L608>
[^hydromt-extremes]: HydroMT, commit 53aa0af, `hydromt/stats/extremes.py`, lines 26 and 152. <https://github.com/Deltares/hydromt/blob/53aa0af/hydromt/stats/extremes.py#L26>
[^cf-ch4]: CF Conventions, chapter 4 "Coordinate Types", § Time Coordinate (the advice against `year` and `month`). <https://github.com/cf-convention/cf-conventions/blob/main/ch04.adoc>
[^xwalk-doc]: Aufdenkampe, A. (with input from many). *An Approach to Cross-Walking Environmental Variable Names based on concatenating core concepts from Observation Data Model 2 Vocabularies*. First drafted May 2016, with minor revisions since.
[^odm2]: Horsburgh, J. S. et al. Observations Data Model 2: a community information model for spatially discrete Earth observations. *Environ. Model. Softw.* **79**, 55–74 (2016). <https://doi.org/10.1016/j.envsoft.2016.01.010>
[^iadopt]: I-ADOPT ontology, version 1.1.0 (Research Data Alliance I-ADOPT Working Group), CC BY 4.0. <https://w3id.org/iadopt/ont/1.1.0>; source <https://github.com/i-adopt/ontology>
[^odm2-schema]: ODM2, release v2.0.1 (2020-03-18), commit a474e20: `src/blank_schema_scripts/ms_sql_server/ODM2_for_MSSQL.sql`, lines 223–283. <https://github.com/ODM2/ODM2>
[^odm2-1-dev]: ODM2, branch `ODM2.1_dev` (last commit 2022-03-04), `doc/ODM2_1/tables/ODM2Core_Variables.html`. <https://github.com/ODM2/ODM2/tree/ODM2.1_dev>
[^nerc-nvs]: NERC Vocabulary Server: P01 (parameter usage), P06 (BODC-approved data storage units), P24 (units of measure dimensions), S06, S26, S27. <https://vocab.nerc.ac.uk/>
[^ntn-map-legend]: National Atmospheric Deposition Program. *NTN map PDF, Sulfur + Nitrogen wet deposition (SplusN_dep), 2023*. <https://nadp.slh.wisc.edu/filelib/maps/NTN/pdfs/2023/SplusN_dep_2023.pdf>, accessed 2026-10-07
[^qudt-changelog]: QUDT, `CHANGELOG.md`, release 3.5.2 (deprecation of the all-zero dimension vector, issue #1533). <https://github.com/qudt/qudt-public-repo/blob/main/CHANGELOG.md>
[^qudt-19]: QUDT issue #19, "Add sameAs links to the old URIs" (opened 2019-12). <https://github.com/qudt/qudt-public-repo/issues/19>
[^odm2-cv]: ODM2 Controlled Vocabularies, vocabulary service and source (commit de48387). <http://vocabulary.odm2.org/>; <https://github.com/ODM2/ODM2ControlledVocabularies>
[^odm2-1-sheet]: ODM2.1 controlled-vocabulary draft workbook (CVs downloaded from vocabulary.odm2.org on 2018-08-30).
