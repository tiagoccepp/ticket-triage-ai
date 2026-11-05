# Ticket Triage AI — Submission

## What it is
A support-ticket triage service that classifies incoming tickets into 8 categories
(billing, account_access, bug_report, feature_request, security, performance,
integration_api, general_inquiry) and decides per ticket whether to **auto-route**
or send to **human review**. Every decision carries machine-readable reasons,
an audit trail persists every triage + review event, and near-duplicates are
flagged via TF-IDF cosine. Runs fully offline and keyless
(`LLM_PROVIDER=mock`, SQLite, system python3).

## Confidence-gating in 5 lines
1. Two classifiers vote on every ticket: a keyword baseline and a model backend (lexical by default, OpenAI-compatible when a key is set).
2. A validity gate clamps model output (bad labels, overconfident abstentions) before any routing decision.
3. The hybrid policy routes to human review on three triggers, in order: HIGH_SEVERITY (high/critical category), LOW_CONFIDENCE (below 0.55), DISAGREEMENT (baseline ≠ model).
4. Agreement + confident + non-severe tickets auto-route; anything else lands in `GET /review-queue` with its reasons.
5. Held-out evals (80 golden tickets): accuracy-on-routed 1.0, overall accuracy 0.912, review rate 0.487.

## How to run locally
```bash
./demo.sh
# then, e.g.:
curl -s http://127.0.0.1:8002/health
curl -s -X POST http://127.0.0.1:8002/tickets/submit \
  -H 'Content-Type: application/json' \
  -d '{"title":"Double charge on invoice","body":"I was charged twice, please refund."}'
curl -s http://127.0.0.1:8002/review-queue
curl -s http://127.0.0.1:8002/metrics
```
Tests: `python3 -m pytest tests/ -q` (33 passed). Evals: `python3 eval/run_evals.py --backend lexical`.
Verified request/response transcript: `demo/transcript.md`.

## Key files to read
- `src/hybrid.py` — the routing policy (severity → confidence → disagreement).
- `src/classifier.py` — pipeline: baseline + model → validity gate → hybrid → duplicate check → persist.
- `src/taxonomy.py` — the 8 labels with severities.
- `src/api.py` — FastAPI service (`/tickets/submit`, `/review-queue`, `/review/{id}`, `/metrics`).
- `src/db.py` — SQLite store with audit trail.
- `eval/run_evals.py` + `eval/golden_tickets.jsonl` — calibration evals.
- `demo/transcript.md` — real local run: 5 submits, review queue, metrics, health.

## Sample triage decisions (copied verbatim from `demo/transcript.md`)

Clear billing issue → auto-routed:
```json
{
  "ticket_id": "t_571e5155f195",
  "label": "billing",
  "confidence": 0.95,
  "runner_up": "feature_request",
  "action": "auto_route",
  "reasons": [],
  "agreement": true,
  "baseline_label": "billing",
  "model_label": "billing",
  "duplicate_of": null,
  "duplicate_score": 0.0,
  "latency_ms": 2.13
}
```

Security report → held for human review on severity:
```json
{
  "ticket_id": "t_c189ebc7d214",
  "label": "security",
  "confidence": 0.95,
  "runner_up": "account_access",
  "action": "human_review",
  "reasons": [
    "HIGH_SEVERITY:security"
  ],
  "agreement": true,
  "baseline_label": "security",
  "model_label": "security",
  "duplicate_of": null,
  "duplicate_score": 0.172,
  "latency_ms": 0.42
}
```
