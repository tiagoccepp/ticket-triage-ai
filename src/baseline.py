"""Deterministic keyword baseline. Zero dependencies, fully explainable.

Scores each category by keyword hits (phrase matches weighted higher),
normalizes to a pseudo-confidence, and returns a runner-up for calibration.
This baseline is the fallback when the LLM abstains AND one side of the
HybridPolicy disagreement check.
"""

from __future__ import annotations

import re
import time

from src.taxonomy import TAXONOMY, Category


from pydantic import BaseModel, Field


class BaselineResult(BaseModel):
    label: str
    confidence: float
    runner_up: str | None = None
    runner_up_confidence: float = 0.0
    method: str = "baseline"
    reasoning: str = ""
    latency_ms: float = 0.0


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def score_categories(text: str, categories: list[Category] | None = None) -> dict[str, float]:
    """Raw keyword scores per category id."""
    cats = categories or TAXONOMY
    norm = _normalize(text)
    scores: dict[str, float] = {}
    for cat in cats:
        score = 0.0
        for kw in cat.keywords:
            k = kw.lower()
            if " " in k:  # phrase -> stronger signal
                if k in norm:
                    score += 2.0
            else:
                # word-boundary match to avoid "fast" matching "breakfast"
                if re.search(rf"\b{re.escape(k)}\b", norm):
                    score += 1.0
        scores[cat.id] = score
    return scores


def scores_to_confidence(scores: dict[str, float]) -> tuple[str, float, str | None, float]:
    """Convert raw scores to (label, confidence, runner_up, runner_up_conf)."""
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_id, top = ranked[0]
    second_id, second = ranked[1] if len(ranked) > 1 else ("", 0.0)
    total = sum(scores.values())
    if top <= 0 or total <= 0:
        return "general_inquiry", 0.30, None, 0.0
    # margin-based confidence: how dominant is the winner
    margin = (top - second) / total if total else 0.0
    confidence = round(min(0.95, 0.45 + margin * 0.9 + min(top, 6) * 0.03), 3)
    runner_conf = round(second / total, 3) if total else 0.0
    runner = second_id if second > 0 else None
    return top_id, confidence, runner, runner_conf


def classify_baseline(text: str, categories: list[Category] | None = None) -> BaselineResult:
    start = time.perf_counter()
    scores = score_categories(text, categories)
    label, conf, runner, runner_conf = scores_to_confidence(scores)
    latency = (time.perf_counter() - start) * 1000
    return BaselineResult(
        label=label,
        confidence=conf,
        runner_up=runner,
        runner_up_confidence=runner_conf,
        reasoning=f"keyword scores: {dict(sorted(scores.items(), key=lambda kv: -kv[1])[:3])}",
        latency_ms=round(latency, 2),
    )
