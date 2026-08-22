# Third-Party Notices

NTL-GPT depends on third-party software, services, datasets, models, documentation, and research materials. Those components remain governed by their respective copyright notices, licenses, and terms. The NTL-GPT `AGPL-3.0-only` license applies only where the project has authority to grant it.

## Python and System Dependencies

Python packages and native libraries installed through `environment.yml`, package metadata, or platform setup retain their own licenses. Installing a dependency does not relicense it under AGPL-3.0-only. Distributors must preserve the notices required by the exact dependency versions they ship.

## External Platforms and Data Providers

NTL-GPT can connect to services and datasets including Google Earth Engine, NASA Earthdata and VIIRS products, AMap, PostgreSQL, language-model providers, and geographic-boundary providers. Their names identify interoperability only and do not imply endorsement or transfer of content rights.

Users and redistributors must review the provider terms, dataset licenses, attribution requirements, access controls, and export or redistribution restrictions applicable to their use.

## Repository Assets Requiring Provenance Review

The following classes require file-level provenance confirmation before they are included in a public binary, dataset bundle, or downstream redistribution:

- imported or mirrored content under `RAG/`;
- generated Chroma or other vector-database artifacts;
- external API documentation and reference examples;
- serialized models, scalers, and checkpoints under `assets/` or other paths;
- shared boundary, raster, tabular, and research data;
- sample outputs derived from third-party data.

Until a material has an explicit compatible license or provenance record, no redistribution permission should be inferred from its presence in the repository.

## Adding Third-Party Material

Every new third-party material committed to the repository should include or reference:

- component or dataset name and version;
- copyright holder or provider;
- canonical source URL or persistent identifier;
- license or terms URL;
- required attribution;
- whether modification and redistribution are allowed; and
- the repository files derived from that material.

See [DATA_AND_MODEL_POLICY.md](DATA_AND_MODEL_POLICY.md) for the project-wide handling policy. If a component's terms conflict with AGPL-3.0-only or prohibit redistribution, keep it separate and obtain it during local setup instead of bundling it with the program.
