#!/usr/bin/env python3
"""Live smoke: ONE real JSON-mode classification via an OpenAI-compatible LLM API.

Reads LLM_API_KEY / LLM_BASE_URL / LLM_MODEL from env (see .env.example).
Refuses to run without a key (except localhost endpoints like Ollama).
Never prints the key. Exits nonzero on HTTP/API/shape errors.
"""
import json
import os
import sys
import time
import urllib.request

BASE = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LOCAL = "localhost" in BASE or "127.0.0.1" in BASE

LABELS = ["billing", "account_access", "bug_report", "feature_request",
          "security", "performance", "integration_api", "general_inquiry"]

if not KEY and not LOCAL:
    print("Missing LLM_API_KEY. See docs/PROVIDERS.md for free options (OpenRouter :free, Ollama).")
    sys.exit(2)

payload = {
    "model": MODEL,
    "temperature": 0.0,
    "max_tokens": 1024,  # reasoning models spend tokens thinking before answering
    "response_format": {"type": "json_object"},
    "messages": [
        {"role": "system", "content": (
            "Classify the support ticket. Reply with a single JSON object: "
            '{"label": <one of: ' + ", ".join(LABELS) + '>, "confidence": <0..1>, '
            '"runner_up": <second-best label or null>}. No other text.')},
        {"role": "user", "content": "Title: Charged twice\nBody: I was charged twice on my card this month, refund the duplicate."},
    ],
}
req = urllib.request.Request(
    f"{BASE}/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}", "User-Agent": "portfolio-live-smoke/1.0", "x-opencode-session": os.getenv("OPENCODE_SESSION_ID", "live-smoke")},  # Zen API requires the session header; ignored by OpenAI/OpenRouter
)
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
except Exception as e:  # noqa: BLE001 - smoke script, surface the error
    print(f"LIVE_SMOKE=ERROR {type(e).__name__}: {e}")
    sys.exit(1)
dt = (time.time() - t0) * 1000
raw = (body["choices"][0]["message"].get("content") or "").strip()
try:
    out = json.loads(raw)
except json.JSONDecodeError:
    print(f"provider={BASE} model={MODEL} latency_ms={dt:.0f}")
    print(f"INVALID_JSON: {raw[:300]}")
    sys.exit(1)
print(f"provider={BASE} model={MODEL} key=***{KEY[-4:] if KEY else 'none'} latency_ms={dt:.0f}")
print(f"label={out.get('label')} confidence={out.get('confidence')} runner_up={out.get('runner_up')}")
print(f"valid_label={out.get('label') in LABELS}")
print("LIVE_SMOKE=OK")
