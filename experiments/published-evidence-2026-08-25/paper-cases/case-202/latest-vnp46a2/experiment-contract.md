# Case 202 extension contract

**Core conclusion.** The existing administrative-AOI daily VNP46A2 series is
displayed and summarized through the latest GEE UTC product date returned at
execution. Numeric ANTL summaries retain only strict-QA-qualified City of
Tehran observations; a later product day with no valid City pixel remains an
explicit gap. Fixed comparison windows remain unchanged.

**Input reuse.** The extraction implementation is imported from the prior Q19
data-stage script without modifying that source. The event timeline is copied
as a dated context record and is not represented as a fresh live source search.

**Figure contract.**

- Archetype: single-panel quantitative time series.
- Hero evidence: strict-QA daily City of Tehran ADM2 mean radiance and its
  14-day observed-data summary.
- Supporting evidence: background fixed-window semantics. The surrounding
  Draw.io composition, not this standalone chart, owns legend and timeline
  annotation.
- Backend: Python / matplotlib.
- Final exports: SVG, PDF, 600 dpi PNG, and 600 dpi LZW TIFF.
- No plot title, subtitle, in-plot legend, event marker, Draw.io panel,
  event-count bar chart, or bottom explanatory prose is included in the
  rendered figure. Axis and tick typography is enlarged 1.5× relative to the
  prior standalone revision.

**Acceptance checks.**

1. The output series has one strict and one permissive row for every UTC date
   from 2026-01-01 through the live collection endpoint; the plotted and
   extended-monitoring time span ends at that endpoint, while numeric ANTL
   rows remain limited to strict-qualified City observations.
2. No unqualified row has a numerical radiance value.
3. The latest collection date and latest strict-qualified date are recorded
   separately.
4. Fixed window summaries are recomputed from the new table rather than copied.
5. The 14-day display line is supported by at least three actual observations
   in every displayed trailing window. Any dashed horizontal extension is a
   documented missing-data connector, not a statistical or imputed value.
6. Existing Q19 and manuscript/figure assets are read-only inputs.
