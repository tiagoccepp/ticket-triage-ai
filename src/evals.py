"""Offline eval helpers shared by eval/run_evals.py and CI."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any


def load_golden(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100)
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    frac = k - lo
    return round(ordered[lo] * (1 - frac) + ordered[hi] * frac, 2)


def confusion_matrix(
    gold: list[str], pred: list[str], labels: list[str]
) -> dict[str, dict[str, int]]:
    matrix = {g: {p: 0 for p in labels} for g in labels}
    for g, p in zip(gold, pred):
        if g in matrix and p in matrix[g]:
            matrix[g][p] += 1
    return matrix


def summarize(
    records: list[dict[str, Any]], labels: list[str]
) -> dict[str, Any]:
    """records: [{expected, predicted, action, agreement, latency_ms}]"""
    total = len(records)
    routed = [r for r in records if r["action"] == "auto_route"]
    reviewed = [r for r in records if r["action"] != "auto_route"]
    correct_routed = sum(1 for r in routed if r["predicted"] == r["expected"])
    disagreements = sum(1 for r in records if not r.get("agreement", True))
    lat = [r.get("latency_ms", 0.0) for r in records]
    gold = [r["expected"] for r in records]
    pred = [r["predicted"] for r in records]
    return {
        "total": total,
        "routed": len(routed),
        "review": len(reviewed),
        "accuracy_on_routed": round(correct_routed / len(routed), 3) if routed else 0.0,
        "overall_accuracy": round(
            sum(1 for r in records if r["predicted"] == r["expected"]) / total, 3
        ) if total else 0.0,
        "review_rate": round(len(reviewed) / total, 3) if total else 0.0,
        "disagreement_rate": round(disagreements / total, 3) if total else 0.0,
        "latency_ms": {
            "p50": percentile(lat, 50),
            "p95": percentile(lat, 95),
            "median": round(median(lat), 2) if lat else 0.0,
        },
        "confusion_matrix": confusion_matrix(gold, pred, labels),
    }
