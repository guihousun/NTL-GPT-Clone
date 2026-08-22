# Runtime Tool Catalog (v1)

This directory is a safe refresh path for the NTL-GPT tool-oriented RAG source.
It is deliberately separate from the legacy code, solution, and literature
collections; the builder neither reads nor writes those collections or their
binary databases.

The catalog is not a second tool registry. Active role Skills, the allowlists
in `tools/__init__.py`, and the live registered tool schema are always the
authority. A catalog card may help an agent discover a relevant current tool,
but it cannot grant access to a role, change a tool contract, or justify a
call whose live schema does not validate.

## Build a reproducible snapshot

From the NTL-GPT runtime checkout:

```powershell
python RAG/runtime_tool_catalog/build_runtime_tool_catalog.py --check
python RAG/runtime_tool_catalog/build_runtime_tool_catalog.py
```

The second command creates an immutable directory under
`RAG/runtime_tool_catalog/v1/snapshots/`. Its name includes the Git HEAD and a
hash of `tools/__init__.py`, `agents/role_specs.py`, and every currently
registered tool module. Re-running against unchanged sources is byte-stable;
if the source changes, a new snapshot directory is created instead of
overwriting the old one.

Each snapshot contains:

- `manifest.json`: role boundaries, exported tools, static descriptions, and
  input-schema summaries;
- `tool_cards.ndjson`: one sanitized retrieval record per exported tool;
- `manifest.sha256`: the exact manifest digest;
- `collection_spec.json`: a non-executing recipe for a future collection.

The builder uses static AST parsing and the standard library only. It does not
import tool modules, execute GEE/API code, print environment variables, embed
tool source, emit machine-specific absolute paths, or mutate a Chroma store.

## Safe future activation

This refresh does **not** create or enable a vector-store collection. If a
future experiment needs one, create a new collection named from the snapshot's
`collection_spec.json`, record both `snapshot_id` and `manifest_sha256` in its
metadata, and bind it only to a graph/system snapshot with the same runtime
tool source hash. Do not modify or reuse a legacy collection.

At query time, use this order:

1. read the active role Skill and check the role's registered allowlist;
2. use the low-priority catalog only to discover a candidate tool or keyword;
3. re-read the live callable schema before invoking the tool;
4. ignore a retrieved card whenever it conflicts with the Skill, allowlist,
   or live schema.

This makes RAG a small supplementary retrieval aid, rather than a competing
source of workflow or scientific authority.
