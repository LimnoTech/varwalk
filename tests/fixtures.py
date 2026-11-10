"""Small annotated tables and datacubes for the tests."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import xarray as xr

from varwalk.variables import variables_frame, variables_to_records

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
STAMP = "2026-10-05T12:00:00Z"


def table(columns: dict[str, tuple[list[float | None], str | None]]) -> pd.DataFrame:
    """A wide table: ``{name: (values, units)}``, nullable Float64
    columns, and a data dictionary in ``attrs["variables"]`` as a source
    would attach it."""
    frame = pd.DataFrame(
        {
            name: pd.array(values, dtype="Float64")
            for name, (values, _) in columns.items()
        }
    )
    rows = [
        {"name": name, "source_units": units, "units": units}
        for name, (_, units) in columns.items()
    ]
    frame.attrs["variables"] = variables_to_records(variables_frame(rows))
    return frame


def cube(
    columns: dict[str, tuple[list[float], str | None]],
    *,
    start: str = "2024-01-01",
    freq: str = "MS",
    calendar: str = "standard",
) -> xr.Dataset:
    """A datacube with one ``time`` dimension,
    ``{name: (values, units)}``, and a ``long_name`` on each variable.
    """
    n = len(next(iter(columns.values()))[0])
    time = xr.date_range(
        start, periods=n, freq=freq, calendar=calendar, use_cftime=None
    )
    data_vars = {}
    for name, (values, units) in columns.items():
        attrs = {"long_name": f"{name} as published"}
        if units is not None:
            attrs["units"] = units
        data_vars[name] = ("time", np.asarray(values, dtype="float64"), attrs)
    return xr.Dataset(data_vars, coords={"time": time})


def record(data, name: str) -> dict:
    """The data-dictionary record of a table variable, or the attrs of a
    Dataset variable."""
    if isinstance(data, xr.Dataset):
        return dict(data[name].attrs)
    return next(r for r in data.attrs["variables"] if r["name"] == name)


def values(data, name: str) -> list[float]:
    """A variable's values as plain floats (NaN for missing)."""
    if isinstance(data, xr.Dataset):
        return [float(v) for v in data[name].values]
    return [float(v) for v in data[name].to_numpy(dtype="float64", na_value=np.nan)]


def cf_roundtrip(ds: xr.Dataset) -> xr.Dataset:
    """``ds`` encoded and decoded as a netCDF file would be (packing,
    fill values, range attributes), without a file: the environment has
    no netCDF engine."""
    variables, attrs = xr.conventions.cf_encoder(ds.variables, ds.attrs)
    return xr.decode_cf(xr.Dataset(variables, attrs=attrs))
