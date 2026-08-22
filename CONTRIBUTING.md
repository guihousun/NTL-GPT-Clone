# Contributing to NTL-GPT

Thank you for improving NTL-GPT. Focused issues and pull requests are easier to review and safer to integrate.

## Before You Start

1. Search existing issues and pull requests.
2. Keep one behavioral change per pull request.
3. Do not commit `.env`, credentials, downloaded private data, local workspaces, RAG rebuild artifacts, or browser/runtime caches.
4. Preserve the local thread workspace model and existing agent/tool ownership boundaries.

## Development Setup

```powershell
conda env create -f environment.yml
conda activate NTL-GPT-stable
Copy-Item .env.example .env
python check_env.py
```

Run the application with:

```powershell
python -m streamlit run Streamlit.py --server.address 127.0.0.1 --server.port 8501
```

## Engineering Expectations

- Prefer reusable capability changes over prompt-specific branches.
- Reuse existing tools before generating custom scripts.
- Resolve inputs and outputs through `storage_manager.py`.
- Keep `/shared` and `base_data` read-only unless a data-curation change explicitly requires otherwise.
- Keep routing changes coherent across `graph_factory.py`, `agents/`, `.ntl-gpt/skills/`, and `tools/__init__.py`.
- Document new environment variables in `.env.example`, `README.md`, and `check_env.py` together.

## Validation

Run the smallest relevant checks, then expand with the change's risk:

```powershell
python -m py_compile Streamlit.py app_logic.py app_agents.py graph_factory.py
python -m pytest tests -q
python -m pytest packages/ntl_toolkit/tests -q
```

For Streamlit changes, launch the application and verify the affected workflow in a browser. Routing and tool changes should cover the target scenario and at least one neighboring variation.

## Pull Requests

Describe:

- the problem and intended behavior;
- the implementation and important tradeoffs;
- validation commands and results;
- configuration or migration steps;
- screenshots for visible UI changes.

Do not include generated caches, personal workspaces, credentials, or unrelated formatting churn.

## Developer Certificate of Origin

All commits contributed to NTL-GPT must be signed off under the [Developer Certificate of Origin 1.1](DCO). The sign-off certifies that you have the right to submit the contribution under the repository's applicable license; it is not a copyright assignment.

Create signed-off commits with:

```powershell
git commit -s -m "Describe the change"
```

The resulting commit message must contain a line in this form:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use your own name and a valid email address. Pull requests containing unsigned commits may be asked to add the missing sign-offs before review.

## Licensing Contributions

Unless a file states otherwise, code contributions are submitted under `AGPL-3.0-only`. Do not contribute material copied from a dataset, model, publication, website, or another codebase unless its license permits inclusion and you preserve all required notices.

Data, models, RAG content, generated indexes, and third-party materials are governed by [DATA_AND_MODEL_POLICY.md](DATA_AND_MODEL_POLICY.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), not automatically by the repository's program-code license.
