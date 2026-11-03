"""Validity gate tests: hallucinated labels must die in code, not in prompt."""

from src.classifier import ClassificationResult, validity_gate


def test_hallucinated_label_forced_to_zero_confidence():
    res = ClassificationResult(
        label="refunds_and_magic", confidence=0.99, method="llm",
        reasoning="model invented this",
    )
    out = validity_gate(res)
    assert out.label == "abstain"
    assert out.confidence == 0.0
    assert out.abstained is True
    assert "VALIDITY GATE" in out.reasoning


def test_valid_label_passes_through_untouched():
    res = ClassificationResult(label="billing", confidence=0.87, method="llm")
    out = validity_gate(res)
    assert out.label == "billing"
    assert out.confidence == 0.87
    assert out.abstained is False


def test_explicit_abstain_stays_abstained():
    res = ClassificationResult(label="abstain", confidence=0.4, method="llm")
    out = validity_gate(res)
    assert out.abstained is True
    assert out.confidence == 0.0


def test_empty_label_is_rejected():
    res = ClassificationResult(label="", confidence=0.7, method="llm")
    out = validity_gate(res)
    assert out.abstained is True
    assert out.confidence == 0.0
