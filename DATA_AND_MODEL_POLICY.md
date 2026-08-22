# Data and Model Policy

This policy separates the NTL-GPT program-code license from data, models, knowledge assets, and runtime content. It is an ownership and redistribution boundary, not an additional restriction on code licensed under `AGPL-3.0-only`.

## Program Code

Unless a file contains a different license notice, original NTL-GPT program source code is licensed under `AGPL-3.0-only`. This includes the Streamlit application, agent orchestration, original tools, MCP servers, tests, and project-maintained setup scripts.

## Materials Not Automatically Covered by AGPL-3.0-only

The repository-level program-code license does not automatically grant rights in:

- satellite imagery, geographic boundaries, tables, or other datasets;
- model weights, serialized estimators, scalers, checkpoints, or training data;
- publications, abstracts, documentation imported from external sources, or other RAG corpora;
- generated embeddings, vector indexes, caches, database files, and derived search stores;
- third-party examples, reference implementations, copied API documentation, or vendor content;
- user uploads, account records, conversation history, generated research outputs, or workspace contents;
- API keys, tokens, credentials, service responses, or access rights to external platforms.

These materials remain subject to their original licenses, terms of use, database rights, privacy obligations, and attribution requirements. The presence of a file in this repository does not by itself establish permission to reuse or redistribute it.

## External Services and Datasets

Users are responsible for complying with the applicable terms and citation requirements of Google Earth Engine, NASA Earthdata, VIIRS products, AMap, model providers, boundary-data providers, and any other external service or dataset used through NTL-GPT.

API credentials and authenticated downloads must never be committed. Access supplied by NTL-GPT tooling does not transfer the underlying provider's redistribution rights.

## RAG and Generated Indexes

`RAG/` may contain a mixture of project-authored guidance, imported source material, and generated vector-store artifacts. Before publishing or redistributing a RAG asset:

1. identify every underlying source;
2. record its author, URL or identifier, version, and license;
3. confirm that redistribution and transformation are permitted;
4. preserve required attribution and notices; and
5. rebuild generated indexes from approved sources when provenance is incomplete.

An embedding or vector index does not replace the licensing obligations of its source material.

## Models and Runtime Assets

Every distributed model or serialized runtime asset should have a provenance record identifying its creator, training or source data where known, license, intended use, and redistribution status. An asset without confirmed redistribution permission should be obtained or generated during local setup rather than committed to a public release.

## User Content and Outputs

Users retain whatever rights they hold in their uploads and original content. NTL-GPT does not claim ownership of user content merely because the software processes or stores it.

Program output is not automatically covered by AGPL solely because it was produced by NTL-GPT. Output may nevertheless contain or derive from third-party data, code, models, or protected content, and users must evaluate those rights before publication or redistribution.

## Research Use

Nighttime-light and geospatial results require scientific validation. Users should cite the original datasets, algorithms, and publications used in an analysis. Citation is a research expectation, not an additional condition on the AGPL-licensed program code.

## Reporting Provenance Problems

Report missing attribution, unclear ownership, or suspected unauthorized material privately according to [SECURITY.md](SECURITY.md). Material with unresolved provenance may be removed from public distributions while its status is reviewed.
