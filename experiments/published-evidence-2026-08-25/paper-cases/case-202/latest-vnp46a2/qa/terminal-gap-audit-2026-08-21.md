# Case 202 terminal-gap audit — 21 August 2026

Status: **PASS**.

This is an independent Codex-subagent audit of the current Case 202 terminal data and figure state. It does not modify the analysis, source data, figure outputs, manuscript, registry, or formal benchmark.

## Data endpoint

The current `gee-checkpoint.json` records:

- GEE collection: `NASA/VIIRS/002/VNP46A2`;
- live collection image endpoint: **2026-08-19 UTC**;
- query time: `2026-08-21T09:10:22Z`;
- latest strict-qualified Tehran ADM2 observation: **2026-08-12 UTC**.

The last strict daily value is 59.868755595489105 nW cm^-2 sr^-1 from 2,644 valid pixels. In `daily-vnp46a2.csv`, every row from 13–19 August is present as an image record but is unqualified in both strict and permissive modes, with a blank mean and zero valid/total pixel counts. The direct raw GEE supplements independently report 2,644 pixels on 12 August and zero server-side raw pixels on 13–19 August; the 19 August export is explicitly marked `downloaded_all_masked`.

## Terminal connectors

The terminal grey connector now uses the same grey-gap style contract in both the plotting source and the exported SVG: `DAILY_GREY` (`#9EA5AD`), width `0.65`, dash pattern `(0, (2, 2))`, alpha `0.72`, and the grey gap-connector visual layer. The current SVG endpoint geometry is:

- grey daily connector: `M 472.273846 99.59273 L 485.740792 99.59273`, reaching the 2026-08-19 endpoint;
- blue 14-day connector: `M 472.273846 105.187966 L 485.740792 105.187966`, stroke `#1a5aa3`, dashed.

Both paths share the same terminal x-coordinate and are structurally connected from the final supported date to the displayed endpoint. They are visual missing-data connectors only; they are not imputed observations and are excluded from the numerical summaries.

The current SVG embeds the restored matching style, and the current PNG was visually re-opened after export. The grey segment is present and reaches the right-hand 2026-08-19 endpoint.

## Audit conclusion

The endpoint and missing-data semantics are internally consistent: GEE has a product record through 19 August, usable strict Tehran values end on 12 August, and 13–19 August remain explicit gaps. The current SVG and PNG contain both terminal connectors reaching the 19 August endpoint with the restored matching grey-gap style.
