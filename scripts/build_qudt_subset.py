"""Build the QUDT subset shipped in src/varwalk/data/qudt/.

Run with `pixi run build-qudt` (rdflib is in the qudt feature).
Downloads the pinned QUDT release, checks its SHA-256, parses units,
quantity kinds and dimension vectors, and writes Parquet with a CSV copy
plus a README carrying the release and CC BY 4.0 attribution. Rebuilding
is deliberate: bump RELEASE, URL and SHA256 together when QUDT releases.
"""

from __future__ import annotations

import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
from rdflib import Graph, Namespace
from rdflib.namespace import DCTERMS, RDF, RDFS

RELEASE = "3.5.2"
RELEASE_DATE = "2026-09-22"
URL = f"https://github.com/qudt/qudt-public-repo/releases/download/v{RELEASE}/qudt-public-repo-{RELEASE}.zip"
SHA256 = "1a42d6409f57e2d8fc4f55aac5e4378926c28a655a045309714f0014fcea3e02"
MEMBERS = (
    "vocab/unit/VOCAB_QUDT-UNITS-ALL.ttl",
    "vocab/quantitykinds/VOCAB_QUDT-QUANTITY-KINDS-ALL.ttl",
    "vocab/dimensionvectors/VOCAB_QUDT-DIMENSION-VECTORS.ttl",
)
OUT = Path(__file__).resolve().parents[1] / "src/varwalk/data/qudt"

QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT_NS = "http://qudt.org/vocab/unit/"
QK_NS = "http://qudt.org/vocab/quantitykind/"
QKDV_NS = "http://qudt.org/vocab/dimensionvector/"


def _local(iri, namespace):
    text = "" if iri is None else str(iri)
    return text[len(namespace) :] if text.startswith(namespace) else None


def _one(graph, subject, predicate):
    # QUDT gives some units several symbols or UCUM codes; keep the
    # first in sort order, so a rebuild from the same release always
    # writes the same subset
    values = sorted(str(value) for value in graph.objects(subject, predicate))
    return values[0] if values else None


def _label(graph, subject):
    labels = list(graph.objects(subject, RDFS.label))
    english = [x for x in labels if getattr(x, "language", None) in ("en", "en-US")]
    plain = [x for x in labels if getattr(x, "language", None) is None]
    chosen = (english or plain or labels or [None])[0]
    return None if chosen is None else str(chosen)


def _download() -> bytes:
    with urllib.request.urlopen(URL) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"SHA-256 mismatch for {URL}: {digest}")
    return data


def build(zip_bytes: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    graph = Graph()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for member in MEMBERS:
            graph.parse(data=archive.read(member).decode("utf-8"), format="turtle")

    units = []
    for subject in set(graph.subjects(RDF.type, QUDT.Unit)):
        name = _local(subject, UNIT_NS)
        if name is None:
            continue
        kinds = sorted(
            {
                kind
                for predicate in (QUDT.hasQuantityKind, QUDT.unitForQuantityKind)
                for obj in graph.objects(subject, predicate)
                if (kind := _local(obj, QK_NS))
            }
        )
        multiplier = _one(graph, subject, QUDT.conversionMultiplier)
        multiplier = (
            None
            if multiplier is None or float(multiplier) == 0.0
            else float(multiplier)
        )
        units.append(
            {
                "name": name,
                "label": _label(graph, subject),
                "symbol": _one(graph, subject, QUDT.symbol),
                "ucum_code": _one(graph, subject, QUDT.ucumCode),
                "udunits_code": _one(graph, subject, QUDT.udunitsCode),
                "dimension_vector": _local(
                    _one(graph, subject, QUDT.hasDimensionVector), QKDV_NS
                ),
                # null where QUDT gives 0.0: "not convertible"
                "conversion_multiplier": multiplier,
                "conversion_offset": float(
                    _one(graph, subject, QUDT.conversionOffset) or 0.0
                ),
                "quantity_kinds": kinds,
                "deprecated": _one(graph, subject, QUDT.deprecated) == "true",
                "replaced_by": _local(
                    _one(graph, subject, DCTERMS.isReplacedBy), UNIT_NS
                ),
            }
        )

    kinds = []
    for subject in set(graph.subjects(RDF.type, QUDT.QuantityKind)):
        name = _local(subject, QK_NS)
        if name is None:
            continue
        kinds.append(
            {
                "name": name,
                "label": _label(graph, subject),
                "dimension_vector": _local(
                    _one(graph, subject, QUDT.hasDimensionVector), QKDV_NS
                ),
                "specialization_of": sorted(
                    {
                        k
                        for o in graph.objects(subject, QUDT.specializationOf)
                        if (k := _local(o, QK_NS))
                    }
                ),
                "qkdv_numerator": _local(
                    _one(graph, subject, QUDT.qkdvNumerator), QKDV_NS
                ),
                "qkdv_denominator": _local(
                    _one(graph, subject, QUDT.qkdvDenominator), QKDV_NS
                ),
                "deprecated": _one(graph, subject, QUDT.deprecated) == "true",
                "replaced_by": _local(
                    _one(graph, subject, DCTERMS.isReplacedBy), QK_NS
                ),
            }
        )
    return (
        pd.DataFrame(units).sort_values("name", ignore_index=True),
        pd.DataFrame(kinds).sort_values("name", ignore_index=True),
    )


def _write(frame: pd.DataFrame, stem: str) -> None:
    frame.to_parquet(OUT / f"{stem}.parquet", index=False)
    csv = frame.copy()
    for column in ("quantity_kinds", "specialization_of"):
        if column in csv:
            csv[column] = csv[column].map(";".join)
    csv.to_csv(OUT / f"{stem}.csv", index=False)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    units, kinds = build(_download())
    _write(units, "units")
    _write(kinds, "quantity_kinds")
    (OUT / "README.md").write_text(
        f"# QUDT subset\n\n"
        f"Extracted from [QUDT](https://qudt.org) release v{RELEASE} ({RELEASE_DATE}), "
        f"`{URL}`, SHA-256 `{SHA256}`, by `scripts/build_qudt_subset.py`.\n\n"
        f"- `units`: {len(units)} units\n- `quantity_kinds`: {len(kinds)} quantity "
        f"kinds\n\n"
        "QUDT is licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); "
        "attribution to QUDT.org. `conversion_multiplier` is null where QUDT gives 0.0 "
        '("not convertible"). Rebuild with `pixi run build-qudt`.\n'
    )
    print(f"{len(units)} units, {len(kinds)} quantity kinds -> {OUT}")


if __name__ == "__main__":
    main()
