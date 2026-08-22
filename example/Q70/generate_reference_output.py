"""Generate the frozen Q70 reference output with the checked-in core."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
PACKAGE_SRC = REPO_ROOT / "packages" / "ntl_toolkit" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from ntl_toolkit.core.urban_structure import CHEN2017_SHANGHAI_2014_CONFIG, detect_urban_centres  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(root: Path) -> Path:
    manifest = root / "SHA256SUMS.txt"
    lines = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == manifest:
            continue
        relative = path.relative_to(root).as_posix()
        lines.append(f"{sha256(path)}  {relative}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return manifest


def clear_reference_outputs(output: Path) -> None:
    """Remove only this script's deterministic output names before a rebuild."""

    output.mkdir(parents=True, exist_ok=True)
    for path in output.glob("urban_centres*"):
        if path.is_file():
            path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    inputs = root / "inputs"
    output = root / "reference_output"
    clear_reference_outputs(output)
    result = detect_urban_centres(
        inputs / "ntl_shanghai_2014_12_v1_albers_500m.tif",
        inputs / "shanghai_boundary.geojson",
        output / "urban_centres.geojson",
        output / "urban_centres.csv",
        output / "urban_centres.metadata.json",
        parameter_profile=CHEN2017_SHANGHAI_2014_CONFIG["profile"],
    )
    if result.status != "succeeded":
        raise SystemExit(f"Q70 reference generation failed: {result.summary}")
    manifest = write_manifest(root)
    summary = {
        "status": result.status,
        "summary": result.summary,
        "metrics": result.metrics,
        "output_directory": str(output),
        "sha256_manifest": str(manifest),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
