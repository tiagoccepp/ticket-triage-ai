"""HybridPolicy routing tests."""

from src.hybrid import HybridInput, HybridPolicy


def _policy() -> HybridPolicy:
    return HybridPolicy(review_threshold=0.55, auto_threshold=0.80)


def test_agreement_high_confidence_auto_routes():
    d = _policy().decide(
        HybridInput(label="billing", confidence=0.85),
        HybridInput(label="billing", confidence=0.90),
    )
    assert d.action == "auto_route"
    assert d.agreement is True
    assert d.final_label == "billing"


def test_disagreement_routes_to_review():
    d = _policy().decide(
        HybridInput(label="billing", confidence=0.85),
        HybridInput(label="bug_report", confidence=0.88),
    )
    assert d.action == "human_review"
    assert d.agreement is False
    assert any("DISAGREEMENT" in r for r in d.reasons)


def test_high_severity_routes_to_review_even_when_agreeing():
    d = _policy().decide(
        HybridInput(label="security", confidence=0.95),
        HybridInput(label="security", confidence=0.95),
    )
    assert d.action == "human_review"
    assert any("HIGH_SEVERITY" in r for r in d.reasons)


def test_low_confidence_routes_to_review():
    d = _policy().decide(
        HybridInput(label="billing", confidence=0.40),
        HybridInput(label="billing", confidence=0.45),
    )
    assert d.action == "human_review"
    assert any("LOW_CONFIDENCE" in r for r in d.reasons)


def test_abstention_forces_review():
    d = _policy().decide(
        HybridInput(label="billing", confidence=0.85),
        HybridInput(label="abstain", confidence=0.0, abstained=True),
    )
    assert d.action == "human_review"
    assert "ABSTENTION" in d.reasons


def test_winner_is_higher_confidence():
    d = _policy().decide(
        HybridInput(label="billing", confidence=0.60),
        HybridInput(label="billing", confidence=0.95),
    )
    assert d.final_confidence == 0.95
