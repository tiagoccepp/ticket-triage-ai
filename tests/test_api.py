"""API tests (offline, isolated temp SQLite)."""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "api_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from src.config import get_settings

    get_settings.cache_clear()
    import src.api as api

    api._pipeline = None
    api._store = None
    c = TestClient(api.app)
    yield c
    get_settings.cache_clear()
    api._pipeline = None
    api._store = None


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "billing" in r.json()["labels"]


def test_submit_ticket_persists_and_triages(client):
    r = client.post("/tickets/submit", json={
        "title": "Double charge on invoice",
        "body": "I was charged twice for my subscription this month, please refund.",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ticket_id"].startswith("t_")
    assert data["label"] == "billing"
    assert data["action"] in ("auto_route", "human_review", "abstain")


def test_get_ticket_includes_audit(client):
    sub = client.post("/tickets/submit", json={
        "title": "Login broken", "body": "Password reset email never arrives.",
    }).json()
    r = client.get(f"/tickets/{sub['ticket_id']}")
    assert r.status_code == 200
    payload = r.json()
    assert payload["ticket"]["id"] == sub["ticket_id"]
    events = [e["event"] for e in payload["audit"]]
    assert "created" in events and "triaged" in events


def test_get_missing_ticket_404(client):
    assert client.get("/tickets/t_missing").status_code == 404


def test_review_queue_and_approve(client):
    sub = client.post("/tickets/submit", json={
        "title": "Hack?", "body": "Someone logged into my account from another country.",
    }).json()
    # security = critical -> must land in review queue
    q = client.get("/review-queue").json()["tickets"]
    assert any(t["id"] == sub["ticket_id"] for t in q)
    r = client.post(f"/review/{sub['ticket_id']}", json={
        "decision": "approve", "reviewer": "ana", "notes": "confirmed",
    })
    assert r.status_code == 200
    assert r.json()["ticket"]["status"] == "reviewed"


def test_review_override_validates_label(client):
    sub = client.post("/tickets/submit", json={
        "title": "Slow app", "body": "The app takes forever to load.",
    }).json()
    bad = client.post(f"/review/{sub['ticket_id']}", json={
        "decision": "override", "label": "not_a_label", "reviewer": "ana",
    })
    assert bad.status_code == 422
    good = client.post(f"/review/{sub['ticket_id']}", json={
        "decision": "override", "label": "performance", "reviewer": "ana",
    })
    assert good.status_code == 200
    assert good.json()["ticket"]["label"] == "performance"


def test_metrics_endpoint(client):
    client.post("/tickets/submit", json={"title": "Q", "body": "How do I invite teammates?"})
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.json()["total"] >= 1
