# Demo transcript — ticket-triage-ai (real local run)

Base URL: http://127.0.0.1:8002 (uvicorn, LLM_PROVIDER=mock, fresh SQLite DB)

## (a) Clear billing issue — expect auto-route

`POST /tickets/submit` → HTTP 200

Request:
```json
{
  "title": "Double charge on invoice",
  "body": "I was charged twice for my subscription this month, please refund the extra charge.",
  "customer_id": "cust_101"
}
```

Response:
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

## (b) Login problem (first report) — expect routed, no duplicate

`POST /tickets/submit` → HTTP 200

Request:
```json
{
  "title": "Cannot log in to my account",
  "body": "Password reset email never arrives, I tried three times this morning.",
  "customer_id": "cust_42"
}
```

Response:
```json
{
  "ticket_id": "t_415ad894cb11",
  "label": "account_access",
  "confidence": 0.95,
  "runner_up": "general_inquiry",
  "action": "auto_route",
  "reasons": [],
  "agreement": true,
  "baseline_label": "account_access",
  "model_label": "account_access",
  "duplicate_of": null,
  "duplicate_score": 0.102,
  "latency_ms": 0.49
}
```

## (c) Near-duplicate from same person — expect duplicate flag

`POST /tickets/submit` → HTTP 200

Request:
```json
{
  "title": "Cannot log in to my account",
  "body": "Password reset email never arrives. I tried three times this morning, please help.",
  "customer_id": "cust_42"
}
```

Response:
```json
{
  "ticket_id": "t_8061490f6f23",
  "label": "account_access",
  "confidence": 0.81,
  "runner_up": "general_inquiry",
  "action": "auto_route",
  "reasons": [],
  "agreement": true,
  "baseline_label": "account_access",
  "model_label": "account_access",
  "duplicate_of": "t_415ad894cb11",
  "duplicate_score": 0.91,
  "latency_ms": 0.52
}
```

## (d) Vague one-liner — expect human review

`POST /tickets/submit` → HTTP 200

Request:
```json
{
  "title": "Help",
  "body": "It doesn't work.",
  "customer_id": "cust_77"
}
```

Response:
```json
{
  "ticket_id": "t_eaaa34326b37",
  "label": "general_inquiry",
  "confidence": 0.95,
  "runner_up": "feature_request",
  "action": "human_review",
  "reasons": [
    "DISAGREEMENT:baseline=general_inquiry,model=account_access"
  ],
  "agreement": false,
  "baseline_label": "general_inquiry",
  "model_label": "account_access",
  "duplicate_of": null,
  "duplicate_score": 0.102,
  "latency_ms": 0.44
}
```

## (e) Security report — expect review for severity

`POST /tickets/submit` → HTTP 200

Request:
```json
{
  "title": "Unauthorized access - possible hack",
  "body": "Someone logged into my account from another country, I did not authorize this access. Please secure my account.",
  "customer_id": "cust_99"
}
```

Response:
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

## Review queue

`GET /review-queue` → HTTP 200

Response:
```json
{
  "tickets": [
    {
      "id": "t_c189ebc7d214",
      "title": "Unauthorized access - possible hack",
      "body": "Someone logged into my account from another country, I did not authorize this access. Please secure my account.",
      "customer_id": "cust_99",
      "label": "security",
      "confidence": 0.95,
      "runner_up": "account_access",
      "status": "needs_review",
      "duplicate_of": "",
      "created_at": "2026-11-05T22:32:42.571904+00:00",
      "updated_at": "2026-11-05T22:32:42.571904+00:00"
    },
    {
      "id": "t_eaaa34326b37",
      "title": "Help",
      "body": "It doesn't work.",
      "customer_id": "cust_77",
      "label": "general_inquiry",
      "confidence": 0.95,
      "runner_up": "feature_request",
      "status": "needs_review",
      "duplicate_of": "",
      "created_at": "2026-11-05T22:32:42.505445+00:00",
      "updated_at": "2026-11-05T22:32:42.505445+00:00"
    }
  ]
}
```

## Metrics

`GET /metrics` → HTTP 200

Response:
```json
{
  "counts": {
    "needs_review": 2,
    "routed": 3
  },
  "total": 5,
  "review_rate": 0.4
}
```

## Health

`GET /health` → HTTP 200

Response:
```json
{
  "status": "ok",
  "labels": "billing,account_access,bug_report,feature_request,security,performance,integration_api,general_inquiry"
}
```
