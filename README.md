# varwalk: variable crosswalks for water and environmental data

varwalk takes a data variable apart into the concepts packed into its
name: its units, its quantity kind, its species, its basis, how it is
counted (mass, amount of substance or equivalents), its medium and its
process. It checks those concepts, converts between units and chemical
bases, and keeps the source's own names, descriptions and units verbatim
beside them, so a reader sees the vocabulary the agency or model actually
used. It works on pandas DataFrames and xarray Datasets.

> **Pre-release.** varwalk is version 0.x: the API may change between
> releases. It is not on PyPI or conda-forge yet.

## Install

As a pixi source package, from a checkout beside your project. In your
`pyproject.toml` (or `pixi.toml`, without the `tool.pixi.` prefix):

```toml
[tool.pixi.workspace]
preview = ["pixi-build"]

[tool.pixi.dependencies]
varwalk = { path = "../varwalk" }
```

Or with pip, from git:

```bash
pip install "varwalk @ git+https://github.com/LimnoTech/varwalk@v0.1.0"
```

`requires-python = ">=3.12"` keeps Python 3.12 supported past
[SPEC 0](https://scientific-python.org/specs/spec-0000/)'s 2026-10 drop,
because the package's first users run 3.12. pandas 2.3 and later, and
pandas 3, are both supported.

## Example

```python
import xarray as xr

from varwalk.annotate import annotate
from varwalk.convert import convert_units

values = ("time", [1.0, 2.0], {"units": "mg l-1"})
ds = xr.Dataset({"NO3": values}, coords={"time": [0, 1]})
kind = {"quantity_kind": "MassConcentration", "counting": "mass"}
annotations = {"NO3": {**kind, "species": "NO3-", "basis": "N"}}
annotated_ds = annotate(ds, annotations)  # source units kept verbatim
converted_ds = convert_units(annotated_ds, {"NO3": "ug l-1"})
print(converted_ds.attrs["history"])  # the conversion is recorded
```

The same two calls work on a pandas DataFrame that carries a data
dictionary in `attrs["variables"]`.

## Licences

varwalk is MIT licensed ([LICENSE](LICENSE)). The QUDT subset it ships
is derived from [QUDT](https://www.qudt.org/) and is licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); keep the
attribution it carries when you redistribute it.

## Provenance

varwalk was extracted in 2026 from the units layer of LimnoTech's
internal water-data-engine package, with fresh history. Its design is
restated in [docs/design.md](docs/design.md).

## Credits

varwalk grows from Anthony Aufdenkampe's 2016 white paper on
cross-walking environmental variable names through ODM2's vocabularies,
and from the Observations Data Model 2 (ODM2) built by
[Jeff Horsburgh](https://github.com/horsburgh),
[Emilio Mayorga](https://github.com/emiliom),
[Kerstin Lehnert](https://github.com/klehnert55) and their colleagues,
and its successor ODMX by
[Roelof Versteeg](https://github.com/roelofversteeg). It owes much to all
the participants in the ODM2 and BiG-CZ workshops from 2012 to 2018.

## Related projects

- [I-ADOPT](https://i-adopt.github.io/) decomposes what is observed into
  property, object of interest, matrix and constraints. It came later
  than the 2016 paper and is an influence. It leaves units out of scope;
  varwalk adds units and counting.
- [QUDT](https://www.qudt.org/) supplies the quantity kinds and units.
- [cf-xarray](https://github.com/xarray-contrib/cf-xarray) supplies the
  UDUNITS registry that varwalk builds on.
- [pint](https://github.com/hgrecco/pint) does the unit arithmetic. It
  has no quantity kinds.
- [NERC NVS](https://vocab.nerc.ac.uk/) holds controlled vocabularies
  that varwalk's terms can cross-reference.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).
