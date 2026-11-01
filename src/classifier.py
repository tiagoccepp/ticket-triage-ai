"""Classification pipeline: backends + validity gate + policy.

Components:
  - LLMBackend: OpenAI-compatible chat call; falls back to MockLLM when no key.
  - LexicalBackend: offline TF-IDF cosine over taxonomy descriptions (CI-safe).
  - ValidityGate: enforced in CODE (not prompt) — unknown labels -> conf 0.
  - DuplicateIndex: TF-IDF cosine duplicate detection (embeddings optional).
  - ThresholdPolicy: confidence-gated automation with abstention.
  - TriagePipeline: orchestrates baseline + model + hybrid + persistence.

Abstention is first-class: low/zero confidence produces action=human_review
or abstain, never a silent guess.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.request
from collections import Counter
from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.baseline import BaselineResult, classify_baseline
from src.config import Settings, get_settings
from src.hybrid import HybridDecision, HybridInput, HybridPolicy
from src.taxonomy import (
    TAXONOMY,
    Category,
    is_valid_label,
    render_full_prompt,
    severity_of,
)

ABSTAIN_LABEL = "abstain"


# ----------------------------------------------------------------------------
# Result model
# ----------------------------------------------------------------------------
class ClassificationResult(BaseModel):
    label: str
    confidence: float
    runner_up: str | None = None
    runner_up_confidence: float = 0.0
    method: str = "llm"
    reasoning: str = ""
    latency_ms: float = 0.0
    abstained: bool = False


class ThresholdPolicy(BaseModel):
    auto_threshold: float = 0.80
    review_threshold: float = 0.55

    def action_for(self, result: ClassificationResult) -> str:
        if result.abstained or result.label == ABSTAIN_LABEL:
            return "abstain"
        if result.confidence >= self.auto_threshold:
            return "auto_route"
        if result.confidence >= self.review_threshold:
            return "human_review"
        return "abstain"


# ----------------------------------------------------------------------------
# Validity gate (CODE-enforced, not prompt-enforced)
# ----------------------------------------------------------------------------
def validity_gate(result: ClassificationResult) -> ClassificationResult:
    """Unknown/hallucinated labels -> confidence 0 + abstained. Always applied."""
    if result.label == ABSTAIN_LABEL:
        result.abstained = True
        result.confidence = 0.0
        return result
    if not is_valid_label(result.label):
        result.reasoning = (
            f"{result.reasoning} [VALIDITY GATE: '{result.label}' not in taxonomy]"
        ).strip()
        result.label = ABSTAIN_LABEL
        result.confidence = 0.0
        result.runner_up = None
        result.runner_up_confidence = 0.0
        result.abstained = True
    return result


# ----------------------------------------------------------------------------
# Tokenizer + TF-IDF utilities (pure stdlib, offline)
# ----------------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class TfidfVectorizer:
    """Minimal TF-IDF with cosine similarity. Fitted on taxonomy corpus."""

    def __init__(self) -> None:
        self.idf: dict[str, float] = {}
        self.n_docs: int = 0

    def fit(self, docs: list[str]) -> None:
        self.n_docs = max(len(docs), 1)
        df: Counter[str] = Counter()
        for d in docs:
            for tok in set(tokenize(d)):
                df[tok] += 1
        self.idf = {
            tok: math.log((1 + self.n_docs) / (1 + freq)) + 1.0
            for tok, freq in df.items()
        }

    def vector(self, text: str) -> dict[str, float]:
        toks = tokenize(text)
        if not toks:
            return {}
        tf = Counter(toks)
        total = len(toks)
        vec = {}
        for tok, count in tf.items():
            idf = self.idf.get(tok, math.log(1 + self.n_docs) + 1.0)
            vec[tok] = (count / total) * idf
        return vec

    @staticmethod
    def cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(a.get(k, 0.0) * v for k, v in b.items())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


# ----------------------------------------------------------------------------
# Lexical backend (offline TF-IDF)
# ----------------------------------------------------------------------------
class LexicalBackend:
    """Offline backend: TF-IDF cosine between ticket and category documents."""

    def __init__(self, categories: list[Category] | None = None) -> None:
        self.categories = categories or TAXONOMY
        self.vec = TfidfVectorizer()
        docs = [self._category_doc(c) for c in self.categories]
        self.vec.fit(docs)
        self.cat_vectors = {c.id: self.vec.vector(self._category_doc(c)) for c in self.categories}

    @staticmethod
    def _category_doc(cat: Category) -> str:
        parts = [cat.name, cat.description, " ".join(cat.keywords), " ".join(cat.examples)]
        return " ".join(parts)

    def classify(self, text: str) -> ClassificationResult:
        start = time.perf_counter()
        tv = self.vec.vector(text)
        scores = {
            cid: self.vec.cosine(tv, cv) for cid, cv in self.cat_vectors.items()
        }
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_id, top = ranked[0]
        second_id, second = ranked[1] if len(ranked) > 1 else ("", 0.0)
        # Map cosine (typically 0..0.5 for short texts) to calibrated confidence
        confidence = round(min(0.95, top * 2.2), 3)
        runner_conf = round(min(0.95, second * 2.2), 3)
        latency = (time.perf_counter() - start) * 1000
        if top <= 0.01:
            return ClassificationResult(
                label=ABSTAIN_LABEL,
                confidence=0.0,
                method="lexical",
                reasoning="no lexical overlap with taxonomy",
                latency_ms=round(latency, 2),
                abstained=True,
            )
        return ClassificationResult(
            label=top_id,
            confidence=confidence,
            runner_up=second_id if second > 0 else None,
            runner_up_confidence=runner_conf,
            method="lexical",
            reasoning=f"tfidf cosine top={top:.3f} runner={second:.3f}",
            latency_ms=round(latency, 2),
        )


# ----------------------------------------------------------------------------
# LLM backends
# ----------------------------------------------------------------------------
class Backend(Protocol):
    def classify(self, text: str) -> ClassificationResult: ...


class MockLLMBackend:
    """Deterministic mock that mimics an LLM JSON response. Keyless, for CI.

    Uses a richer signal than the baseline (weighted phrases + description
    overlap) so evals exercise the full pipeline offline.
    """

    method = "mock-llm"

    def __init__(self, categories: list[Category] | None = None) -> None:
        self.categories = categories or TAXONOMY
        self._lex = LexicalBackend(self.categories)

    def classify(self, text: str) -> ClassificationResult:
        start = time.perf_counter()
        lex = self._lex.classify(text)
        base = classify_baseline(text, self.categories)
        # Mock "LLM judgment": lexical signal boosted when baseline agrees
        if lex.label == base.label and not lex.abstained:
            conf = round(min(0.93, lex.confidence + 0.08), 3)
        else:
            conf = round(lex.confidence * 0.9, 3)
        latency = (time.perf_counter() - start) * 1000
        if lex.abstained:
            return ClassificationResult(
                label=ABSTAIN_LABEL, confidence=0.0, method=self.method,
                reasoning="mock-llm: insufficient signal", latency_ms=round(latency, 2),
                abstained=True,
            )
        return ClassificationResult(
            label=lex.label, confidence=conf,
            runner_up=lex.runner_up, runner_up_confidence=lex.runner_up_confidence,
            method=self.method,
            reasoning=f"mock-llm judgment; {lex.reasoning}",
            latency_ms=round(latency, 2),
        )


class OpenAICompatibleBackend:
    """Minimal OpenAI-compatible chat backend (stdlib http, no SDK needed)."""

    method = "llm"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def classify(self, text: str) -> ClassificationResult:
        start = time.perf_counter()
        if not self.settings.llm_enabled:
            # Keyless fallback -> deterministic mock
            mock = MockLLMBackend().classify(text)
            mock.method = "llm-fallback-mock"
            return mock
        prompt = render_full_prompt(text)
        body = json.dumps({
            "model": self.settings.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }).encode()
        req = urllib.request.Request(
            f"{self.settings.llm_base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.llm_api_key}",
            },
            method="POST",
        )
        latency = 0.0
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
            label = str(data.get("label", ABSTAIN_LABEL))
            conf = float(data.get("confidence", 0.0))
            runner = data.get("runner_up")
            reason = str(data.get("reason", ""))
        except Exception as exc:  # network/parse failure -> abstain, never guess
            latency = (time.perf_counter() - start) * 1000
            return ClassificationResult(
                label=ABSTAIN_LABEL, confidence=0.0, method=self.method,
                reasoning=f"llm call failed, abstaining: {exc}",
                latency_ms=round(latency, 2), abstained=True,
            )
        latency = (time.perf_counter() - start) * 1000
        result = ClassificationResult(
            label=label, confidence=max(0.0, min(1.0, conf)),
            runner_up=runner if isinstance(runner, str) else None,
            method=self.method, reasoning=reason,
            latency_ms=round(latency, 2),
        )
        return validity_gate(result)


def get_backend(name: str = "auto", settings: Settings | None = None) -> Backend:
    s = settings or get_settings()
    if name == "lexical":
        return LexicalBackend()
    if name == "mock":
        return MockLLMBackend()
    if name == "llm":
        return OpenAICompatibleBackend(s)
    # auto: llm when key present, else lexical (offline-safe)
    if s.llm_enabled:
        return OpenAICompatibleBackend(s)
    return LexicalBackend()


# ----------------------------------------------------------------------------
# Duplicate index (TF-IDF; swap vectors for embeddings in production)
# ----------------------------------------------------------------------------
class DuplicateIndex:
    """In-memory near-duplicate detector. Threshold-tuned cosine."""

    def __init__(self, threshold: float = 0.82) -> None:
        self.threshold = threshold
        self.vec = TfidfVectorizer()
        self._texts: dict[str, str] = {}
        self._vectors: dict[str, dict[str, float]] = {}
        self._fitted = False

    def _refit(self) -> None:
        docs = list(self._texts.values()) or ["empty"]
        self.vec.fit(docs)
        self._vectors = {tid: self.vec.vector(t) for tid, t in self._texts.items()}
        self._fitted = True

    def add(self, ticket_id: str, text: str) -> None:
        self._texts[ticket_id] = text
        self._fitted = False

    def find(self, text: str, top_k: int = 3) -> list[tuple[str, float]]:
        if not self._texts:
            return []
        if not self._fitted:
            self._refit()
        tv = self.vec.vector(text)
        scored = [
            (tid, self.vec.cosine(tv, vec)) for tid, vec in self._vectors.items()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def duplicate_of(self, text: str) -> tuple[str | None, float]:
        hits = self.find(text, top_k=1)
        if hits and hits[0][1] >= self.threshold:
            return hits[0]
        return None, hits[0][1] if hits else 0.0


# ----------------------------------------------------------------------------
# Triage outcome + pipeline
# ----------------------------------------------------------------------------
class TriageOutcome(BaseModel):
    ticket_id: str = ""
    label: str
    confidence: float
    runner_up: str | None = None
    action: str  # auto_route | human_review | abstain
    reasons: list[str] = Field(default_factory=list)
    agreement: bool = True
    baseline_label: str = ""
    model_label: str = ""
    duplicate_of: str | None = None
    duplicate_score: float = 0.0
    latency_ms: float = 0.0


class TriagePipeline:
    """Full pipeline: baseline + model -> validity gate -> hybrid -> persist."""

    def __init__(
        self,
        settings: Settings | None = None,
        backend: Backend | None = None,
        store: Any | None = None,
        duplicates: DuplicateIndex | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.backend = backend or get_backend("auto", self.settings)
        self.policy = ThresholdPolicy(
            auto_threshold=self.settings.auto_threshold,
            review_threshold=self.settings.review_threshold,
        )
        self.hybrid = HybridPolicy(
            review_threshold=self.settings.review_threshold,
            auto_threshold=self.settings.auto_threshold,
        )
        self.duplicates = duplicates or DuplicateIndex(
            threshold=self.settings.duplicate_threshold
        )
        self._store = store  # lazy to keep imports light

    @property
    def store(self):  # type: ignore[no-untyped-def]
        if self._store is None:
            from src.db import TicketStore
            self._store = TicketStore(self.settings)
        return self._store

    def triage(
        self, title: str, body: str, customer_id: str = "",
        persist: bool = True,
    ) -> TriageOutcome:
        start = time.perf_counter()
        text = f"{title}\n{body}".strip()

        # 1. Both classifiers
        base: BaselineResult = classify_baseline(text)
        model: ClassificationResult = self.backend.classify(text)

        # 2. Validity gate on the model output (code-enforced)
        model = validity_gate(model)

        # 3. Hybrid routing decision
        decision: HybridDecision = self.hybrid.decide(
            HybridInput(label=base.label, confidence=base.confidence),
            HybridInput(label=model.label, confidence=model.confidence,
                        abstained=model.abstained),
        )

        # 4. Threshold policy refines model-only edge cases
        policy_action = self.policy.action_for(model)
        action = decision.action
        reasons = list(decision.reasons)
        if policy_action == "abstain" and action == "auto_route":
            action = "human_review"
            reasons.append("POLICY:abstain->review")

        # 5. Duplicate check
        dup_id, dup_score = self.duplicates.duplicate_of(text)

        # 6. Severity annotation
        sev = severity_of(decision.final_label) if decision.final_label != ABSTAIN_LABEL else "medium"

        latency = (time.perf_counter() - start) * 1000
        outcome = TriageOutcome(
            label=decision.final_label,
            confidence=decision.final_confidence,
            runner_up=model.runner_up,
            action=action,
            reasons=reasons,
            agreement=decision.agreement,
            baseline_label=base.label,
            model_label=model.label,
            duplicate_of=dup_id,
            duplicate_score=round(dup_score, 3),
            latency_ms=round(latency, 2),
        )

        if persist:
            status = {"auto_route": "routed", "human_review": "needs_review",
                      "abstain": "abstained"}[action]
            row = self.store.create_ticket(
                title=title, body=body, customer_id=customer_id,
                label=outcome.label, confidence=outcome.confidence,
                runner_up=outcome.runner_up or "",
                status=status, duplicate_of=outcome.duplicate_of or "",
            )
            outcome.ticket_id = row["id"]
            self.duplicates.add(row["id"], text)
            self.store.add_audit(row["id"], "triaged", {
                "label": outcome.label, "confidence": outcome.confidence,
                "runner_up": outcome.runner_up, "action": action,
                "reasons": reasons, "agreement": decision.agreement,
                "baseline": {"label": base.label, "confidence": base.confidence},
                "model": {"label": model.label, "confidence": model.confidence,
                          "method": model.method},
                "duplicate_of": dup_id, "duplicate_score": round(dup_score, 3),
                "severity": sev, "latency_ms": outcome.latency_ms,
            })
        return outcome
