from __future__ import annotations

import json
from pathlib import Path

from ntl_toolkit.core import boundary
from ntl_toolkit.core.boundary import GeoBoundaryDownloadRequest, download_geoboundary


def _feature_collection() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"shapeName": "Tehran"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
            {
                "type": "Feature",
                "properties": {"shapeName": "Isfahan"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
        ],
    }


def test_download_geoboundary_filters_and_writes_geojson(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "irn_adm1.geojson"

    def fake_read(url: str, *, timeout: int) -> dict:
        assert timeout == 30
        if "/api/current/" in url:
            return {"gjDownloadURL": "https://example.test/irn-adm1.geojson"}
        return _feature_collection()

    monkeypatch.setattr(boundary, "_read_json_url", fake_read)
    result = download_geoboundary(
        GeoBoundaryDownloadRequest(
            iso3="irn",
            adm_level=1,
            output=str(output),
            place_name="teh",
            timeout=30,
        )
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result.status == "succeeded"
    assert result.metrics["iso3"] == "IRN"
    assert result.metrics["feature_count"] == 1
    assert payload["features"][0]["properties"]["shapeName"] == "Tehran"


def test_download_geoboundary_reuses_valid_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "irn_adm1.geojson"
    output.write_text(json.dumps(_feature_collection()), encoding="utf-8")

    result = download_geoboundary(
        GeoBoundaryDownloadRequest(
            iso3="IRN",
            adm_level=1,
            output=str(output),
        )
    )

    assert result.status == "succeeded"
    assert result.metrics["downloaded"] is False
    assert result.metrics["feature_count"] == 2


def test_download_geoboundary_returns_structured_failure_for_empty_match(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        boundary,
        "_read_json_url",
        lambda url, *, timeout: (
            {"gjDownloadURL": "https://example.test/irn-adm1.geojson"}
            if "/api/current/" in url
            else _feature_collection()
        ),
    )

    result = download_geoboundary(
        GeoBoundaryDownloadRequest(
            iso3="IRN",
            adm_level=1,
            output=str(tmp_path / "missing.geojson"),
            place_name="not-a-place",
        )
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "GEOBOUNDARY_DOWNLOAD_FAILED"
    assert not (tmp_path / "missing.geojson").exists()
