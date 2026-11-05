# ARCHITECTURE.md — Ticket Triage AI

## 1. System overview

A ticket triage service with three planes:

- **Classify plane**: deterministic baseline + model backend (LLM or offline lexical) produce labeled predictions with confidence + runner-up.
- **Decide plane**: validity gate (code-enforced) → HybridPolicy → threshold policy produce a routing action (`auto_route` | `human_review` | `abstain`).
- **Persist plane**: tickets + append-only audit events in SQLite (default) or Postgres.

```
                    +------------------+
                    |  FastAPI (api.py)|
                    +--------+---------+
                             |
                    +--------v---------+
                    | TriagePipeline   |
                    | (classifier.py)  |
                    +---+----------+---+
                        |          |
            +-----------v-+  +-----v------------+
            | baseline.py |  | backend: LLM /   |
            | keywords    |  | lexical / mock   |
            +-----------+  +-----+------------+
                                 |
                        +--------v--------+
                        | validity_gate() |
                        +--------+--------+
                                 |
                        +--------v--------+
                        | HybridPolicy    |
                        | (hybrid.py)     |
                        +--------+--------+
                                 |
                    +------------v-------------+
                    | TicketStore (db.py)      |
                    | tickets + audit_events   |
                    +--------------------------+
```

## 2. Module contracts

### `config.py` — `Settings`
Env-driven; `DATABASE_URL` selects SQLite vs Postgres; `LLM_PROVIDER=mock` keeps CI keyless. Thresholds (`AUTO_THRESHOLD`, `REVIEW_THRESHOLD`, `DUPLICATE_THRESHOLD`) are env-tunable without code changes.

### `taxonomy.py` — taxonomy-as-data
`TAXONOMY: list[Category]` is the single source of truth. `render_prompt_section()` derives the LLM label set from it; `is_valid_label()` backs the gate; `load_taxonomy_from_json()` allows runtime swaps. Severity (`low|medium|high|critical`) drives the HIGH_SEVERITY routing trigger.

### `baseline.py` — deterministic rules
Word-boundary keyword hits (phrases ×2), margin-based pseudo-confidence, runner-up. Zero deps, explainable, and the disagreement anchor for the hybrid policy.

### `classifier.py` — backends + pipeline
- `LexicalBackend`: TF-IDF cosine between ticket and per-category documents (name + description + keywords + examples). Pure stdlib.
- `MockLLMBackend`: deterministic lexical-boosted mock so LLM-path tests/evals run keyless.
- `OpenAICompatibleBackend`: minimal stdlib-HTTP chat call, JSON mode, `temperature=0`; any failure → abstain (never guess). Falls back to mock when no key.
- `validity_gate()`: unknown label → `abstain`, confidence 0, reason annotated. Applied to every model output in the pipeline.
- `ThresholdPolicy`: confidence → `auto_route` / `human_review` / `abstain`.
- `DuplicateIndex`: TF-IDF cosine, threshold-tuned; `duplicate_of()` returns best hit above threshold. Embedding vectors can replace TF-IDF behind the same methods.
- `TriagePipeline.triage()`: baseline + model → gate → hybrid → policy refinement → duplicate check → persist ticket + audit event.

### `hybrid.py` — `HybridPolicy`
Compares baseline vs model. Triggers checked in order: `ABSTENTION` (either side) → `HIGH_SEVERITY` → `LOW_CONFIDENCE` → `DISAGREEMENT`. Any trigger ⇒ `human_review`. Winner = higher confidence.

### `db.py` — `TicketStore`
Sync store, `?` placeholders translated to `%s` for Postgres. Tables: `tickets(id, title, body, customer_id, label, confidence, runner_up, status, duplicate_of, created_at, updated_at)`, `audit_events(id, ticket_id, event, payload JSON, created_at)` append-only. Statuses: `open | routed | needs_review | abstained | reviewed`.

### `api.py` — FastAPI
`POST /tickets/submit`, `GET /tickets/{id}` (+audit), `GET /tickets`, `GET /review-queue`, `POST /review/{id}` (approve/override, taxonomy-validated), `GET /metrics`, `GET /health`.

### `evals.py` + `eval/run_evals.py`
Offline eval harness: accuracy-on-routed, overall accuracy, review/disagreement rates, latency p50/p95, confusion matrix over 80 golden tickets.

## 3. Data flow (submit)

1. `POST /tickets/submit` → `TriagePipeline.triage(title, body)`.
2. Baseline + model classify in-process (LLM call only when key configured).
3. `validity_gate` sanitizes model output.
4. `HybridPolicy.decide` + `ThresholdPolicy` pick the action.
5. `DuplicateIndex` scores against previously seen tickets.
6. Ticket persisted with status mapped from action; `triaged` audit event stores baseline/model/policy/duplicate payload; ticket id added to duplicate index.
7. Reviewers resolve `needs_review`/`abstained` via `POST /review/{id}` → `reviewed` + `reviewed` audit event.

## 4. Failure modes

| Failure | Behavior |
|---|---|
| LLM unreachable / bad JSON | Abstain (confidence 0), route to review, reason logged |
| Hallucinated label | Validity gate → abstain, confidence 0 |
| Empty/gibberish input | Lexical abstains; policy routes to review |
| Postgres down | Startup `wait_ready` for health; SQLite default avoids this in dev/CI |
| Duplicate index cold | Returns no hit; warms as tickets persist |

## 5. Extension points

- New label: add a `Category` (or JSON file) — prompt, gate, evals, API validation follow automatically.
- Real embeddings: replace `TfidfVectorizer` vectors in `DuplicateIndex`/`LexicalBackend` with an embedding call; keep cosine + threshold interface.
- Reviewer UI: thin client over `/review-queue` + `/review/{id}` (see README).
- Auth/multi-tenancy: add middleware + `customer_id` scoping in `TicketStore` queries.
