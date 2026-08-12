---
name: ntl-data-searcher-gee-earthdata-acquisition
description: Execute validated Google Earth Engine, Earthdata, LAADS, CMR, direct-download, or batch-export acquisition plans.
---

# GEE and Earthdata Acquisition

- Execute the accepted route: direct local export, server-side reduction, batch export, or audited official-product retrieval.
- For large AOIs, many features, or long series, prefer server-side reduction or batch export rather than downloading all source rasters.
- A submitted batch job is planned, not complete. Preserve job ID and manifest and verify final state before claiming completion.
- For official HDF retrieval preserve granule audit, mosaics, retry targets, and product provenance; distinguish no granules from transport failure.
- Never expose credentials or claim an artifact before its actual path and non-empty content are validated.
