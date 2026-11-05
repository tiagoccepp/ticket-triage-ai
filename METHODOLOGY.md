# METHODOLOGY.md — Calibration & Eval Method

## 1. Why accuracy-on-routed is the headline metric

Raw accuracy mixes two populations: tickets the system handled alone and tickets a human reviewed. Only the first population carries automation risk. We therefore optimize:

- **accuracy-on-routed** = correct / auto-routed (safety)
- **review rate** = human-routed / total (cost)

A good triage system maximizes accuracy-on-routed subject to an affordable review rate. The `.env` thresholds (`AUTO_THRESHOLD=0.80`, `REVIEW_THRESHOLD=0.55`) are the dials; `eval/run_evals.py` is the instrument.

## 2. Confidence design

- **Baseline**: margin-based — `(top − runner) / total` plus a magnitude term, capped at 0.95. Keyword overlap with no clear winner yields low confidence by construction.
- **Lexical**: TF-IDF cosine rescaled (`×2.2`, capped 0.95). Short-text cosines cluster low, so the multiplier was chosen so clear matches clear 0.55 while weak matches abstain.
- **Mock LLM**: lexical ± agreement boost, deterministic for CI.
- **Real LLM**: model-reported confidence, clamped to [0,1], then gated. Treat as uncalibrated until measured — the hybrid disagreement check exists precisely because LLM confidences overstate.

## 3. Routing policy rationale

| Trigger | Why |
|---|---|
| HIGH_SEVERITY | `security`/`bug_report`/`performance` errors are expensive; a human must see them even at 0.95 confidence |
| LOW_CONFIDENCE | Below 0.55 the model is guessing; abstain-or-review dominates random routing |
| DISAGREEMENT | Baseline and model use independent signals (keywords vs semantics); disagreement is the cheapest uncertainty detector available |
| ABSTENTION | Either side declining to predict is explicit uncertainty — never override it |

## 4. Validity gate

Prompt instructions ("use exactly these labels") reduce but never eliminate hallucinations. The gate is enforced in `validity_gate()` on every model output: unknown label → `abstain`, confidence 0, reason annotated, audit-logged. Tested in `tests/test_validity_gate.py` with adversarial labels at 0.99 confidence.

## 5. Runner-up calibration

Every prediction carries `runner_up` + `runner_up_confidence`. Uses:

1. Reviewer UX: "billing 0.62 vs refund 0.58" reads differently from "billing 0.62 vs security 0.05".
2. Future calibration: top−runner margin is a stronger routing signal than raw confidence; the eval harness already records both sides for analysis.
3. Disagreement forensics: when baseline and model disagree, runner-ups often reveal the shared second choice.

## 6. Duplicate detection

TF-IDF cosine with threshold 0.82 (env-tunable). Chosen over exact-match because ticket re-submits differ in punctuation/casing; chosen over embeddings for the MVP because it is offline, deterministic, and dependency-free. Swap path: same `DuplicateIndex` interface, embedding vectors instead of TF-IDF.

## 7. Eval protocol

1. 80 golden tickets (10/category), hand-written to cover paraphrases, not just keyword copies.
2. `python eval/run_evals.py --backend lexical` (CI) and `--backend mock` (LLM path).
3. Read accuracy-on-routed first; if it drops after a taxonomy/threshold change, the change does not ship.
4. Confusion matrix localizes category-boundary problems (e.g. billing↔account_access on "permission to view billing").
5. Latency p50/p95 guards the in-process path; LLM latency is measured separately in production via the audit payload's `latency_ms`.

## 8. Known limitations

- Keyword/TF-IDF signals underperform embeddings on paraphrase-heavy tickets; the review queue absorbs this by design.
- Mock LLM is a stand-in, not a model — real-LLM calibration requires labeled production traffic.
- Thresholds are set by judgment + golden evals, not by isotonic regression on production data (next step once review labels accumulate).
