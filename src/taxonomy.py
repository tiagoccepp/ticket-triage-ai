"""Taxonomy-as-data: categories live in data, not in model weights.

Adding or renaming a category = editing TAXONOMY below (or loading it from
JSON). No retraining, no redeploy of the model. The prompt renderer derives
the LLM label set from this single source of truth, and the validity gate
rejects anything outside it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Category(BaseModel):
    id: str
    name: str
    description: str
    keywords: list[str] = Field(default_factory=list)
    severity: str = Field(default="medium")  # low | medium | high | critical
    sla_hours: int = Field(default=24)
    examples: list[str] = Field(default_factory=list)


TAXONOMY: list[Category] = [
    Category(
        id="billing",
        name="Billing & Payments",
        description="Invoices, charges, refunds, subscriptions, payment failures.",
        keywords=["invoice", "charge", "charged", "refund", "subscription", "payment",
                  "billing", "receipt", "overcharged", "credit card", "renewal", "cancel subscription"],
        severity="medium",
        sla_hours=24,
        examples=[
            "I was charged twice for my subscription this month.",
            "Please refund the last invoice, I cancelled before renewal.",
        ],
    ),
    Category(
        id="account_access",
        name="Account & Access",
        description="Login, passwords, 2FA, locked accounts, permissions.",
        keywords=["login", "password", "locked out", "2fa", "two-factor", "reset",
                  "sign in", "authentication", "sso", "permission", "access denied"],
        severity="medium",
        sla_hours=12,
        examples=[
            "I can't log in, password reset email never arrives.",
            "My account is locked after too many attempts.",
        ],
    ),
    Category(
        id="bug_report",
        name="Bug Report",
        description="Something broken, errors, crashes, incorrect behavior.",
        keywords=["bug", "error", "crash", "broken", "not working", "fails",
                  "exception", "500", "404", "glitch", "wrong", "issue with"],
        severity="high",
        sla_hours=8,
        examples=[
            "The dashboard crashes with a 500 error when I export.",
            "Save button does nothing on the settings page.",
        ],
    ),
    Category(
        id="feature_request",
        name="Feature Request",
        description="New functionality, improvements, integrations wished for.",
        keywords=["feature", "request", "add", "wish", "would be nice", "improvement",
                  "suggestion", "roadmap", "support for", "please add"],
        severity="low",
        sla_hours=72,
        examples=[
            "Please add dark mode to the mobile app.",
            "It would be nice to export reports as PDF.",
        ],
    ),
    Category(
        id="security",
        name="Security Incident",
        description="Suspected breach, phishing, unauthorized access, data leak.",
        keywords=["hack", "breach", "phishing", "unauthorized", "suspicious",
                  "vulnerability", "leak", "malware", "compromised", "intrusion"],
        severity="critical",
        sla_hours=2,
        examples=[
            "Someone logged into my account from another country.",
            "I found an API key leaked in a public repo.",
        ],
    ),
    Category(
        id="performance",
        name="Performance",
        description="Slowness, timeouts, latency, degraded service.",
        keywords=["slow", "timeout", "latency", "lag", "performance", "taking forever",
                  "hangs", "unresponsive", "degraded", "fast"],
        severity="high",
        sla_hours=8,
        examples=[
            "The app takes forever to load since yesterday.",
            "API requests keep timing out after 30 seconds.",
        ],
    ),
    Category(
        id="integration_api",
        name="Integration & API",
        description="API usage, webhooks, SDKs, third-party integrations.",
        keywords=["api", "webhook", "sdk", "integration", "endpoint", "token",
                  "rate limit", "oauth", "zapier", "slack integration"],
        severity="medium",
        sla_hours=24,
        examples=[
            "Webhook deliveries are failing with 401 errors.",
            "How do I paginate the list endpoint in the Python SDK?",
        ],
    ),
    Category(
        id="general_inquiry",
        name="General Inquiry",
        description="How-to questions, documentation, anything not matching above.",
        keywords=["how do i", "how to", "question", "help", "docs", "documentation",
                  "where is", "what is", "pricing", "trial"],
        severity="low",
        sla_hours=48,
        examples=[
            "How do I invite teammates to my workspace?",
            "Where is the documentation for SSO setup?",
        ],
    ),
]

HIGH_SEVERITY: set[str] = {"high", "critical"}


def list_ids() -> list[str]:
    return [c.id for c in TAXONOMY]


def get_category(category_id: str) -> Category | None:
    for c in TAXONOMY:
        if c.id == category_id:
            return c
    return None


def is_valid_label(label: str) -> bool:
    return label in set(list_ids())


def severity_of(label: str) -> str:
    cat = get_category(label)
    return cat.severity if cat else "medium"


def to_dict_list() -> list[dict[str, Any]]:
    return [c.model_dump() for c in TAXONOMY]


def load_taxonomy_from_json(path: str | Path) -> list[Category]:
    """Swap the taxonomy at runtime from a JSON file (taxonomy-as-data)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Category(**item) for item in raw]


def render_prompt_section(categories: list[Category] | None = None) -> str:
    """Render the label set as an LLM prompt section. Single source of truth."""
    cats = categories or TAXONOMY
    lines = ["You classify support tickets. Valid labels (use EXACTLY one):"]
    for c in cats:
        lines.append(f"- {c.id}: {c.description}")
    lines.append(
        'Reply with JSON only: {"label": "<id>", "confidence": 0.0-1.0, '
        '"runner_up": "<id or null>", "reason": "<short>"}'
    )
    return "\n".join(lines)


def render_full_prompt(ticket_text: str, categories: list[Category] | None = None) -> str:
    return f"{render_prompt_section(categories)}\n\nTicket:\n{ticket_text}\n\nJSON:"
