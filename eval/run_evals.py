"""Offline eval runner: keyless, uses the lexical backend by default.

Usage:
    python eval/run_evals.py [--backend lexical|mock] [--golden eval/golden_tickets.jsonl]

Emits: accuracy-on-routed, review rate, disagreement rate, latency p50/p95,
overall accuracy, and the confusion matrix.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.baseline import classify_baseline
from src.classifier import (
    LexicalBackend,
    MockLLMBackend,
    TriagePipeline,
    validity_gate,
)
from src.config import Settings
from src.evals import load_golden, summarize
from src.hybrid import HybridInput, HybridPolicy
from src.taxonomy import list_ids


def run(golden_path: str, backend_name: str) -> dict:
    settings = Settings(
        database_url="sqlite:///:memory:",
        auto_threshold=0.80,
        review_threshold=0.55,
    )
    backend = MockLLMBackend() if backend_name == "mock" else LexicalBackend()
    hybrid = HybridPolicy(
        review_threshold=settings.review_threshold,
        auto_threshold=settings.auto_threshold,
    )
    rows = load_golden(golden_path)
    records = []
    for row in rows:
        text = f"{row['title']}\n{row['body']}"
        base = classify_baseline(text)
        model = validity_gate(backend.classify(text))
        decision = hybrid.decide(
            HybridInput(label=base.label, confidence=base.confidence),
            HybridInput(label=model.label, confidence=model.confidence,
                        abstained=model.abstained),
        )
        records.append({
            "expected": row["expected"],
            "predicted": decision.final_label,
            "action": decision.action,
            "agreement": decision.agreement,
            "latency_ms": base.latency_ms + model.latency_ms,
        })
    summary = summarize(records, list_ids())
    summary["backend"] = backend_name
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="lexical", choices=["lexical", "mock"])
    parser.add_argument("--golden", default="eval/golden_tickets.jsonl")
    args = parser.parse_args()
    summary = run(args.golden, args.backend)
    print(f"backend:            {summary['backend']}")
    print(f"total:              {summary['total']}")
    print(f"routed:             {summary['routed']}")
    print(f"in review:          {summary['review']}")
    print(f"accuracy-on-routed: {summary['accuracy_on_routed']}")
    print(f"overall accuracy:   {summary['overall_accuracy']}")
    print(f"review rate:        {summary['review_rate']}")
    print(f"disagreement rate:  {summary['disagreement_rate']}")
    print(f"latency p50/p95:    {summary['latency_ms']['p50']}/{summary['latency_ms']['p95']} ms")
    print("\nconfusion matrix (gold -> predicted):")
    labels = list_ids()
    header = "gold\\pred".ljust(16) + "".join(l[:8].ljust(9) for l in labels)
    print(header)
    for g in labels:
        row = summary["confusion_matrix"][g]
        print(g.ljust(16) + "".join(str(row[p]).ljust(9) for p in labels))


if __name__ == "__main__":
    main()
