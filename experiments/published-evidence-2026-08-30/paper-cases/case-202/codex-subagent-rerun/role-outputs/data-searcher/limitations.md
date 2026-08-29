# Q19 data-input limitations

- **Status: partial.** Internal package integrity and the required baseline reconstruction pass, but the result is bounded to the supplied snapshot.
- **No live refresh in this role run (unsupported):** no Earth Engine query or download was performed by this audit. The package query timestamp is `2026-08-13T17:13:48Z` and the actual product cutoff is `2026-08-02`; later/current availability is not established.
- **Product-date gaps (supported):** `14` of `214` calendar dates lack a product image: `2026-03-10, 2026-03-11, 2026-03-12, 2026-04-28, 2026-04-29, 2026-04-30, 2026-06-01, 2026-06-02, 2026-07-11, 2026-07-12, 2026-07-13, 2026-07-14, 2026-07-15, 2026-07-16`. They remain missing and were not interpolated or filled.
- **QA-validity gaps (supported):** for the required baseline, strict has `47` qualified days and `11` image-present zero-valid days; permissive has `48` qualified days and `10` image-present zero-valid days.
- **Coverage threshold (partial):** `qualified` means at least one QA-qualified pixel; no minimum coverage threshold is imposed. Downstream analysis must inspect `valid_fraction` and avoid treating a low-coverage day as equivalent to a well-covered day.
- **AOI semantics (supported limitation):** the geometry is a 2017 geoBoundaries ADM2 / canonical Shahrestan feature named City of Tehran, built in 2023. It is not a municipality or functional urban footprint by assertion.
- **Catalog verification boundary (partial):** product/band/QA claims were checked against local package fields, the extractor, the checkpoint band list, and the recorded official catalog URL; this role did not fetch the online catalog separately.
- **Event interpretation (unsupported here):** this data-searcher output does not verify event dates, rankings, event-window conclusions, causation, conflict attribution, outage, damage, recovery, or monitoring claims.
- **Simulation boundary (unsupported here):** nothing in these files proves deployed NTL-GPT, Deep Agents, runtime telemetry, four-role performance, or benchmark performance.

See [daily-series-audit.json](daily-series-audit.json) for exact checks and [q19-data-contract.json](q19-data-contract.json) for Analyst-facing selection rules.
