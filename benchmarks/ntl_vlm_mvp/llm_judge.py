"""Optional LLM-based text judge with persistent cache."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .io_utils import ensure_dir, read_jsonl, write_jsonl
from .text_metrics import rouge_l


def _hash_key(task_id: str, reference: str, prediction: str, context: str) -> str:
    raw = f"{task_id}|||{reference}|||{prediction}|||{context}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _heuristic_score(reference: str, prediction: str) -> float:
    overlap = rouge_l(reference, prediction)
    length_ratio = 0.0
    ref_len = max(len(reference.split()), 1)
    pred_len = len(prediction.split())
    length_ratio = min(pred_len / ref_len, ref_len / max(pred_len, 1))
    score = 1.0 + 4.0 * (0.65 * overlap + 0.35 * length_ratio)
    return float(max(1.0, min(5.0, score)))


@dataclass
class LLMJudge:
    cache_path: Path
    model: str = "gpt-4o-mini"
    enabled: bool = False

    def __post_init__(self) -> None:
        ensure_dir(self.cache_path.parent)
        self._cache: Dict[str, float] = {}
        for row in read_jsonl(self.cache_path):
            key = row.get("key")
            score = row.get("score")
            if isinstance(key, str) and isinstance(score, (int, float)):
                self._cache[key] = float(score)

    def _openai_score(self, task_id: str, reference: str, prediction: str, context: str) -> Optional[float]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        try:
            from openai import OpenAI
        except Exception:
            return None

        prompt = (
            "You are grading remote sensing benchmark outputs.\n"
            "Score the candidate from 1 to 5.\n"
            "1=incorrect/unsafe, 3=partially correct, 5=accurate/actionable.\n"
            "Return only a number.\n\n"
            f"Task: {task_id}\n"
            f"Context: {context}\n"
            f"Reference: {reference}\n"
            f"Candidate: {prediction}\n"
        )
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=16,
            )
            text = response.choices[0].message.content.strip()
            value = float(text)
            return float(max(1.0, min(5.0, value)))
        except Exception:
            return None

    def score(self, task_id: str, reference: str, prediction: str, context: str = "") -> float:
        key = _hash_key(task_id, reference, prediction, context)
        if key in self._cache:
            return self._cache[key]

        score = None
        if self.enabled:
            score = self._openai_score(task_id=task_id, reference=reference, prediction=prediction, context=context)
        if score is None:
            score = _heuristic_score(reference=reference, prediction=prediction)

        self._cache[key] = float(score)
        self._flush()
        return float(score)

    def _flush(self) -> None:
        rows = [{"key": key, "score": score} for key, score in self._cache.items()]
        write_jsonl(self.cache_path, rows)

