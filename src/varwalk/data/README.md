# varwalk data

- `qudt/`: the QUDT v3.5.2 subset (units and quantity kinds), with its own
  README naming the release, checksum and CC BY 4.0 attribution.
- `local_kinds.csv`: the local quantity kinds, described below.

## Local quantity kinds (`local_kinds.csv`)

Quantity kinds for dimensions that QUDT has **no** kind for at all, read by
`varwalk.qudt` after QUDT's own. They are not QUDT's: they have no QUDT IRI,
and `qudt.iri` refuses them.

| Name | Dimension vector | For |
| --- | --- | --- |
| `AmountOfSubstancePerArea` | `A1E0L-2I0M0H0T0D0` | amounts and equivalents per area: keq/ha, eq/ha, mmol m-2 |
| `DirectionalVarianceSpectralDensity` | `A0E0L2I0M0H0T1D0` | a wave spectrum per frequency and direction: m2 s rad-1 (CF `sea_surface_wave_directional_variance_spectral_density`) |

The columns are those of `qudt/quantity_kinds.csv` plus `definition`;
`specialization_of` is a `;`-separated list. Add a kind only where no QUDT
kind has the dimension vector, never as a second name for a QUDT kind. The
one exception is `DirectionalVarianceSpectralDensity`: the only QUDT kind
with its vector is `AreaTime`, a different quantity, so it lists `AreaTime`
in `specialization_of`, and the vocabulary test accepts a shared vector only
with that statement. When a QUDT release adds a kind with the same name, the
vocabulary refuses to load until the local row is removed. See
`docs/units.md` section 6.
