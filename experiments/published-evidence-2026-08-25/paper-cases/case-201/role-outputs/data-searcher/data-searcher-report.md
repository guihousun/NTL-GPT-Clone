# CASE-201 Data Searcher report

**Execution context:** Codex-subagent simulation. This is bounded evidence work, not a deployed NTL-GPT / Deep Agents runtime trace. No model call, runtime telemetry, GEE/LAADS/CMR call, or download was performed.

## Verdict

The exact UTC-indexed first-night product date **2025-03-28 is present and qualified for both formal Q18 supports**. The terminal exact-date gate therefore passes as `qualified_both_supports`; no later date was substituted.

The case contract maps the event at `2025-03-28T06:20:52Z` (`2025-03-28 12:50:52 Asia/Yangon`) to the interpreted local first night `2025-03-29`. The candidate local acquisition interval `00:30–02:30` MMT maps to `18:00–20:00Z` on `2025-03-28`, so the UTC-indexed product date is `2025-03-28`. The HDF does not expose an exact pixel acquisition time.

## Product and file identity

| Field | Verified value |
|---|---|
| Product / collection | `VNP46A2` / `002` |
| Band | `DNB_BRDF-Corrected_NTL` |
| Band path | `HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/DNB_BRDF-Corrected_NTL` |
| HDF filename | `VNP46A2.A2025087.h27v06.002.2025095151403.h5` |
| UTC date | filename `A2025087`, HDF `RangeBeginningDate=2025-03-28` |
| Tile | `h27v06` |
| Bytes / SHA-256 | `34,468,952` / `d5b56523344d2407eefe0180b9399c14fe7f56400b0e32c0869ee8f3812e17de` |

The target HDF exists locally; its SHA-256 matches the Q18 inventory and both target CSV rows. Direct HDF inspection confirmed the product, collection, band, band attributes, and all three strict-QA datasets (`Mandatory_Quality_Flag`, `QF_Cloud_Mask`, `Snow_Flag`).

## Exact-date strict-QA audit

The formal Q18 mask requires finite, non-fill, non-negative radiance; `Mandatory_Quality_Flag == 0`; valid night/medium-or-high/clear cloud-mask bits; no shadow, cirrus, cloud-mask snow, aurora, or lunar eclipse; and `Snow_Flag == 0`.

| Support | AOI pixels | `qa_valid_pixel_count` | QA valid fraction | Nonempty radiance mean (nW cm^-2 sr^-1) | Gate |
|---:|---:|---:|---:|---:|---|
| 25 km | 9,895 | 9,802 | 0.9906013137948458 | 1.0435125119745428 | **PASS** |
| 50 km | 39,575 | 39,330 | 0.9938092229943146 | 0.8748512739786589 | **PASS** |

I independently re-read the target HDF and recomputed the WGS84 pixel-centre masks and strict QA means with `h5py`, `numpy`, and `pyproj.Geod(ellps="WGS84")`; all three values for both supports match the formal CSV exactly.

If either support had failed on `2025-03-28`, the required result would have been `no_eligible_first_night_observation`; silently replacing it with a later date would violate the case contract. Here both supports pass, so the result is not partial or failed.

## Evidence files

- [product-eligibility.json](product-eligibility.json) — exact-date decision and support values.
- [input-integrity.json](input-integrity.json) — source hashes, HDF metadata, and independent readback/recompute checks.
- [skill-usage-evidence.json](skill-usage-evidence.json) — frozen date-boundary Skill rules applied, with runtime-simulation disclosure.
- [artifact-manifest.json](artifact-manifest.json) — output hashes and provenance manifest.

Limitations remain: local first-night timing is a documented candidate-window interpretation, not an exact pixel timestamp; the result is observational eligibility evidence and does not establish outage, damage, recovery, earthquake causation, or deployed-runtime performance.
