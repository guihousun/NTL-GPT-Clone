"""Lightweight text metrics used by the benchmark evaluator."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def tokenize(text: str) -> List[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _ngrams(tokens: Sequence[str], n: int) -> List[Tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def bleu4(reference: str, candidate: str) -> float:
    """Compute sentence-level BLEU-4 with simple smoothing."""

    ref_tokens = tokenize(reference)
    cand_tokens = tokenize(candidate)
    if not cand_tokens:
        return 0.0

    precisions: List[float] = []
    for n in range(1, 5):
        ref_counts = Counter(_ngrams(ref_tokens, n))
        cand_counts = Counter(_ngrams(cand_tokens, n))
        if not cand_counts:
            precisions.append(1e-8)
            continue
        overlap = sum(min(count, ref_counts[gram]) for gram, count in cand_counts.items())
        precision = (overlap + 1.0) / (sum(cand_counts.values()) + 1.0)
        precisions.append(precision)

    geometric_mean = math.exp(sum(math.log(max(p, 1e-12)) for p in precisions) / 4.0)
    bp = 1.0
    if len(cand_tokens) < len(ref_tokens):
        bp = math.exp(1.0 - (len(ref_tokens) / max(len(cand_tokens), 1)))
    return float(max(0.0, min(1.0, geometric_mean * bp)))


def _lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    if not a or not b:
        return 0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, tok_a in enumerate(a, start=1):
        for j, tok_b in enumerate(b, start=1):
            if tok_a == tok_b:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[-1][-1]


def rouge_l(reference: str, candidate: str) -> float:
    ref_tokens = tokenize(reference)
    cand_tokens = tokenize(candidate)
    if not ref_tokens or not cand_tokens:
        return 0.0
    lcs = _lcs_length(ref_tokens, cand_tokens)
    prec = lcs / len(cand_tokens)
    rec = lcs / len(ref_tokens)
    if prec + rec == 0:
        return 0.0
    beta = 1.2
    score = ((1 + beta**2) * prec * rec) / (rec + beta**2 * prec)
    return float(max(0.0, min(1.0, score)))


def cider_lite(reference: str, candidate: str) -> float:
    """Approximate CIDEr in [0, 10] without external dependencies."""

    ref_tokens = tokenize(reference)
    cand_tokens = tokenize(candidate)
    if not ref_tokens or not cand_tokens:
        return 0.0

    score = 0.0
    for n in range(1, 5):
        ref_counts = Counter(_ngrams(ref_tokens, n))
        cand_counts = Counter(_ngrams(cand_tokens, n))
        if not ref_counts or not cand_counts:
            continue
        overlap = sum(min(cand_counts[g], ref_counts[g]) for g in cand_counts)
        prec = overlap / max(sum(cand_counts.values()), 1)
        rec = overlap / max(sum(ref_counts.values()), 1)
        if prec + rec == 0:
            continue
        f1 = (2 * prec * rec) / (prec + rec)
        score += f1
    return float(max(0.0, min(10.0, score * 2.5)))


def aggregate_text_metrics(references: Iterable[str], predictions: Iterable[str]) -> Dict[str, float]:
    refs = list(references)
    preds = list(predictions)
    if not refs or not preds or len(refs) != len(preds):
        return {"bleu4": 0.0, "rouge_l": 0.0, "cider_lite": 0.0}

    bleu_scores = [bleu4(r, p) for r, p in zip(refs, preds)]
    rouge_scores = [rouge_l(r, p) for r, p in zip(refs, preds)]
    cider_scores = [cider_lite(r, p) for r, p in zip(refs, preds)]

    return {
        "bleu4": float(sum(bleu_scores) / len(bleu_scores)),
        "rouge_l": float(sum(rouge_scores) / len(rouge_scores)),
        "cider_lite": float(sum(cider_scores) / len(cider_scores)),
    }


def normalized_text_score(bleu: float, rouge: float, cider: float, llm_score: float | None) -> float:
    llm_component = 0.0 if llm_score is None else max(0.0, min(1.0, llm_score / 5.0))
    return float((bleu + rouge + min(cider / 10.0, 1.0) + llm_component) / 4.0)

