from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, field_validator

from ntl_toolkit.runtime.paths import reserve_output_path
from ntl_toolkit.schemas import OutputArtifact, ToolError, ToolResult


GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM{adm}/"


class GeoBoundaryDownloadRequest(BaseModel):
    iso3: str = Field(..., description="ISO 3166-1 alpha-3 country code.")
    adm_level: int = Field(..., ge=0, le=4)
    output: str
    place_name: str | None = None
    reuse_existing: bool = True
    timeout: int = Field(default=90, ge=1, le=600)

    @field_validator("iso3")
    @classmethod
    def normalize_iso3(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("iso3 must be a three-letter ISO country code")
        return normalized

    @field_validator("output")
    @classmethod
    def require_geojson_output(cls, value: str) -> str:
        output = str(value or "").strip()
        if not output:
            raise ValueError("output is required")
        if Path(output).suffix.lower() not in {".geojson", ".json"}:
            raise ValueError("output must use a .geojson or .json suffix")
        return output


def _read_json_url(url: str, *, timeout: int) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "ntl-toolkit/0.1"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return payload


def _filter_features(payload: dict[str, Any], place_name: str | None) -> dict[str, Any]:
    features = payload.get("features")
    if payload.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise ValueError("Downloaded boundary is not a GeoJSON FeatureCollection")

    target = str(place_name or "").strip().casefold()
    if not target:
        selected = features
    else:
        selected = []
        for feature in features:
            properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
            shape_name = str(properties.get("shapeName", "")).strip()
            if target in shape_name.casefold():
                selected.append(feature)
    if not selected:
        suffix = f" matching place_name={place_name!r}" if target else ""
        raise ValueError(f"Boundary response contains no features{suffix}")

    return {**payload, "features": selected}


def download_geoboundary(request: GeoBoundaryDownloadRequest) -> ToolResult:
    """Download one geoBoundaries gbOpen administrative layer as GeoJSON."""
    tool = "download_geoboundary"
    requested_output = Path(request.output).expanduser().resolve(strict=False)

    try:
        if request.reuse_existing and requested_output.exists():
            existing = json.loads(requested_output.read_text(encoding="utf-8"))
            selected = _filter_features(existing, request.place_name)
            return ToolResult.succeeded(
                tool=tool,
                summary="Reused an existing validated geoBoundaries GeoJSON file.",
                outputs=[OutputArtifact(path=str(requested_output), media_type="application/geo+json")],
                metrics={
                    "iso3": request.iso3,
                    "adm_level": request.adm_level,
                    "feature_count": len(selected["features"]),
                    "downloaded": False,
                },
            )

        output = requested_output if not requested_output.exists() else reserve_output_path(requested_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        metadata_url = GEOBOUNDARIES_API.format(iso3=request.iso3, adm=request.adm_level)
        metadata = _read_json_url(metadata_url, timeout=request.timeout)
        download_url = str(metadata.get("gjDownloadURL") or "").strip()
        if not download_url:
            raise ValueError("geoBoundaries metadata does not contain gjDownloadURL")

        boundary = _filter_features(
            _read_json_url(download_url, timeout=request.timeout),
            request.place_name,
        )
        temporary = output.with_suffix(f"{output.suffix}.part")
        temporary.write_text(
            json.dumps(boundary, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(output)
        return ToolResult.succeeded(
            tool=tool,
            summary="Downloaded and validated a geoBoundaries administrative layer.",
            outputs=[OutputArtifact(path=str(output), media_type="application/geo+json")],
            metrics={
                "iso3": request.iso3,
                "adm_level": request.adm_level,
                "place_name": request.place_name or "",
                "feature_count": len(boundary["features"]),
                "downloaded": True,
                "source": download_url,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        return ToolResult.failed(
            tool=tool,
            error=ToolError(
                code="GEOBOUNDARY_DOWNLOAD_FAILED",
                message="Unable to download or validate the requested administrative boundary.",
                details={
                    "iso3": request.iso3,
                    "adm_level": request.adm_level,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                suggestion=(
                    "Verify the ISO3 code and ADM level, check network access to geoboundaries.org, "
                    "and retry with a .geojson output path."
                ),
            ),
        )
