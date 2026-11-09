# varwalk design

This page restates varwalk's design for readers outside the project. The
design grew out of the units layer of LimnoTech's internal
water-data-engine package, from which varwalk was extracted in 2026.

## Why

Every data system and model packs several concepts into one variable
name. USGS's "00618: Nitrate, water, filtered, milligrams per liter as
nitrogen" combines a constituent, a medium, a fraction, a basis and a
unit. Nothing in common use takes such names apart into shared concepts
that a machine can check, convert and join on. A 2016 white paper on
cross-walking environmental variable names through ODM2's vocabularies
proposed that decomposition.

Even for units alone, no single standard closes the gap, especially for
water-quality variables:

- **The year.** UDUNITS reads `yr` as the tropical year, while pint and
  QUDT mean the Julian year.
- **Basis.** No unit system has a place for "as N". Written into a unit
  string, UDUNITS misreads it: `kg-N/ha` parses as kilogram-newtons per
  hectare.
- **Counting.** `mmol m-2 d-1` and `meq m-2 d-1` share one QUDT quantity
  kind, so whether a number counts a mass, an amount of substance or
  equivalents must be stated separately.
- **Quantity kinds QUDT lacks**, for dimensions it has no kind for.
- **Quantity kind itself.** pint knows dimensions, not kinds: it cannot
  tell a torque from an energy.

## Design principles

1. **Each step pays for itself.** A concept, a vocabulary or a table is
   added when a real deliverable needs it, never ahead of one.
2. **Tables, not ontologies.** Curated CSV tables, one row per source
   variable, checked by tests against the source's documentation.
3. **Fail loudly.** The data always arrives, and anything missing or
   changed is named in a warning from the `AnnotationWarning` family.
4. **Build on, and give back to, the existing libraries.** pint for
   arithmetic, cf-xarray's registry for UDUNITS strings, cf-units for
   UDUNITS-2 validation, QUDT for quantity kinds, molmass for formulas.
   Fixes found here go upstream.
5. **Small surface, cheap to maintain.** One person should be able to
   keep it alive.
6. **Neutral naming.** Nothing in the package's API, data or docs
   depends on one organization's name, so the repository can move.

## Non-goals

- **No ontology engine.** No RDF store, reasoner or SPARQL at runtime.
  Plain tables (CSV, Parquet) and plain attrs; RDF or JSON-LD are
  exports.
- **No competing units registry.** varwalk builds on pint and on
  cf-xarray's registry.
- **No `Quantity` subclass carrying a kind.** A kind is a declared fact
  about a stored variable, checked when it is annotated or converted. It
  is not propagated through arithmetic.
- **No data fetching.** Sources, drivers, caching and storage belong to
  the packages that use varwalk.
- **No live vocabulary calls at runtime.** Vocabulary subsets ship with
  the package, as the QUDT subset does.
- **Not bound to ODM2.1 or I-ADOPT.** Both inform the concepts, together
  with the white paper, but neither limits them.

## Anti-goals

What would make varwalk a failure even if it worked:

- **Ontology first.** varwalk's own lesson is to be useful before it is
  complete: a release that defines concepts no real dataset uses has
  taken on the cost of an ontology without its benefit.
- **Silent wrong answers.** A partial crosswalk is safe; a wrong one is
  not. varwalk refuses rather than guesses: an unannotatable variable
  warns, a basis written into a unit string is refused, and a unit that
  does not fit its row is not loosened to fit.

## The variable model

A variable is described by its **source's own fields**, kept verbatim,
and varwalk's annotation fields:

- `source_long_name`, `source_description`, `source_units`: what the
  source called and described the variable, and the unit it published.
- `standard_name`, `units`, `aliases`, `crosswalk_source` and
  `crosswalk_reference`: the data dictionary shared by tables and
  datasets.
- `quantity_kind`, `counting`, `units_iri`, `species`, `basis`, `medium`
  and `process`: the annotation fields.

A new field is added only when a real dataset needs it, after checking
that an existing vocabulary does not already express it.

The intended mapping of the fields onto other vocabularies, so that
later exports stay straightforward (inferred, not yet checked against
an export):

| varwalk | I-ADOPT | ODM2.1 |
| --- | --- | --- |
| `quantity_kind` | Property | `quantitykindcv` |
| `species` | ObjectOfInterest | `taxonomicclassifierid` |
| `medium` | Matrix | `sampledmediumcv` |
| `basis` | Constraint on the ObjectOfInterest | `speciationid` |
| `counting` | none | none |
| `process` | ObjectOfInterest of a flux system, or a Constraint | none |
| `units`, `units_iri`, `source_units` | out of scope | `CV_Units` |

## Stack

Python 3.12 and later, pint 0.26 and later, and pandas 2.3 and later
(pandas 2 and 3 are both tested). Importing the package is light:
`import varwalk` imports nothing, and each submodule imports what it
needs.

## Related work

- [I-ADOPT](https://i-adopt.github.io/) decomposes what is observed; it
  leaves units out of scope.
- [QUDT](https://www.qudt.org/) models quantity kinds with dimension
  vectors and is the model varwalk follows for kinds.
- [cf-xarray](https://github.com/xarray-contrib/cf-xarray) and
  [xclim](https://xclim.readthedocs.io/) share the registry pattern.
- [pint](https://github.com/hgrecco/pint) has no quantity kinds; see its
  open [quantity kinds pull request](https://github.com/hgrecco/pint/pull/1967).
