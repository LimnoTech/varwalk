"""Hold varwalk's package section to its one dependency list.

varwalk is a pixi-build source package: a consumer that names it under
a conda ``[dependencies]`` table gets its conda record in its own solve.
With ``ignore-pypi-mapping = false``, pixi-build-python writes that
record from ``[project.dependencies]`` (PyPI names, mapped to conda
names) plus ``[tool.pixi.package.run-dependencies]``. The mapping drops
a requirement it cannot map without a word: a requirement with an
environment marker, a direct reference, a PyPI-only name, or any name
the mapping service could not be reached for during the lock. The
record test below reads the record pixi locked and fails on each of
those.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

import varwalk

REPO = Path(__file__).resolve().parents[1]

# PyPI-only requirements (no conda-forge build): none.
PYPI_ONLY: set[str] = set()

# Where the conda name is not one of the usual spellings.
RENAMES: dict[str, str] = {}

# Packages taken as source packages from a checkout beside this one:
# none, varwalk is the bottom of its chain.
UPSTREAMS: set[str] = set()


@pytest.fixture(scope="module")
def pyproject() -> dict:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


@pytest.fixture(scope="module")
def lock() -> dict:
    text = (REPO / "pixi.lock").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def package(pyproject: dict) -> dict:
    return pyproject["tool"]["pixi"]["package"]


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    pattern = r"[\s<>=!~;\[@(]"
    return re.split(pattern, requirement.strip(), maxsplit=1)[0]


def requirement_specifier(requirement: str) -> str:
    """The version specifier of a plain requirement, spaces removed."""
    rest = requirement.strip()[len(requirement_name(requirement)) :]
    return re.sub(r"\s+", "", rest)


def conda_names(pypi: str) -> set[str]:
    """The conda spellings a PyPI name usually maps to."""
    base = normalize(pypi)
    names = {base, base.replace("-", "_")}
    names |= {
        f"python-{base}",
        f"py-{base}",
        f"{base}-base",
        f"{base}-core",
        f"{base}-python",
    }
    if base in RENAMES:
        names.add(RENAMES[base])
    return {normalize(n) for n in names}


def self_records(pyproject: dict, lock: dict) -> dict[str, dict]:
    """The package's own record (``conda_source``) per platform.

    Fails naming the platform whose default environment has none, so a
    lock made for fewer platforms than the workspace declares cannot
    pass on the records it does have.
    """
    name = package(pyproject)["name"]
    packages = {
        str(p.get("conda_source")): p for p in lock["packages"] if "conda_source" in p
    }
    environment = lock["environments"]["default"]["packages"]
    records = {}
    for platform in pyproject["tool"]["pixi"]["workspace"]["platforms"]:
        sources = [
            e["conda_source"]
            for e in environment.get(platform, [])
            if str(e.get("conda_source", "")).startswith(f"{name}[")
            and str(e["conda_source"]).endswith("@ .")
        ]
        assert len(sources) == 1, f"{platform}: {len(sources)} self records"
        records[platform] = packages[sources[0]]
    return records


def test_conda_names_tries_the_usual_spellings():
    # Every spelling is normalized (underscores become hyphens), the
    # way the record test compares names.
    assert {"matplotlib-base", "pyarrow-core", "python-cf-xarray"} <= (
        conda_names("matplotlib") | conda_names("pyarrow") | conda_names("cf-xarray")
    )
    assert "cf-xarray" in conda_names("cf_xarray")
    assert "pandas" in conda_names("pandas")


def test_requirement_specifier_drops_the_name_and_spaces():
    assert requirement_specifier("pandas >= 2.3, <4") == ">=2.3,<4"
    assert requirement_specifier("pint-xarray") == ""


def test_the_mapping_is_on(pyproject):
    """Without it the record lacks [project.dependencies]."""
    config = package(pyproject)["build"]["config"]
    assert config["ignore-pypi-mapping"] is False


def test_no_requirement_has_a_marker_or_a_direct_reference(pyproject):
    """The mapping drops a marked requirement on every platform and
    turns a direct reference into the conda package of that name."""
    dependencies = pyproject["project"]["dependencies"]
    assert [r for r in dependencies if ";" in r or "@" in r] == []


def test_no_requirement_asks_for_an_extra(pyproject):
    """A source package's record carries no extras."""
    dependencies = pyproject["project"]["dependencies"]
    assert [r for r in dependencies if "[" in r] == []


def test_the_dependency_list_is_the_one_the_code_needs(pyproject):
    names = {
        normalize(requirement_name(r)) for r in pyproject["project"]["dependencies"]
    }
    assert names == {
        "cf-units",
        "cf-xarray",
        "molmass",
        "numpy",
        "pandas",
        "pint",
        "pint-xarray",
        "pyarrow",
        "xarray",
    }


def test_pypi_only_names_are_requirements(pyproject):
    """The allowlist names only real requirements."""
    if not PYPI_ONLY:
        pytest.skip("no PyPI-only package")
    names = {
        normalize(requirement_name(r)) for r in pyproject["project"]["dependencies"]
    }
    assert PYPI_ONLY <= names


def test_every_requirement_reaches_the_record(pyproject, lock):
    """Each requirement not on PYPI_ONLY is in every self record's
    depends, by one of its conda names, with its specifier."""
    missing = []
    for record in self_records(pyproject, lock).values():
        depends: dict[str, set[str]] = {}
        for entry in record.get("depends", []):
            name, _, spec = entry.partition(" ")
            depends.setdefault(normalize(name), set()).add(re.sub(r"\s+", "", spec))
        for requirement in pyproject["project"]["dependencies"]:
            name = requirement_name(requirement)
            if normalize(name) in PYPI_ONLY:
                continue
            wanted = requirement_specifier(requirement)
            specs = set().union(*(depends.get(n, set()) for n in conda_names(name)))
            if not specs or (wanted and wanted not in specs):
                missing.append(f"{record['conda_source']}: {requirement}")
    assert missing == [], (
        "requirements missing from the record (re-lock after a change)"
    )


def test_requires_python_reaches_the_record(pyproject, lock):
    wanted = re.sub(r"\s+", "", pyproject["project"]["requires-python"])
    for record in self_records(pyproject, lock).values():
        depends = record.get("depends", [])
        assert f"python {wanted}" in depends, record["conda_source"]


def test_pypi_only_names_are_not_in_the_record(pyproject, lock):
    """If one appears, conda-forge has gained a build: drop it from
    the allowlist."""
    if not PYPI_ONLY:
        pytest.skip("no PyPI-only package")
    for record in self_records(pyproject, lock).values():
        names = {normalize(e.split()[0]) for e in record.get("depends", [])}
        for pypi in PYPI_ONLY:
            assert not (names & conda_names(pypi)), pypi


def test_upstreams_are_source_packages_in_the_run_dependencies(pyproject):
    """A package taken from a sibling checkout goes only in the
    run-dependencies, by path."""
    if not UPSTREAMS:
        pytest.skip("no upstream source package")
    run_dependencies = package(pyproject)["run-dependencies"]
    for name in UPSTREAMS:
        declared = run_dependencies[name]
        assert isinstance(declared, dict)
        assert declared.get("path") == f"../{name}", name


def test_the_package_consumes_itself(pyproject):
    pixi = pyproject["tool"]["pixi"]
    assert pixi["dependencies"]["varwalk"] == {"path": "."}
    assert "varwalk" not in pixi.get("pypi-dependencies", {})


def locked_names(entry: dict) -> str | None:
    """The package name of a lock environment entry, or None for a
    source package (``conda_source``)."""
    url = entry.get("conda") or entry.get("pypi")
    if not url:
        return None
    filename = url.rsplit("/", 1)[-1].split("#", 1)[0]
    if "conda" in entry:
        stem = re.sub(r"\.(conda|tar\.bz2)$", "", filename)
        return normalize(stem.rsplit("-", 2)[0])
    return normalize(re.split(r"-\d", filename, maxsplit=1)[0])


def locked_version(entry: dict) -> str:
    filename = (entry.get("conda") or "").rsplit("/", 1)[-1]
    stem = re.sub(r"\.(conda|tar\.bz2)$", "", filename)
    return stem.rsplit("-", 2)[1]


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])


def locked_platforms(lock: dict):
    """Each (environment, platform, entries) the lock holds."""
    for env_name, env in lock["environments"].items():
        for platform, entries in env["packages"].items():
            yield env_name, platform, entries


def test_locked_names_reads_conda_and_pypi_entries():
    base = "https://conda.anaconda.org/conda-forge/osx-arm64/"
    conda = {"conda": base + "pyarrow-core-26.0.0-py312h_1_cpu.conda"}
    wheel = "pcodec-1.1.0-cp312-cp312-macosx_11_0_arm64.whl"
    pypi = {"pypi": "https://files.pythonhosted.org/packages/0f/" + wheel}
    assert locked_names(conda) == "pyarrow-core"
    assert locked_version(conda) == "26.0.0"
    assert locked_names(pypi) == "pcodec"
    assert locked_names({"conda_source": "x[1] @ ."}) is None
    assert version_tuple("3.38.2") >= (3, 38)


def test_pyarrow_is_locked_wherever_pandas_is(lock):
    """pandas 3 backs its str dtype with pyarrow only when pyarrow is
    installed, and conda-forge's pandas does not require it."""
    missing = []
    for env_name, platform, entries in locked_platforms(lock):
        names = {locked_names(e) for e in entries}
        if "pandas" in names and not names & {"pyarrow", "pyarrow-core"}:
            missing.append(f"{env_name}/{platform}")
    assert missing == [], "pandas is locked without pyarrow"


def test_sqlite_is_at_least_3_38_wherever_libgdal_is(lock):
    """GDAL needs sqlite 3.38 and its packages leave it unbounded.

    varwalk has no GDAL, so this skips unless a lock holds libgdal.
    """
    too_old = []
    seen = False
    for env_name, platform, entries in locked_platforms(lock):
        by_name = {locked_names(e): e for e in entries if "conda" in e}
        if not {"libgdal", "libgdal-core"} & set(by_name):
            continue
        seen = True
        sqlite = by_name.get("sqlite") or by_name.get("libsqlite")
        if sqlite is None or version_tuple(locked_version(sqlite)) < (3, 38):
            too_old.append(f"{env_name}/{platform}")
    if not seen:
        pytest.skip("no libgdal in the lock")
    assert too_old == [], "libgdal is locked beside sqlite older than 3.38"


def test_python_has_no_ceiling(pyproject):
    assert "<" not in pyproject["project"]["requires-python"]


def test_run_dependencies_hold_only_pyarrow(pyproject):
    """The runtime list is [project.dependencies]. The mapping turns
    pyarrow into pyarrow-core, which lacks Parquet, so the full
    package is named here (the QUDT tables are Parquet)."""
    assert set(package(pyproject)["run-dependencies"]) == {"pyarrow"}
    assert "run-constraints" not in package(pyproject)


def test_core_feature_holds_only_python(pyproject):
    feature = pyproject["tool"]["pixi"]["feature"]["core"]
    assert set(feature["dependencies"]) == {"python"}


def test_pandas2_environment_pins_the_oldest_pandas(pyproject):
    pixi = pyproject["tool"]["pixi"]
    assert pixi["feature"]["pandas2"]["dependencies"] == {"pandas": ">=2.3,<3"}
    environments = pixi["environments"]
    assert "solve-group" not in environments["pandas2"]
    assert environments["default"]["solve-group"] == "default"
    assert environments["ci"]["solve-group"] == "default"


def test_package_version_is_the_latest_release(pyproject):
    """The package version is the newest CHANGELOG heading, bumped at
    each release.

    ``__version__`` still comes from hatch-vcs (``_version.py``).
    """
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    pattern = r"^## \[?(\d+(?:\.\d+)*)\]?"
    released = re.findall(pattern, changelog, flags=re.MULTILINE)
    assert released, "CHANGELOG.md has no '## x.y.z' heading"
    assert package(pyproject)["version"] == released[0]

    assert pyproject["tool"]["hatch"]["version"]["source"] == "vcs"
    assert "version" in pyproject["project"]["dynamic"]
    # Only in a built or editable install: _version.py is generated.
    _version = pytest.importorskip("varwalk._version")
    assert varwalk.__version__ == _version.__version__


def test_ci_environment_has_no_jupyter_or_qudt_stack():
    """The self-package brings in only its record, never the Jupyter
    stack or the QUDT builder's rdflib."""
    pixi = shutil.which("pixi")
    if pixi is None:
        pytest.skip("pixi is not on PATH")
    listed = subprocess.run(
        [pixi, "list", "--environment", "ci", "--frozen", "--json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    names = {entry["name"] for entry in json.loads(listed.stdout)}
    assert "varwalk" in names
    present = names & {"jupyterlab", "jupytext", "rdflib"}
    assert not present, f"ci has packages it should not: {sorted(present)}"


def spec(text: str) -> str:
    return re.sub(r"\s+", "", text)


def satisfies(version: str, specifier: str) -> bool:
    """Whether a dotted version meets a comma-joined specifier.

    Raises ValueError naming the text for a version that is not dotted
    numbers or an operator this does not read (``~=``, ``!=``).
    """

    def parts(text: str) -> tuple[int, ...]:
        if not re.fullmatch(r"v?\d+(\.\d+)*", text):
            raise ValueError(f"not a dotted numeric version: {text!r}")
        return tuple(int(p) for p in text.lstrip("v").split("."))

    compare = {
        ">=": lambda a, b: a >= b,
        ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        "<": lambda a, b: a < b,
        "==": lambda a, b: a[: len(b)] == b,
    }
    for clause in spec(specifier).split(","):
        match = re.fullmatch(r"(>=|<=|==|>|<)([^<>=!~]+)", clause)
        if match is None:
            raise ValueError(f"unsupported specifier {clause!r}")
        op, bound = match.groups()
        if not compare[op](parts(version), parts(bound)):
            return False
    return True


def test_satisfies_reads_requires_pixi_ranges():
    assert satisfies("v0.84.2", ">=0.84.2")
    assert satisfies("0.85.0", ">=0.84.2")
    assert not satisfies("0.84.1", ">=0.84.2")
    # The helper still reads a ceiling, though the family sets none.
    assert not satisfies("v0.85.0", ">=0.84,<0.85")


def test_satisfies_names_a_version_it_cannot_read():
    with pytest.raises(ValueError, match="'latest'"):
        satisfies("latest", ">=0.84.2")


@pytest.mark.parametrize("specifier", ["~=0.84", "!=0.85", ">=0.84,!=0.84.1"])
def test_satisfies_refuses_an_unsupported_specifier(specifier):
    with pytest.raises(ValueError, match="unsupported specifier"):
        satisfies("0.84.2", specifier)


def setup_pixi_steps(workflow: dict) -> list[dict]:
    """The prefix-dev/setup-pixi steps of a parsed workflow."""
    return [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps") or []
        if str(step.get("uses", "")).startswith("prefix-dev/setup-pixi")
    ]


def pixi_pin_problems(workflow: dict, required: str | None) -> list[str]:
    """What is wrong with the workflow's pixi pins, one per step."""
    problems = []
    for step in setup_pixi_steps(workflow):
        name = step.get("name", step["uses"])
        version = (step.get("with") or {}).get("pixi-version")
        if version is None:
            problems.append(f"{name!r} sets no pixi-version")
        elif required:
            try:
                inside = satisfies(str(version), required)
            except ValueError as error:
                problems.append(f"{name!r}: pixi-version {version!r}: {error}")
            else:
                if not inside:
                    problems.append(
                        f"{name!r}: pixi-version {version!r} is outside {required!r}"
                    )
    return problems


def workflow_with(step_with: object) -> dict:
    step = {
        "name": "Setup pixi",
        "uses": "prefix-dev/setup-pixi@v0",
        "with": step_with,
    }
    return {"jobs": {"j": {"steps": [step]}}}


def test_an_empty_with_is_reported_not_raised():
    problems = pixi_pin_problems(workflow_with(None), ">=0.84.2")
    assert problems == ["'Setup pixi' sets no pixi-version"]


def test_a_non_numeric_pixi_version_is_reported_with_its_step():
    workflow = workflow_with({"pixi-version": "latest"})
    (problem,) = pixi_pin_problems(workflow, ">=0.84.2")
    assert problem.startswith("'Setup pixi': pixi-version 'latest'")


def test_an_unsupported_requires_pixi_is_reported():
    workflow = workflow_with({"pixi-version": "v0.84.2"})
    (problem,) = pixi_pin_problems(workflow, "~=0.84")
    assert "unsupported specifier" in problem


def test_ci_pins_the_pixi_version(pyproject):
    """pixi-build is a preview, so CI runs the pixi the lock used."""
    path = REPO / ".github/workflows/ci.yaml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert setup_pixi_steps(workflow), "no setup-pixi step in ci.yaml"
    required = pyproject["tool"]["pixi"]["workspace"].get("requires-pixi")
    problems = pixi_pin_problems(workflow, required)
    assert not problems, "; ".join(problems)


def test_requires_pixi_is_a_floor_only(pyproject):
    required = pyproject["tool"]["pixi"]["workspace"]["requires-pixi"]
    assert re.fullmatch(r">=\d+\.\d+\.\d+", required), required


def test_ci_pins_the_floor_version(pyproject):
    floor = pyproject["tool"]["pixi"]["workspace"]["requires-pixi"][2:]
    workflow = yaml.safe_load(
        (REPO / ".github/workflows/ci.yaml").read_text(encoding="utf-8")
    )
    pins = {s["with"]["pixi-version"] for s in setup_pixi_steps(workflow)}
    assert pins == {f"v{floor}"}


def test_the_canary_runs_the_latest_pixi():
    canary = yaml.safe_load(
        (REPO / ".github/workflows/pixi-canary.yaml").read_text(encoding="utf-8")
    )
    # PyYAML reads the bare key `on` as True.
    triggers = canary.get("on", canary.get(True))
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    (step,) = setup_pixi_steps(canary)
    assert step["with"]["pixi-version"] == "latest"
    assert step["with"]["cache"] is False
    assert step["with"]["locked"] is True


def test_ci_is_safe_for_a_public_repository():
    """No secrets and no pull_request_target: a fork's PR runs this."""
    text = (REPO / ".github/workflows/ci.yaml").read_text(encoding="utf-8")
    assert "secrets." not in text
    workflow = yaml.safe_load(text)
    # PyYAML reads the bare key `on` as True.
    triggers = workflow.get("on", workflow.get(True))
    assert "pull_request_target" not in triggers
    assert workflow["permissions"] == {"contents": "read"}


def test_ci_runs_the_pandas2_job_on_push_and_pull_request():
    path = REPO / ".github/workflows/ci.yaml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    job = workflow["jobs"]["pandas2"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["if"] == "github.event_name != 'workflow_dispatch'"
    text = path.read_text(encoding="utf-8")
    assert "pixi run -e pandas2 test" in text
