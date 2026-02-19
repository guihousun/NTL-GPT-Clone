from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings


HASH_PREFIX_RE = re.compile(r"^[0-9a-f]{12}_", re.IGNORECASE)
NOISE_NAME_MARKERS = (
    "dedupe_case",
    "repeat_fail_case",
    "execute_dedupe_case",
    "final_geocode_",
    "execute_case",
    "cot_block_",
)


@dataclass
class RuntimeCandidate:
    py_path: Path
    meta_path: Path | None
    base_name: str
    category: str
    score: float
    reason: str
    stdout_excerpt: str


def _strip_hash_prefix(file_name: str) -> str:
    return HASH_PREFIX_RE.sub("", file_name)


def _classify_category(name: str, code: str = "", stdout_excerpt: str = "") -> str:
    low = name.lower()
    low_code = (code or "").lower()
    low_stdout = (stdout_excerpt or "").lower()
    if "earthquake" in low or "impact" in low:
        return "disaster_assessment"
    if "gdp" in low and "regression" in low:
        return "gdp_ntl_regression"
    if "wuhan" in low and "lockdown" in low:
        return "lockdown_comparison"
    if "brightest_district" in low or ("brightest" in low and "district" in low):
        return "district_ranking"
    if (
        ("district" in low_code or "district" in low_stdout)
        and "reduceregions(" in low_code
    ):
        return "district_zonal_stats"
    if "district" in low and "antl" in low:
        return "district_zonal_stats"
    if "trend" in low or "slope" in low or "cagr" in low or "growth" in low:
        return "trend_analysis"
    if "anomaly" in low:
        return "anomaly_detection"
    return "other"


def _topic_tags_from_text(text: str) -> str:
    low = (text or "").lower()
    tags: set[str] = set()
    rules = {
        "ntl": [r"\bntl\b", r"nighttime light", r"antl"],
        "viirs": [r"\bviirs\b", r"npp-viirs", r"vnp46a2"],
        "gee": [r"earth engine", r"\bee\."],
        "geopandas": [r"\bgeopandas\b"],
        "rasterio": [r"\brasterio\b"],
        "gdp": [r"\bgdp\b"],
        "regression": [r"\bregression\b", r"\bols\b", r"\br2\b"],
        "disaster": [r"earthquake", r"impact", r"blackout", r"recovery", r"flood", r"wildfire"],
    }
    for tag, patterns in rules.items():
        if any(re.search(p, low) for p in patterns):
            tags.add(tag)
    if not tags:
        tags.add("general_code")
    return ",".join(sorted(tags))


def _normalize_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _doc_hash(page_content: str, metadata: dict[str, Any]) -> str:
    key = json.dumps(
        {
            "content": _normalize_for_hash(page_content),
            "doc_type": str(metadata.get("doc_type", "")),
            "symbol": str(metadata.get("symbol", "")),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _safe_read_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return path.read_text(errors="ignore")


def _extract_symbols(py_path: Path) -> list[dict[str, str]]:
    source = _safe_read_text(py_path)
    tree = ast.parse(source)
    lines = source.splitlines()
    symbols: list[dict[str, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if getattr(node, "name", "").startswith("_"):
            continue
        start = getattr(node, "lineno", 1) - 1
        end = getattr(node, "end_lineno", start + 1)
        code = "\n".join(lines[start:end]).strip()
        signature = ""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                signature = f"{node.name}({ast.unparse(node.args)})"
            except Exception:
                signature = f"{node.name}(...)"
        symbols.append(
            {
                "name": node.name,
                "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                "signature": signature,
                "docstring": ast.get_docstring(node) or "",
                "code": code,
            }
        )
    return symbols


def _compute_score(py_name: str, code: str, stdout_excerpt: str) -> tuple[float, str]:
    low_name = py_name.lower()
    low_code = code.lower()
    low_stdout = (stdout_excerpt or "").lower()

    if any(marker in low_name for marker in NOISE_NAME_MARKERS):
        return -100.0, "noise_name_marker"
    if "run_once_is_enough" in low_stdout:
        return -50.0, "test_artifact_stdout"
    if "traceback" in low_stdout or "error" in low_stdout and "saved" not in low_stdout:
        return -20.0, "error_in_stdout"

    score = 0.0
    score += min(len(code) / 700.0, 20.0)
    if "ee.initialize" in low_code:
        score += 6
    if "reduceregions(" in low_code:
        score += 6
    if "storage_manager.resolve_input_path" in low_code:
        score += 4
    if "storage_manager.resolve_output_path" in low_code:
        score += 4
    if ".to_csv(" in low_code:
        score += 3
    if "regression" in low_code:
        score += 3
    if "earthquake" in low_code or "impact" in low_code:
        score += 2
    if "output saved" in low_stdout or "saved to" in low_stdout:
        score += 2
    return score, "ok"


def _load_candidate(runtime_dir: Path, py_path: Path) -> RuntimeCandidate:
    stem = py_path.stem
    meta_path = runtime_dir / f"{stem}.meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(_safe_read_text(meta_path))
        except Exception:
            meta = {}
    stdout_excerpt = str(meta.get("stdout_excerpt", "") or "")
    code = _safe_read_text(py_path)
    score, reason = _compute_score(py_path.name, code, stdout_excerpt)
    base_name = _strip_hash_prefix(py_path.name)
    category = _classify_category(base_name, code=code, stdout_excerpt=stdout_excerpt)
    return RuntimeCandidate(
        py_path=py_path,
        meta_path=meta_path if meta_path.exists() else None,
        base_name=base_name,
        category=category,
        score=score,
        reason=reason,
        stdout_excerpt=stdout_excerpt,
    )


def _gather_candidates(runtime_dir: Path) -> list[RuntimeCandidate]:
    items: list[RuntimeCandidate] = []
    for py_path in sorted(runtime_dir.glob("*.py")):
        items.append(_load_candidate(runtime_dir, py_path))
    return items


def _select_best(candidates: list[RuntimeCandidate], max_per_category: int) -> tuple[list[RuntimeCandidate], list[RuntimeCandidate]]:
    valid = [c for c in candidates if c.score > 0]
    groups: dict[str, list[RuntimeCandidate]] = {}
    for c in valid:
        groups.setdefault(c.category, []).append(c)

    selected: list[RuntimeCandidate] = []
    for _, group in groups.items():
        group_sorted = sorted(
            group,
            key=lambda x: (x.score, len(x.stdout_excerpt), x.py_path.stat().st_size),
            reverse=True,
        )
        selected.extend(group_sorted[:max_per_category])
    selected_set = {c.py_path for c in selected}
    dropped = [c for c in candidates if c.py_path not in selected_set]
    return sorted(selected, key=lambda x: (x.category, -x.score, x.base_name)), dropped


def _copy_selected(selected: list[RuntimeCandidate], curated_dir: Path) -> list[dict[str, str]]:
    curated_dir.mkdir(parents=True, exist_ok=True)
    keep_names = {item.py_path.name for item in selected}
    keep_names.update({f"{Path(name).stem}.meta.json" for name in keep_names})
    for existing in curated_dir.glob("*"):
        if existing.is_file() and existing.name not in keep_names:
            existing.unlink()

    copied: list[dict[str, str]] = []
    for item in selected:
        target_py = curated_dir / item.py_path.name
        target_py.write_text(_safe_read_text(item.py_path), encoding="utf-8")
        entry = {
            "source_py": str(item.py_path),
            "target_py": str(target_py),
        }
        if item.meta_path and item.meta_path.exists():
            target_meta = curated_dir / item.meta_path.name
            target_meta.write_text(_safe_read_text(item.meta_path), encoding="utf-8")
            entry["source_meta"] = str(item.meta_path)
            entry["target_meta"] = str(target_meta)
        copied.append(entry)
    return copied


def _existing_hashes(store: Chroma) -> set[str]:
    payload = store._collection.get(include=["documents", "metadatas"])
    docs = payload.get("documents", []) or []
    metas = payload.get("metadatas", []) or []
    out: set[str] = set()
    for text, meta in zip(docs, metas):
        if not isinstance(meta, dict):
            continue
        out.add(_doc_hash(str(text or ""), meta))
    return out


def _build_runtime_documents(selected: list[RuntimeCandidate]) -> list[Document]:
    docs: list[Document] = []
    for item in selected:
        source = _safe_read_text(item.py_path)
        try:
            symbols = _extract_symbols(item.py_path)
        except Exception:
            symbols = []
        if symbols:
            for symbol in symbols:
                signature = symbol["signature"] or f"{symbol['name']}(...)"
                page_content = (
                    f"Runtime Source: {item.py_path.name}\n"
                    f"Category: {item.category}\n"
                    f"Symbol: {symbol['name']}\n"
                    f"Kind: {symbol['kind']}\n"
                    f"Signature: {signature}\n"
                    f"Docstring: {symbol['docstring'] or 'No docstring.'}\n\n"
                    f"Code:\n```python\n{symbol['code']}\n```"
                )
                metadata = {
                    "source": str(item.py_path),
                    "source_file": str(item.py_path),
                    "doc_type": "runtime_template",
                    "language": "python",
                    "source_bucket": "tools_latest_runtime_curated",
                    "topic_tags": _topic_tags_from_text(page_content),
                    "symbol": symbol["name"],
                    "quality_tier": "high",
                    "task_id": "",
                    "category": item.category,
                    "tool_names": "[]",
                }
                docs.append(Document(page_content=page_content, metadata=metadata))
        else:
            page_content = (
                f"Runtime Source: {item.py_path.name}\n"
                f"Category: {item.category}\n\n"
                f"Code:\n```python\n{source}\n```"
            )
            metadata = {
                "source": str(item.py_path),
                "source_file": str(item.py_path),
                "doc_type": "runtime_template",
                "language": "python",
                "source_bucket": "tools_latest_runtime_curated",
                "topic_tags": _topic_tags_from_text(page_content),
                "symbol": "",
                "quality_tier": "high",
                "task_id": "",
                "category": item.category,
                "tool_names": "[]",
            }
            docs.append(Document(page_content=page_content, metadata=metadata))
    return docs


def _ingest_selected(
    selected: list[RuntimeCandidate],
    persist_dir: Path,
    collection_name: str,
) -> dict[str, Any]:
    load_dotenv()
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    store = Chroma(
        collection_name=collection_name,
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
    )

    existing = _existing_hashes(store)
    runtime_docs = _build_runtime_documents(selected)
    filtered_docs: list[Document] = []
    skipped = 0
    for doc in runtime_docs:
        digest = _doc_hash(doc.page_content, doc.metadata)
        if digest in existing:
            skipped += 1
            continue
        existing.add(digest)
        filtered_docs.append(doc)

    if filtered_docs:
        store.add_documents(filtered_docs)

    return {
        "documents_built": len(runtime_docs),
        "documents_added": len(filtered_docs),
        "documents_skipped_dedup": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Curate successful runtime scripts and ingest selected templates into Code_RAG."
    )
    parser.add_argument(
        "--runtime-dir",
        default=r".\RAG\code_guide\tools_latest_runtime",
        help="Runtime script archive directory.",
    )
    parser.add_argument(
        "--curated-dir",
        default=r".\RAG\code_guide\tools_latest_runtime_curated",
        help="Destination for curated scripts/meta.",
    )
    parser.add_argument(
        "--persist-dir",
        default=r".\RAG\Code_RAG",
        help="Chroma persist directory for Code_RAG.",
    )
    parser.add_argument(
        "--collection-name",
        default="Code_RAG",
        help="Chroma collection name.",
    )
    parser.add_argument(
        "--max-per-category",
        type=int,
        default=1,
        help="How many scripts to keep per category.",
    )
    parser.add_argument(
        "--report-path",
        default=r".\reports\runtime_code_curation_report.json",
        help="Output report JSON path.",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Do not copy selected scripts to curated directory.",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest selected scripts into Code_RAG.",
    )
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    curated_dir = Path(args.curated_dir)
    report_path = Path(args.report_path)
    persist_dir = Path(args.persist_dir)

    candidates = _gather_candidates(runtime_dir)
    selected, dropped = _select_best(candidates, max_per_category=max(1, args.max_per_category))

    copied: list[dict[str, str]] = []
    if not args.no_copy:
        copied = _copy_selected(selected, curated_dir)

    ingest_result: dict[str, Any] = {"ingest_requested": bool(args.ingest)}
    if args.ingest:
        ingest_result = _ingest_selected(selected, persist_dir, args.collection_name)
        ingest_result["ingest_requested"] = True

    report = {
        "runtime_dir": str(runtime_dir),
        "curated_dir": str(curated_dir),
        "persist_dir": str(persist_dir),
        "collection_name": args.collection_name,
        "total_candidates": len(candidates),
        "selected_count": len(selected),
        "dropped_count": len(dropped),
        "selected": [
            {
                "file": c.py_path.name,
                "base_name": c.base_name,
                "category": c.category,
                "score": round(c.score, 3),
                "reason": c.reason,
            }
            for c in selected
        ],
        "dropped_top20": [
            {
                "file": c.py_path.name,
                "base_name": c.base_name,
                "category": c.category,
                "score": round(c.score, 3),
                "reason": c.reason,
            }
            for c in sorted(dropped, key=lambda x: x.score, reverse=True)[:20]
        ],
        "copied_files": copied,
        "ingest": ingest_result,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
