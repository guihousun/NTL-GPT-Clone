"""Match H3C DEI labels to annual LongNTL city TNTL rows.

The matcher is deterministic and fail-closed.  Administrative suffixes are
resolved only through unique prefix matching against the frozen boundary
table, with a single explicit alias for ``黔西南州``.  The 2023 ``毫州`` label
is quarantined because the same edition also contains a different ``亳州``
score and the boundary asset contains only one ``亳州市`` geometry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


WORKBOOK_SHA256 = "6C7ABE1A06917FBF9BEEE26C7462ED00557EA038A5374DFC0EDA9BEB240AB753"
LABEL_SOURCE = (
    "H3C live AllCityOneInfo API snapshot matched to workbook; "
    f"workbook_sha256={WORKBOOK_SHA256}; model-year semantics follow the user's "
    "explicit instruction that IndexYear is the DEI year"
)
BOUNDARY_ASSET = "projects/empyrean-caster-430308-m2/assets/city"
NTL_DATASET = "projects/sat-io/open-datasets/npp-viirs-ntl"
NTL_BAND = "b1"
PREPROCESSING_ID = "longntl_annual_native500m_positive_pixel_sum_v1"
ALIAS_OVERRIDES = {
    "黔西南州": "黔西南布依族苗族自治州",
}
QUARANTINE_LABELS = {
    (2023, "毫州"): (
        "unresolved_spelling_collision: 2023 also contains 亳州=42.7; the boundary "
        "asset has one 亳州市 geometry and no 毫州市 geometry"
    ),
}


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": (
        "Create a source-traceable H3C IndexYear-DEI/LongNTL-TNTL training table "
        "with a deterministic city-boundary match and explicit quarantine."
    ),
    "input_manifest": [
        {
            "kind": "normalized_dei_label_csv",
            "path": "data/dei_labels_2017_2024.csv",
            "required": True,
        },
        {
            "kind": "city_year_tntl_csv",
            "path": "data/city_tntl_longntl_2017_2024.csv",
            "required": True,
        },
        {
            "kind": "tntl_extraction_manifest",
            "path": "data/city_tntl_longntl_2017_2024_manifest.json",
            "required": True,
        },
    ],
    "method_steps": [
        "validate unique year-label and year-boundary keys",
        "apply explicit aliases and otherwise require a unique boundary-name prefix",
        "quarantine the documented 2023 毫州/亳州 collision",
        "reject non-positive TNTL from log-model training",
        "validate unique year-boundary keys after matching",
        "write training, matching, quarantine, and manifest artifacts",
    ],
    "parameters": {
        "year_semantics": "same H3C IndexYear and LongNTL calendar-year key",
        "alias_overrides": ALIAS_OVERRIDES,
        "quarantine_labels": ["2023:毫州"],
    },
    "output_manifest": [
        {
            "kind": "matched_training_csv",
            "path": "data/dei_longntl_matched_2017_2024.csv",
            "required": True,
        },
        {
            "kind": "city_match_csv",
            "path": "data/dei_longntl_city_match.csv",
            "required": True,
        },
        {
            "kind": "quarantine_csv",
            "path": "data/dei_longntl_quarantine.csv",
            "required": True,
        },
        {
            "kind": "matching_manifest_json",
            "path": "data/dei_longntl_matching_manifest.json",
            "required": True,
        },
    ],
    "validation_checks": [
        "1474 input label rows with recorded annual counts",
        "3000 unique year-boundary TNTL rows",
        "no duplicate year-boundary training key",
        "all training TNTL values are finite and positive",
        "every exclusion has a machine-readable quarantine reason",
    ],
    "failure_gates": [
        "missing input field or provenance manifest",
        "ambiguous or missing boundary match outside the explicit quarantine",
        "duplicate year-label, year-boundary, or matched training key",
        "non-finite DEI/TNTL",
        "unacknowledged quarantine rows",
    ],
    "execution": {
        "mode": "local",
        "timeout_seconds": 120,
        "overwrite_policy": "explicit output paths",
        "network_scope": [],
        "test_strategy": "unit tests plus full-table row/count/uniqueness assertions",
    },
}


class MatchError(ValueError):
    """Raised when a city or integrity gate cannot be resolved safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def require_fields(rows: list[dict[str, str]], fields: Iterable[str], name: str) -> None:
    if not rows:
        raise MatchError(f"{name} contains no rows")
    missing = [field for field in fields if field not in rows[0]]
    if missing:
        raise MatchError(f"{name} is missing fields: {', '.join(missing)}")


def parse_labels(path: Path) -> list[dict[str, Any]]:
    raw = read_csv(path)
    require_fields(raw, ("Year", "City", "CityNormalized", "DEI"), "label CSV")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for number, row in enumerate(raw, start=2):
        year = int(row["Year"])
        city = row["CityNormalized"].strip()
        dei = float(row["DEI"])
        if not city or not math.isfinite(dei) or not 0 <= dei <= 100:
            raise MatchError(f"label row {number}: invalid city or DEI")
        key = (year, city)
        if key in seen:
            raise MatchError(f"label row {number}: duplicate year-city {key}")
        seen.add(key)
        rows.append(
            {
                "year": year,
                "label_city": row["City"].strip(),
                "normalized_city": city,
                "dei": dei,
            }
        )
    expected = {2017: 40, 2018: 100, 2019: 113, 2020: 220, 2021: 242, 2022: 242, 2023: 257, 2024: 260}
    counts = Counter(row["year"] for row in rows)
    if dict(sorted(counts.items())) != expected:
        raise MatchError(f"label annual counts changed: {dict(sorted(counts.items()))}")
    return rows


def parse_tntl(path: Path) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    raw = read_csv(path)
    require_fields(
        raw,
        (
            "Year",
            "BoundaryName",
            "BoundaryGB",
            "TNTL",
            "DatasetID",
            "Band",
            "PreprocessingID",
        ),
        "TNTL CSV",
    )
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    boundary_names: dict[str, set[str]] = defaultdict(set)
    for number, row in enumerate(raw, start=2):
        year = int(row["Year"])
        name = row["BoundaryName"].strip()
        code = row["BoundaryGB"].strip()
        tntl = float(row["TNTL"])
        if not name or not code or not math.isfinite(tntl) or tntl < 0:
            raise MatchError(f"TNTL row {number}: invalid identity or TNTL")
        key = (year, code)
        if key in seen:
            raise MatchError(f"TNTL row {number}: duplicate year-boundary {key}")
        seen.add(key)
        boundary_names[name].add(code)
        rows.append(
            {
                "year": year,
                "boundary_name": name,
                "boundary_gb": code,
                "tntl": tntl,
                "dataset_id": row["DatasetID"].strip(),
                "band": row["Band"].strip(),
                "preprocessing_id": row["PreprocessingID"].strip(),
            }
        )
    expected = len(range(2017, 2025)) * 375
    if len(rows) != expected:
        raise MatchError(f"expected {expected} TNTL rows, got {len(rows)}")
    if any(len(codes) != 1 for codes in boundary_names.values()):
        raise MatchError("boundary name maps to multiple gb codes")
    return rows, boundary_names


def resolve_boundary(city: str, boundary_names: dict[str, set[str]]) -> tuple[str, str, str]:
    if city in ALIAS_OVERRIDES:
        target = ALIAS_OVERRIDES[city]
        if target not in boundary_names:
            raise MatchError(f"explicit alias target is absent: {city} -> {target}")
        return target, next(iter(boundary_names[target])), "explicit_alias"
    candidates = sorted(name for name in boundary_names if name == city or name.startswith(city))
    if len(candidates) != 1:
        raise MatchError(f"{city}: expected one exact/prefix boundary match, got {candidates}")
    target = candidates[0]
    return target, next(iter(boundary_names[target])), "unique_exact_or_prefix"


def match(
    labels: list[dict[str, Any]],
    tntl_rows: list[dict[str, Any]],
    boundary_names: dict[str, set[str]],
    *,
    boundary_source: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    tntl_by_key = {(row["year"], row["boundary_gb"]): row for row in tntl_rows}
    training: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    matched_keys: set[tuple[int, str]] = set()
    for label in labels:
        year = label["year"]
        city = label["normalized_city"]
        quarantine_reason = QUARANTINE_LABELS.get((year, city))
        if quarantine_reason:
            row = {
                "Year": year,
                "LabelCity": label["label_city"],
                "CityNormalized": city,
                "DEI": format(label["dei"], ".15g"),
                "Status": "quarantined",
                "Reason": quarantine_reason,
            }
            quarantine.append(row)
            matches.append(
                {
                    **row,
                    "BoundaryName": "",
                    "BoundaryGB": "",
                    "MatchMethod": "none",
                    "TNTL": "",
                }
            )
            continue
        boundary_name, boundary_gb, method = resolve_boundary(city, boundary_names)
        key = (year, boundary_gb)
        if key in matched_keys:
            raise MatchError(f"duplicate matched year-boundary key {key}")
        source = tntl_by_key.get(key)
        if source is None:
            raise MatchError(f"missing TNTL for matched key {key}")
        if source["tntl"] <= 0:
            reason = "matched boundary has non-positive TNTL, incompatible with ln(TNTL)"
            row = {
                "Year": year,
                "LabelCity": label["label_city"],
                "CityNormalized": city,
                "DEI": format(label["dei"], ".15g"),
                "Status": "quarantined",
                "Reason": reason,
            }
            quarantine.append(row)
            matches.append(
                {
                    **row,
                    "BoundaryName": boundary_name,
                    "BoundaryGB": boundary_gb,
                    "MatchMethod": method,
                    "TNTL": format(source["tntl"], ".15g"),
                }
            )
            continue
        matched_keys.add(key)
        matches.append(
            {
                "Year": year,
                "LabelCity": label["label_city"],
                "CityNormalized": city,
                "DEI": format(label["dei"], ".15g"),
                "Status": "matched",
                "Reason": "",
                "BoundaryName": boundary_name,
                "BoundaryGB": boundary_gb,
                "MatchMethod": method,
                "TNTL": format(source["tntl"], ".15g"),
            }
        )
        training.append(
            {
                "city": boundary_name,
                "year": year,
                "dei": format(label["dei"], ".15g"),
                "tntl": format(source["tntl"], ".15g"),
                "dei_source": LABEL_SOURCE,
                "boundary_source": boundary_source,
                "ntl_product": f"{source['dataset_id']} band={source['band']}",
                "preprocessing_id": source["preprocessing_id"],
                "label_city": label["label_city"],
                "boundary_name": boundary_name,
                "boundary_gb": boundary_gb,
                "match_method": method,
                "year_semantics": "H3C IndexYear paired to same LongNTL calendar year by user instruction",
            }
        )
    training.sort(key=lambda row: (int(row["year"]), str(row["boundary_gb"])))
    matches.sort(key=lambda row: (int(row["Year"]), str(row["CityNormalized"])))
    quarantine.sort(key=lambda row: (int(row["Year"]), str(row["CityNormalized"])))
    return training, matches, quarantine


TRAINING_FIELDS = [
    "city",
    "year",
    "dei",
    "tntl",
    "dei_source",
    "boundary_source",
    "ntl_product",
    "preprocessing_id",
    "label_city",
    "boundary_name",
    "boundary_gb",
    "match_method",
    "year_semantics",
]
MATCH_FIELDS = [
    "Year",
    "LabelCity",
    "CityNormalized",
    "DEI",
    "Status",
    "Reason",
    "BoundaryName",
    "BoundaryGB",
    "MatchMethod",
    "TNTL",
]
QUARANTINE_FIELDS = ["Year", "LabelCity", "CityNormalized", "DEI", "Status", "Reason"]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=root / "data" / "dei_labels_2017_2024.csv")
    parser.add_argument("--tntl", type=Path, default=root / "data" / "city_tntl_longntl_2017_2024.csv")
    parser.add_argument(
        "--tntl-manifest",
        type=Path,
        default=root / "data" / "city_tntl_longntl_2017_2024_manifest.json",
    )
    parser.add_argument(
        "--training-output",
        type=Path,
        default=root / "data" / "dei_longntl_matched_2017_2024.csv",
    )
    parser.add_argument(
        "--match-output",
        type=Path,
        default=root / "data" / "dei_longntl_city_match.csv",
    )
    parser.add_argument(
        "--quarantine-output",
        type=Path,
        default=root / "data" / "dei_longntl_quarantine.csv",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=root / "data" / "dei_longntl_matching_manifest.json",
    )
    parser.add_argument(
        "--allow-quarantine",
        action="store_true",
        help="Emit the eligible matched subset while preserving quarantined rows separately.",
    )
    args = parser.parse_args()

    if not args.tntl_manifest.is_file():
        raise MatchError(f"missing TNTL manifest: {args.tntl_manifest}")
    source_manifest = json.loads(args.tntl_manifest.read_text(encoding="utf-8"))
    if source_manifest.get("status") != "complete":
        raise MatchError("TNTL extraction manifest is not complete")
    boundary = source_manifest.get("boundary") or {}
    boundary_source = (
        f"{BOUNDARY_ASSET}; update_time={boundary.get('update_time')}; "
        "source/licence/reference-year unresolved; one static layer used for all years"
    )
    labels = parse_labels(args.labels)
    tntl_rows, names = parse_tntl(args.tntl)
    training, matches, quarantine = match(
        labels, tntl_rows, names, boundary_source=boundary_source
    )
    if quarantine and not args.allow_quarantine:
        raise MatchError(
            f"{len(quarantine)} row(s) require quarantine; rerun with --allow-quarantine "
            "only if a matched-subset model is explicitly intended"
        )

    write_csv(args.training_output, training, TRAINING_FIELDS)
    write_csv(args.match_output, matches, MATCH_FIELDS)
    write_csv(args.quarantine_output, quarantine, QUARANTINE_FIELDS)
    counts = Counter(int(row["year"]) for row in training)
    status_counts = Counter(row["Status"] for row in matches)
    manifest = {
        "schema_version": "ntl-gpt.dei.longntl-matching.v1",
        "status": "matched_subset_complete_with_quarantine" if quarantine else "complete",
        "training_classification": "eligible_matched_subset",
        "year_semantics": (
            "H3C IndexYear is treated as the DEI model year and paired to the same "
            "LongNTL calendar year by explicit user instruction; official H3C publication "
            "semantics often describe the preceding natural year"
        ),
        "inputs": {
            "labels": {"path": str(args.labels.resolve()), "sha256": sha256_file(args.labels)},
            "tntl": {"path": str(args.tntl.resolve()), "sha256": sha256_file(args.tntl)},
            "tntl_manifest": {
                "path": str(args.tntl_manifest.resolve()),
                "sha256": sha256_file(args.tntl_manifest),
            },
        },
        "matching": {
            "input_label_rows": len(labels),
            "matched_training_rows": len(training),
            "quarantined_rows": len(quarantine),
            "status_counts": dict(sorted(status_counts.items())),
            "annual_training_counts": {str(year): counts[year] for year in sorted(counts)},
            "alias_overrides": ALIAS_OVERRIDES,
            "quarantine_policy": "never merge, average, or silently typo-correct conflicting city labels",
        },
        "outputs": {},
        "limitations": [
            "The 2023 model uses 256 eligible matched rows, not all 257 source labels, because 毫州 is quarantined.",
            "The boundary asset provenance and reference year are unresolved.",
            "Same-key H3C IndexYear/LongNTL pairing is user-defined and conflicts with common H3C publication-year semantics.",
        ],
    }
    for key, path, count in (
        ("training", args.training_output, len(training)),
        ("city_match", args.match_output, len(matches)),
        ("quarantine", args.quarantine_output, len(quarantine)),
    ):
        manifest["outputs"][key] = {
            "path": str(path.resolve()),
            "row_count": count,
            "sha256": sha256_file(path),
        }
    args.manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest["matching"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
