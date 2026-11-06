# Deploy

Primary target: **Hugging Face Spaces (Docker mode)** — free, no card, persistent URL.

```bash
HF_TOKEN=hf_xxx python scripts/hf_deploy.py   # creates/updates the Space, prints the URL
```

Then open `https://<you>-ticket-triage.hf.space/ui`.

## How it works

- `Dockerfile` serves the API with uvicorn on `${PORT:-7860}`.
- The deploy script uploads only `Dockerfile`, `requirements.txt`, `src/`, `data/`
  plus a generated Space `README.md` (SDK header).
- No env vars required: lexical backend, keyless. Optional LLM backend via
  `LLM_API_KEY` (+ `LLM_BASE_URL`, `LLM_MODEL`) as Space secrets.
- Note: the SQLite store is ephemeral on Spaces (resets on rebuild) — fine for demos.

## Alternatives

- **Render/Railway**: connect the GitHub repo, Docker runtime, free tier.
- **Local**: `./demo.sh` — identical UI.
