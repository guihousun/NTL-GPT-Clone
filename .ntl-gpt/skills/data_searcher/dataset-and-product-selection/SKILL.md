---
name: ntl-data-searcher-dataset-and-product-selection
description: Select and validate the nighttime-light or auxiliary product, band, resolution, and source required by an accepted assignment.
---

# Dataset and Product Selection

- Preserve every explicit dataset ID and band unless NTL_Engineer approves a documented fallback.
- Validate asset type, band semantics, spatial resolution, units, temporal coverage, version, and source provenance before execution.
- Use `GEE_request_plan_tool` first for Earth Engine retrieval and follow its returned execution mode.
- Prefer official or validated sources and label community catalogs with provider, license, and warnings.
- Return `OBSERVATION_NOT_AVAILABLE` rather than substituting a scientifically different product silently.
