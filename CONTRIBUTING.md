# Contributing

Thanks for helping. Issues and pull requests are welcome. Please read
[AGENTS.md](AGENTS.md) first: its rules (the source's own words kept
verbatim, refuse rather than guess, how dependencies are declared) apply
to every contributor, not only agents.

## Environment

[pixi](https://pixi.sh) manages the environment; do not use bare `pip`
or `conda` here.

```bash
pixi install --all
```

## Tasks

| Task | What it does |
| --- | --- |
| `pixi run test` | the test suite |
| `pixi run lint` | `ruff check` |
| `pixi run format` | `ruff format` |
| `pixi run typecheck` | `pyrefly check src/varwalk` |
| `pixi run build-qudt` | rebuild the shipped QUDT subset |
| `pixi run -e ci test` | the tests in CI's lean environment |
| `pixi run -e pandas2 test` | the tests with pandas 2.3 |

Add or extend a test for any function you change. A runtime dependency
goes in one place: its PyPI name in `pyproject.toml`'s
`[project.dependencies]`, which pixi maps to a conda name. Re-lock after
a change and run `tests/test_package_section.py`, which checks the
locked record.

## Pre-commit

```bash
pixi run pre-commit install
```

The hooks run ruff, codespell, markdownlint-cli2 and zizmor, and the
usual file checks.

## Reporting a problem

Open an issue with the varwalk version (`varwalk.__version__`), what you
expected and what you got, with the full traceback or the wrong values,
and a minimal reproduction. Please do not attach data that belongs to a
client or a project.
