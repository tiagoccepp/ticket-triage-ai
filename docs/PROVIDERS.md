# LLM providers

The classifier backend speaks **OpenAI Chat Completions (JSON mode)**, so any
OpenAI-compatible endpoint works. Tests, evals and the demo run offline
(`LLM_PROVIDER=mock`); set `LLM_PROVIDER=openai_compatible` + key for a real model.

## Supported endpoints

| Provider | Base URL | Key | Cost |
|---|---|---|---|
| OpenAI | `https://api.openai.com/v1` (default) | `LLM_API_KEY` | paid |
| OpenRouter | `https://openrouter.ai/api/v1` | free key at openrouter.ai/keys | free `:free` models, no card |
| Ollama (local) | `http://localhost:11434/v1` | none needed | free, private |
| opencode Zen ✅ verified | `https://opencode.ai/zen/go/v1` | your Zen key | free `beam-free` model ($0) |
| other gateways | your gateway URL | your gateway key | varies |

## Configure

```bash
cp .env.example .env
# OpenRouter free example:
# LLM_PROVIDER=openai_compatible
# LLM_API_KEY=sk-or-v1-...
# LLM_BASE_URL=https://openrouter.ai/api/v1
# LLM_MODEL=nvidia/nemotron-3.5-lightning:free
```

## Verify with one real call

```bash
python scripts/live_smoke.py
# label=billing confidence=0.92 runner_up=account_access valid_label=True ... LIVE_SMOKE=OK
```

The script makes exactly one JSON-mode classification, validates the label
against the taxonomy, and never prints the key. CI stays keyless: tests and
evals always run on the lexical/mock backends.

## Notes

- Zen requires an `x-opencode-session` header — `scripts/live_smoke.py` sends it
  automatically (override with `OPENCODE_SESSION_ID`); other providers ignore it.

- The code-enforced validity gate (`src/classifier.py`) rejects any label
  outside the taxonomy regardless of provider — hallucinated labels can never
  route, even from weak/free models.
- Timeouts are 60s. Production hardening (retries with backoff on 429/5xx)
  is tracked future work.
- Never commit `.env` or keys — `.gitignore` excludes them.
