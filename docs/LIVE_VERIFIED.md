# Live verification

Verified against a real LLM API via `scripts/live_smoke.py` (exactly one real
call, stdlib only, key never printed).

- Date: 2026-11-05
- Provider: opencode Zen — OpenAI-compatible `https://opencode.ai/zen/go/v1`
- Model: `beam-free` (free tier, $0)
- Key: local file, shown redacted below

```text
provider=https://opencode.ai/zen/go/v1 model=beam-free key=*** latency_ms=2326
label=billing confidence=0.99 runner_up=None
valid_label=True
LIVE_SMOKE=OK
```

What this proves: real JSON-mode classification works end-to-end — the model
returned a valid JSON object with the correct label (`billing` for a double
charge) at 0.99 confidence, validated against the taxonomy.
