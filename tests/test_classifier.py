"""Classifier backend + policy tests (offline, keyless)."""

from src.classifier import (
    DuplicateIndex,
    LexicalBackend,
    MockLLMBackend,
    ThresholdPolicy,
    TfidfVectorizer,
    ClassificationResult,
)
from src.taxonomy import is_valid_label


def test_lexical_classifies_billing_ticket():
    backend = LexicalBackend()
    res = backend.classify("I was charged twice on my last invoice, please refund")
    assert res.label == "billing"
    assert res.confidence > 0.1
    assert not res.abstained


def test_lexical_returns_runner_up():
    backend = LexicalBackend()
    res = backend.classify("login password reset account locked")
    assert res.runner_up is None or is_valid_label(res.runner_up)


def test_lexical_abstains_on_gibberish():
    backend = LexicalBackend()
    res = backend.classify("xqzt blorp fnord zzzqq")
    assert res.abstained
    assert res.confidence == 0.0


def test_mock_llm_returns_valid_label():
    backend = MockLLMBackend()
    res = backend.classify("The dashboard crashes with a 500 error on export")
    assert res.label == "bug_report"
    assert 0 < res.confidence <= 1


def test_mock_llm_is_deterministic():
    backend = MockLLMBackend()
    a = backend.classify("webhook deliveries failing with 401")
    b = backend.classify("webhook deliveries failing with 401")
    assert a.label == b.label and a.confidence == b.confidence


def test_tfidf_cosine_identical_is_one():
    vec = TfidfVectorizer()
    vec.fit(["hello world", "other doc"])
    v = vec.vector("hello world")
    assert abs(vec.cosine(v, v) - 1.0) < 1e-6


def test_duplicate_index_finds_near_dup():
    idx = DuplicateIndex(threshold=0.5)
    idx.add("t_1", "my invoice shows a double charge this month")
    dup_id, score = idx.duplicate_of("my invoice shows a double charge this month!")
    assert dup_id == "t_1"
    assert score >= 0.5


def test_duplicate_index_empty_returns_none():
    idx = DuplicateIndex()
    dup_id, score = idx.duplicate_of("anything")
    assert dup_id is None


def test_threshold_policy_actions():
    policy = ThresholdPolicy(auto_threshold=0.8, review_threshold=0.55)
    assert policy.action_for(ClassificationResult(label="billing", confidence=0.9)) == "auto_route"
    assert policy.action_for(ClassificationResult(label="billing", confidence=0.6)) == "human_review"
    assert policy.action_for(ClassificationResult(label="billing", confidence=0.2)) == "abstain"
    assert policy.action_for(
        ClassificationResult(label="abstain", confidence=0.0, abstained=True)
    ) == "abstain"
