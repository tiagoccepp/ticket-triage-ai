"""FastAPI service: submit tickets, triage, human review queue.

Endpoints:
  GET  /health
  POST /tickets/submit   -> run pipeline, persist, return outcome
  GET  /tickets/{id}     -> ticket + audit trail
  GET  /tickets          -> recent tickets
  GET  /review-queue     -> tickets needing human review
  POST /review/{id}      -> approve / override with reviewer identity
  GET  /metrics          -> counts + review rate
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.classifier import TriageOutcome, TriagePipeline
from src.config import get_settings
from src.db import TicketStore
from src.taxonomy import is_valid_label, list_ids

app = FastAPI(title="Ticket Triage AI", version="0.1.0")

_pipeline: TriagePipeline | None = None
_store: TicketStore | None = None


def get_pipeline() -> TriagePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = TriagePipeline(settings=get_settings())
    return _pipeline


def get_store() -> TicketStore:
    global _store
    if _store is None:
        _store = TicketStore(get_settings())
    return _store


# -- schemas ------------------------------------------------------------------
class SubmitRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=10000)
    customer_id: str = ""


class ReviewRequest(BaseModel):
    decision: Literal["approve", "override"]
    label: str | None = None
    reviewer: str = Field(min_length=1)
    notes: str = ""


class TicketWithAudit(BaseModel):
    ticket: dict[str, Any]
    audit: list[dict[str, Any]]


# -- routes --------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "labels": ",".join(list_ids())}


@app.post("/tickets/submit", response_model=TriageOutcome)
def submit_ticket(req: SubmitRequest) -> TriageOutcome:
    return get_pipeline().triage(
        title=req.title, body=req.body, customer_id=req.customer_id
    )


@app.get("/tickets/{ticket_id}", response_model=TicketWithAudit)
def get_ticket(ticket_id: str) -> TicketWithAudit:
    ticket = get_store().get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return TicketWithAudit(ticket=ticket, audit=get_store().list_audit(ticket_id))


@app.get("/tickets")
def list_tickets(limit: int = 50) -> dict[str, Any]:
    return {"tickets": get_store().list_tickets(limit=min(limit, 200))}


@app.get("/review-queue")
def review_queue(limit: int = 50) -> dict[str, Any]:
    """Human review queue: needs_review + abstained, newest first."""
    return {"tickets": get_store().list_review_queue(limit=min(limit, 200))}


@app.post("/review/{ticket_id}")
def review_ticket(ticket_id: str, req: ReviewRequest) -> dict[str, Any]:
    store = get_store()
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    if req.decision == "override":
        if not req.label or not is_valid_label(req.label):
            raise HTTPException(
                status_code=422,
                detail=f"label must be one of {list_ids()}",
            )
        store.update_ticket(ticket_id, label=req.label, status="reviewed")
    else:
        store.update_ticket(ticket_id, status="reviewed")
    store.add_audit(ticket_id, "reviewed", {
        "decision": req.decision, "label": req.label,
        "reviewer": req.reviewer, "notes": req.notes,
    })
    return {"ticket": store.get_ticket(ticket_id), "ok": True}


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    store = get_store()
    counts = store.counts_by_status()
    total = sum(counts.values())
    review = counts.get("needs_review", 0) + counts.get("abstained", 0)
    return {
        "counts": counts,
        "total": total,
        "review_rate": round(review / total, 3) if total else 0.0,
    }
