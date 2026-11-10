# Changelog

## 0.1.0 (unreleased)

First version of varwalk, extracted in 2026 from the units layer of
LimnoTech's internal water-data-engine package. A pre-release: the
interface may still change before 1.0. It is a pixi-build source
package with CI and a record test of its dependency list.

- Modules: `registry` (the private pint registry, the year setting, CF
  formatting), `qudt` and `validate` (the shipped QUDT subset, dimension
  vectors, quantity kinds), `annotate` (`annotate`,
  `validate_annotations`, `read_table` and `clear_table_cache`),
  `convert` (`convert_units`, `rate_to_amount`), `chemistry`
  (`convert_basis`, `convert_amount`, and the public formula helpers
  `formula`, `molar_mass`, `charge` and `basis_count`), `dictionary`,
  `variables` and `warnings`. `import varwalk` loads none of the heavy
  packages.
- Vocabulary: a subset of QUDT's units and quantity kinds, shipped as
  package data (QUDT is licensed CC BY 4.0), and a small set of local
  quantity kinds (`local_kinds.csv`) for what QUDT does not define.
- Every function that writes a `history` line takes `mark=`, the text
  that opens the line after its timestamp; the default is
  `" varwalk: "`.
- `crosswalk_sources=` on the data-dictionary functions names the
  sources a variable's crosswalk may cite.
- pandas 2.3 and later, and pandas 3, are supported.
