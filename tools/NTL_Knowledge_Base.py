"""Retriever tools for NTL knowledge stores."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.tools import StructuredTool, create_retriever_tool
from utils.ntl_embeddings import create_text_embeddings


load_dotenv()


def _resolve_rag_persist_dir(store_name: str) -> str:
    """
    Resolve RAG store path in a cwd-independent way.

    Priority:
    1) NTL_RAG_ROOT env (absolute recommended), e.g. D:\\NTL-GPT\\NTL-GPT-Clone\\RAG
    2) repository-root/RAG (derived from this file location)
    """
    env_root = str(os.getenv("NTL_RAG_ROOT", "") or "").strip()
    if env_root:
        root = Path(env_root).expanduser().resolve()
    else:
        root = Path(__file__).resolve().parents[1] / "RAG"
    return str((root / store_name).resolve())


def _empty_store_response(store_name: str, query: str) -> str:
    return json.dumps(
        {
            "status": "empty_store",
            "store": store_name,
            "reason": f"{store_name} currently has no indexed documents.",
            "query": query,
        },
        ensure_ascii=False,
    )


def _unavailable_store_response(store_name: str, query: str, exc: Exception) -> str:
    """Return a safe, non-blocking response for an optional knowledge store.

    Chroma persistent stores can be mounted read-only in a benchmark worker, or
    be temporarily locked by a different process.  The knowledge base is an
    optional source of supplemental context, so its storage implementation
    details must not terminate a task (or disclose host paths to the model).
    """

    return json.dumps(
        {
            "status": "knowledge_unavailable",
            "store": store_name,
            "reason_code": "supplemental_store_unavailable",
            "error_type": type(exc).__name__,
            "message": "Supplemental knowledge retrieval is unavailable for this call.",
            "fallback": "Continue with the active role Skills and registered tools.",
            "query": query,
        },
        ensure_ascii=False,
    )


def _build_retriever_tool(
    *,
    collection_name: str,
    persist_directory: str,
    tool_name: str,
    description: str,
    embeddings: Any | None,
    k: int,
    score_threshold: float,
) -> StructuredTool:
    """Build a lazily opened, read-safe Chroma retrieval tool.

    Tool registration happens while the runtime graph is constructed.  Opening
    a persistent Chroma collection at that point can try to create or update
    local metadata and used to make unrelated local tasks fail when the store
    was read-only.  Defer opening until the tool is actually selected, never
    request collection creation, and turn a store exception into an explicit
    supplemental-knowledge fallback.
    """

    def _retrieve(query: str) -> str:
        store_path = Path(persist_directory)
        if not store_path.is_dir():
            return _empty_store_response(collection_name, query)

        try:
            vector_store = Chroma(
                collection_name=collection_name,
                persist_directory=persist_directory,
                embedding_function=(
                    embeddings if embeddings is not None else create_text_embeddings()
                ),
                create_collection_if_not_exists=False,
            )
            count = vector_store._collection.count()
            if count == 0:
                return _empty_store_response(collection_name, query)

            retriever = vector_store.as_retriever(
                search_type="similarity_score_threshold",
                search_kwargs={"k": k, "score_threshold": score_threshold},
            )
            retriever_tool = create_retriever_tool(retriever, name=tool_name, description=description)
            return retriever_tool.invoke({"query": query})
        except Exception as exc:
            return _unavailable_store_response(collection_name, query, exc)

    return StructuredTool.from_function(
        func=_retrieve,
        name=tool_name,
        description=description,
    )


NTL_Literature_Knowledge = _build_retriever_tool(
    collection_name="Literature_RAG",
    persist_directory=_resolve_rag_persist_dir("Literature_RAG"),
    tool_name="NTL_Literature_Knowledge",
    description=(
        "Use this tool to retrieve peer-reviewed academic literature related to "
        "Nighttime Light (NTL) remote sensing. Includes theory, equations, and "
        "scientific definitions."
    ),
    embeddings=None,
    k=2,
    score_threshold=0.33,
)


NTL_Solution_Knowledge = _build_retriever_tool(
    collection_name="Solution_RAG",
    persist_directory=_resolve_rag_persist_dir("Solution_RAG"),
    tool_name="NTL_Solution_Knowledge",
    description=(
        "Use this tool to retrieve structured workflows, tool usage guides, "
        "dataset access instructions, and end-to-end NTL application solutions."
    ),
    embeddings=None,
    k=3,
    score_threshold=0.3,
)


def _code_rag_disabled(query: str) -> str:
    return json.dumps(
        {
            "status": "disabled_store",
            "store": "Code_RAG",
            "reason": (
                "The legacy code corpus is excluded from the formal runtime until "
                "it is rebuilt and snapshot-bound against the unified GEE runtime."
            ),
            "query": query,
        },
        ensure_ascii=False,
    )


# Compatibility export only. Do not open the legacy Code_RAG database at import
# time: current agents use role Skills and registered tools for executable code.
NTL_Code_Knowledge = StructuredTool.from_function(
    func=_code_rag_disabled,
    name="NTL_Code_Knowledge",
    description="Compatibility stub for the disabled legacy Code_RAG corpus.",
)
