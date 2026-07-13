# VNP46A1 Official HDF5 Download Design

## Goal

Extend the local-only `ntl-download` stdio MCP with audited Earthdata VNP46A1
downloads. It must produce one daily, clipped GeoTIFF per requested country or
bounding-box target, preserve raw HDF5 provenance, stream progress, and support
manifest-based inspection and exact retries.

VNP46A1 is kept distinct from VNP46A2. Its primary raster is daily
top-of-atmosphere DNB radiance `DNB_At_Sensor_Radiance_500m`; it is not a
BRDF-corrected or gap-filled nighttime-light product.

## Scope

Add one MCP write tool:

| Tool | Input mode | Primary output |
| --- | --- | --- |
| `download_vnp46a1_official_h5` | Exactly one of ISO3 `countries` or WGS84 `bbox` | Daily clipped float32 GeoTIFFs of `DNB_At_Sensor_Radiance_500m` |

The tool has the same `plan`, `prepare`, `download`, `mosaic`, `audit`, and
`full` modes as the VNP46A2 pipeline. It uses `EARTHDATA_TOKEN` only from the
process environment or `NTL_MCP_ENV_FILE`, emits MCP progress, and writes
sanitized manifests. `inspect_download_run` becomes product-aware and can read
both VNP46A1 and VNP46A2 audit files.

The scope excludes VNP46A1 BRDF correction, gap filling, radiometric
cross-calibration, event attribution, a remote service, job queue, database,
or automatic OAuth.

## Target Contract

`countries` accepts one or more ISO3 codes and uses the existing simplified
OSM admin-0 boundary workflow. `bbox` is `[minx, miny, maxx, maxy]` in WGS84,
requires `-180 <= minx < maxx <= 180` and `-90 <= miny < maxy <= 90`, and is
saved as a local target GeoJSON during `prepare`.

Each target receives a stable target id:

- Country mode: its ISO3 code, for example `ISR`.
- BBox mode: `BBOX_<sha256-prefix>` derived from the normalized bbox. The
  normalized coordinates are also retained in every manifest and GeoTIFF tag.

Exact retry targets use `TARGET_ID:YYYY-MM-DD`. Country mode therefore remains
compatible with the existing `ISR:2026-02-13` convention. BBox targets are
accepted only when they match the current run's generated target id.

## VNP46A1 Processing

The download stage queries CMR with short name `VNP46A1`, requested date, and
the target bbox, then downloads matching official HDF5 granules with the
Earthdata token. Acquisition-day tokens in producer granule names remain the
authoritative day assignment.

The mosaic stage reads `DNB_At_Sensor_Radiance_500m` from the HDF5 grid,
applies source `_FillValue`, `scale_factor`, and `add_offset`, derives its
geographic transform from authoritative HDF-EOS bounding metadata, mosaics
all target-day tiles, clips to the prepared target geometry, and writes a
float32 WGS84 GeoTIFF with nodata `-9999`. It does not use VNP46A2 tile-grid
assumptions.

## UTC_Time

VNP46A1's `UTC_Time` is an optional companion layer. A caller may set
`include_utc_time=true`; then the mosaic phase also writes a separately named
float32 `UTC_Time` GeoTIFF clipped to the same target. It records decimal UTC
hours at each valid pixel and is never used as radiance, aggregated into the
primary radiance output, or silently treated as a local-night date.

The manifests and `ntl-gpt-project` skill state that `UTC_Time` is for
acquisition-time/date-boundary validation. It should be used when an event is
near a UTC boundary; users must inspect its valid range and document the
chosen date rule. It is optional because it increases per-day raster output
and is unnecessary for ordinary radiance retrieval.

## Audit and Errors

The audit distinguishes `mosaic_valid`, `no_granules`, `mosaic_all_nodata`,
`retry_download`, `downloaded_without_mosaic`, and `not_processed`. A run is
complete only when `downloaded_without_mosaic`, `retry_download`, and
`not_processed` are all zero. `no_granules` means product availability, not a
transport failure. `mosaic_all_nodata` is terminal only after valid HDF5,
successful mosaic execution, and a radiance pixel scan.

All phase output and stored manifests use existing bearer-token redaction.
The tool returns only `EARTHDATA_TOKEN` presence, never its value.

## Architecture

The existing VNP46A2 core remains unchanged. Add a focused VNP46A1 core and a
small `tools/vnp46a1_official_h5/` script package. The new package can reuse
the established CMR client and country boundary helpers but owns product
metadata, bbox target preparation, HDF5 dataset discovery, and geographic-grid
conversion. This prevents VNP46A1-specific scale, grid, or QA assumptions from
changing the proven VNP46A2 pipeline.

The MCP adapter gains explicit VNP46A1 schema handling; its client schema stays
sealed and does not expose an Earthdata token argument. Documentation and the
global `ntl-gpt-project` skill route VNP46A1 requests to this new tool, while
the older general BBox downloader remains a legacy raw-download utility.

## Validation

Tests use synthetic HDF5 files with VNP46A1 metadata to verify radiance scaling,
nodata, WGS84 transforms, target clipping, optional `UTC_Time`, target-mode
validation, audit retry parsing, command construction, MCP schema sealing,
credential redaction, and package-data inclusion. Existing VNP46A2 tests run
unchanged as regression coverage.
