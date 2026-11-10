"""The shipped QUDT subset (src/varwalk/data/qudt/). See docs/units.md section 6."""

from __future__ import annotations

import math
import re

import pandas as pd
import pytest

from varwalk import qudt


def test_tables_load_and_match_their_readme():
    readme = (qudt.DATA_DIR / "README.md").read_text()
    assert "v3.5.2" in readme
    n_units = int(re.search(r"`units`: (\d+) units", readme).group(1))
    n_kinds = int(re.search(r"`quantity_kinds`: (\d+) quantity kinds", readme).group(1))
    assert len(qudt.units_table()) == n_units == 2932
    assert len(qudt.quantity_kinds_table()) == n_kinds == 1224


def test_unit_rows_carry_the_values_qudt_publishes():
    mg_per_l = qudt.unit("MilliGM-PER-L")
    assert mg_per_l["dimension_vector"] == "A0E0L-3I0M1H0T0D0"
    assert mg_per_l["conversion_multiplier"] == 0.001
    assert mg_per_l["ucum_code"] == "mg.L-1"
    assert "MassConcentration" in list(mg_per_l["quantity_kinds"])
    assert qudt.unit("DEG_C")["conversion_offset"] == 273.15
    assert qudt.unit("YR")["conversion_multiplier"] == 31557600.0


def test_not_convertible_units_have_no_multiplier():
    assert math.isnan(qudt.unit("NTU")["conversion_multiplier"])


def test_quantity_kind_rows():
    kind = qudt.quantity_kind("MassConcentration")
    assert kind["dimension_vector"] == "A0E0L-3I0M1H0T0D0"
    assert "Density" in list(kind["specialization_of"])


def test_unknown_names_raise_with_suggestions():
    with pytest.raises(ValueError, match="MassConcentration"):
        qudt.quantity_kind("MassConcentratoin")


def test_unknown_term_is_also_a_key_error_with_a_plain_message():
    with pytest.raises(qudt.UnknownTermError) as caught:
        qudt.unit("NotAUnit")
    assert isinstance(caught.value, KeyError)
    assert str(caught.value) == caught.value.args[0]


def test_iris():
    assert (
        qudt.iri("MilliGM-PER-L", "unit") == "http://qudt.org/vocab/unit/MilliGM-PER-L"
    )
    assert (
        qudt.iri("Density", "quantity_kind")
        == "http://qudt.org/vocab/quantitykind/Density"
    )


def test_missing_data_files_raise_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(qudt, "DATA_DIR", tmp_path)
    qudt.units_table.cache_clear()
    try:
        with pytest.raises(FileNotFoundError, match="units.parquet"):
            qudt.units_table()
    finally:
        qudt.units_table.cache_clear()


# --- local quantity kinds (src/varwalk/data/local_kinds.csv)

VECTOR = re.compile(r"^A-?\d+E-?\d+L-?\d+I-?\d+M-?\d+H-?\d+T-?\d+D[01]$")


def test_the_local_kinds_load_and_hold_amount_of_substance_per_area():
    local = qudt.local_kinds_table()
    assert list(local.columns) == [*qudt.quantity_kinds_table().columns, "definition"]
    row = local.loc["AmountOfSubstancePerArea"]
    assert row["dimension_vector"] == "A1E0L-2I0M0H0T0D0"
    assert list(row["specialization_of"]) == []
    assert not row["deprecated"]
    assert "keq/ha" in row["definition"]
    assert qudt.is_local_kind("AmountOfSubstancePerArea")
    assert not qudt.is_local_kind("MassConcentration")


def _shared_vector_problems(local, qudt_table):
    """Local kinds whose vector a QUDT kind also has, unless they name that QUDT kind in
    ``specialization_of``."""
    qudt_vectors = set(qudt_table["dimension_vector"])
    problems = []
    for name, row in local.iterrows():
        if row["dimension_vector"] not in qudt_vectors:
            continue
        broader = [k for k in row["specialization_of"] if k in qudt_table.index]
        if not broader or any(
            qudt_table.loc[k, "dimension_vector"] != row["dimension_vector"]
            for k in broader
        ):
            problems.append(name)
    return problems


def test_a_shared_vector_needs_a_specialization_of_a_qudt_kind_with_it():
    qudt_table = qudt.quantity_kinds_table()
    kinds = qudt_table.loc[["AreaTime", "Length"], "dimension_vector"]
    base = {"dimension_vector": kinds["AreaTime"], "specialization_of": ["AreaTime"]}
    local = pd.DataFrame(
        {
            "Stated": base,
            "Unstated": {**base, "specialization_of": []},
            "Mismatched": {**base, "specialization_of": ["Length"]},
        }
    ).T
    assert _shared_vector_problems(local, qudt_table) == ["Unstated", "Mismatched"]


def test_every_local_kind_has_a_well_formed_vector_and_a_qudt_kind_only_as_its_broader_kind():
    local = qudt.local_kinds_table()
    for name, row in local.iterrows():
        assert VECTOR.match(row["dimension_vector"]), name
    # a kind QUDT names differently (a wave spectrum; QUDT's only match is AreaTime) must say
    # which QUDT kind it specializes
    assert _shared_vector_problems(local, qudt.quantity_kinds_table()) == []


def test_no_local_kind_is_also_a_qudt_name():
    local = set(qudt.local_kinds_table().index)
    assert not local & set(qudt.quantity_kinds_table().index)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (
            "MassConcentration,X,A0E0L-3I0M1H0T0D0,,,,False,,x",
            (
                "local quantity kind\\(s\\) \\['MassConcentration'\\] in local_kinds.csv "
                "are also "
                "QUDT quantity kinds in the shipped subset: QUDT now defines them, so remove them "
                "from the local vocabulary and use QUDT's"
            ),
        ),
        ("Odd,X,A1L-2,,,,False,,x", "malformed dimension vector for \\['Odd'\\]"),
        (
            "Twice,X,A0E0L0I0M0H0T0D0,,,,False,,x\nTwice,X,A0E0L0I0M0H0T0D0,,,,False,,x",
            "local_kinds.csv lists \\['Twice'\\] more than once",
        ),
    ],
    ids=["qudt-name", "malformed", "duplicate"],
)
def test_a_bad_local_vocabulary_raises_when_it_loads(
    monkeypatch, tmp_path, row, message
):
    path = tmp_path / "local_kinds.csv"
    header = qudt.LOCAL_KINDS_PATH.read_text(encoding="utf-8").splitlines()[0]
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    monkeypatch.setattr(qudt, "LOCAL_KINDS_PATH", path)
    qudt.local_kinds_table.cache_clear()
    try:
        with pytest.raises(ValueError, match=message):
            qudt.local_kinds_table()
    finally:
        qudt.local_kinds_table.cache_clear()


def test_a_local_vocabulary_with_the_wrong_columns_raises_when_it_loads(
    monkeypatch, tmp_path
):
    path = tmp_path / "local_kinds.csv"
    path.write_text("name,definition\nOdd,x\n", encoding="utf-8")
    monkeypatch.setattr(qudt, "LOCAL_KINDS_PATH", path)
    qudt.local_kinds_table.cache_clear()
    expected = ["name", *qudt.quantity_kinds_table().columns, "definition"]
    try:
        with pytest.raises(ValueError) as err:
            qudt.local_kinds_table()
    finally:
        qudt.local_kinds_table.cache_clear()
    assert str(err.value) == (
        f"local_kinds.csv has columns ['name', 'definition']; expected {expected}"
    )


def test_quantity_kind_searches_qudt_then_the_local_kinds():
    assert qudt.quantity_kind("MassPerArea")["dimension_vector"] == "A0E0L-2I0M1H0T0D0"
    assert qudt.quantity_kind("AmountOfSubstancePerArea")["dimension_vector"] == (
        "A1E0L-2I0M0H0T0D0"
    )
    with pytest.raises(
        qudt.UnknownTermError, match="nor a local one.*AmountOfSubstancePerArea"
    ):
        qudt.quantity_kind("AmountOfSubstancePerAera")


def test_a_local_kind_has_no_qudt_iri():
    with pytest.raises(ValueError, match="local quantity kind.*no QUDT IRI"):
        qudt.iri("AmountOfSubstancePerArea", "quantity_kind")
