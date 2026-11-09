# AGENTS.md

Guidance for AI coding agents, and for human contributors, working in
this repository. For what varwalk is, see [README.md](README.md) and
[docs/design.md](docs/design.md); for how to contribute, see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Guardrails

- **Work on a branch.** Never commit to `main`, push, merge or tag
  without the maintainer's say-so. Create the branch from local `main`,
  or add `--no-track` when branching from a remote ref, and check
  `git branch -vv` before handing back: no upstream, or the branch's
  own name.
- **Commit messages carry no AI co-author trailer.**
- **Multi-step work pauses for review.** Commit each step on its branch
  and stop for the maintainer's review before the next step starts.
- **Every review finding is fixed before a hand-back**, Minor ones
  included.
- **Neutral naming.** No organization name is a default in the API or
  the data, and nothing here links to a private repository. Link only
  public pages.
- **No routes in tracked files.** No home-directory path, UNC path,
  `smb://` URL or private address (`tests/test_no_routes.py`).

## Refuse, don't guess

A partial crosswalk is safe; a wrong one is not.

- **The data always arrives**: an annotation that cannot be made is a
  warning from the `AnnotationWarning` family
  (`varwalk.warnings`), never an exception and never a silent guess.
  `pyproject.toml` makes every warning an error in the test suite, so a
  test that meets one expects it.
- **Keep the source's own words.** Carry each source's variable names,
  descriptions and units verbatim (`source_long_name`,
  `source_description`, `source_units`). A new name is only for an
  explicitly derived quantity, labelled as such.
- **Never put a basis in a unit string.** `kg-N/ha` or `mg/l as N` are
  misread by UDUNITS (newtons, attoseconds), so `check_udunits` refuses
  them; the string stays in `source_units`.
- **Never loosen a match.** `annotate` refuses a variable whose
  published unit no table row fits. Add a row; do not relax the match.
- **Years are explicit.** An incoming `year` or `yr` means the active
  year setting (default `julian`); written units say `julian_year`,
  `common_year` or `year` (UDUNITS' tropical year).
- **The registry is private.** Use `registry.get_registry()` or pass
  `registry=`. Never build units on pint's global registry.

## Curated tables

- One row per source variable, each stating the `source_units` it was
  curated for.
- Every annotated variable needs a `quantity_kind`, and a `counting`
  (`mass`, `amount` or `equivalents`) wherever `species` is set.
  Equivalents are written in mol.
- Ground every row in the source's own documentation, and link to it.
- Shipped vocabulary subsets (QUDT) keep their licence and attribution.
  `pixi run build-qudt` rebuilds the QUDT subset (the `qudt` feature
  holds its `rdflib`).

## Layout

- `src/varwalk/`: the package. `__init__.py` imports nothing; its
  docstring lists the submodules. `py.typed` marks it typed.
- `tests/`: the pytest suite.
- `docs/design.md`: the design principles, non-goals and variable model.
- `scripts/`: maintenance scripts (the QUDT subset builder).

## Lazy imports

`import varwalk` loads none of pint, pandas, xarray, cf_xarray, cf_units
or molmass, and neither do `varwalk.variables` or `varwalk.warnings`
(`tests/test_lazy_imports.py`). Import heavy packages inside the
functions that need them, or under `TYPE_CHECKING`.

## Environment

[pixi](https://pixi.sh) manages the environment; do not use bare `pip`
or `conda`. Tasks are in `[tool.pixi.tasks]` in `pyproject.toml`:
`test`, `lint`, `format`, `typecheck`, `build-qudt`. Environments:

- `default`: core, qudt, jupyter and dev;
- `ci`: core and dev, the lean environment CI tests in;
- `pandas2`: core and dev with `pandas>=2.3,<3`, in its own solve.

Run `pixi run -e ci test` and `pixi run -e pandas2 test` before handing
back: `pixi run test` uses the full environment and can pass a test that
imports something only an optional feature provides.

`pixi.lock` is generated: never edit it by hand, and expect any
dependency change to rewrite it.

## Dependencies

- **One runtime list.** `[project.dependencies]`, in PyPI names, holds
  what `src/varwalk` imports; pixi-build-python maps it to conda names
  for the package's record (`ignore-pypi-mapping = false`).
- **`[tool.pixi.package.run-dependencies]`** holds only what that list
  cannot say: `pyarrow`, because the mapping turns it into
  `pyarrow-core`, which lacks Parquet.
- **No environment markers and no direct references** in the list: the
  mapping drops the first and turns the second into the conda package of
  that name. No extras either (`pkg[extra]` reaches the record as plain
  `pkg`).
- **`pandas` always comes with `pyarrow`.**
- Tools and optional features (`qudt`, `jupyter`, `dev`, `pandas2`) are
  pixi features, in conda names.
- After every `pixi lock`, run `tests/test_package_section.py`: it reads
  the locked record and fails for a requirement the mapping dropped (for
  example, when the mapping service was unreachable during the lock; lock
  again).
- pixi is pinned (`requires-pixi = ">=0.76,<0.77"`, and `pixi-version:
  v0.76.0` on every setup-pixi step in CI), because pixi-build is a
  preview. Moving it is a deliberate change.

## Style

- Python code at 88 columns; docstrings and comments at 72
  (`[tool.ruff.lint.pycodestyle] max-doc-length`, rule `W505`). An
  unbreakable token longer than that, such as a URL, gets `# noqa: W505`
  on its line.
- Markdown wrapped at 80 columns, checked by markdownlint-cli2.
- The project follows the
  [Scientific Python Development Guide](https://learn.scientific-python.org/development/),
  checked with
  [sp-repo-review](https://learn.scientific-python.org/development/guides/repo-review/).
  The differences are deliberate and each is commented in
  `[tool.repo-review] ignore` in `pyproject.toml`.
- Add or extend a test for any function you change.

## CI

A push to any branch runs on Ubuntu; a PR into `main` adds Windows; a
manual run (`workflow_dispatch`) takes an `os` choice (`windows`, `macos`
or `both`). A `pandas2` job runs on every push and PR. Only `main`
writes the pixi cache, so after a merge that changes `pixi.lock`, run
the workflow manually on `main` with `both` once. The workflow holds no
secrets and its token is read-only; never add the pull-request-target
trigger.
