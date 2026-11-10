"""The data files ship in a built wheel, so a non-editable install has them."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DATA_FILES = (
    "varwalk/data/qudt/units.parquet",
    "varwalk/data/qudt/quantity_kinds.parquet",
    "varwalk/data/local_kinds.csv",
)


def test_package_data_ships(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "hatchling",
            "build",
            "-t",
            "wheel",
            "-d",
            str(tmp_path),
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    (wheel,) = tmp_path.glob("varwalk-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())
    missing = [name for name in DATA_FILES if name not in members]
    assert not missing, f"not in the wheel: {missing}"
