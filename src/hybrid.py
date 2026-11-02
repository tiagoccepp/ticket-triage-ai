"""Hybrid policy: routes uncertain or risky tickets to human review.

Three routing triggers (checked in order):
  1. HIGH_SEVERITY — predicted category severity is high/critical -> review
  2. LOW_CONFIDENCE — winner confidence below review_threshold -> review
  3. DISAGREEMENT — baseline and LLM top labels differ -> review

Otherwise the LLM (or lexical) prediction auto-routes. Abstention is a
first-class outcome: either side abstaining forces human review.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.taxonomy import HIGH_SEVERITY, severity_of


class HybridInput(BaseModel):
    label: str
    confidence: float
    abstained: bool = False


class HybridDecision(BaseModel):
    final_label: str
    final_confidence: float
    action: str = Field(default="auto_route")  # auto_route | human_review | abstain
    agreement: bool = True
    reasons: list[str] = Field(default_factory=list)


class HybridPolicy(BaseModel):
    review_threshold: float = 0.55
    auto_threshold: float = 0.80

    def decide(self, baseline: HybridInput, model: HybridInput) -> HybridDecision:
        reasons: list[str] = []

        # Abstention anywhere -> human review, keep best-effort label
        if baseline.abstained or model.abstained:
            reasons.append("ABSTENTION")
            best = model if model.confidence >= baseline.confidence else baseline
            return HybridDecision(
                final_label=best.label,
                final_confidence=round(min(best.confidence, 0.49), 3),
                action="human_review",
                agreement=False,
                reasons=reasons,
            )

        agreement = baseline.label == model.label

        # Winner = higher confidence
        winner = model if model.confidence >= baseline.confidence else baseline

        # Trigger 1: high severity always gets human eyes
        if severity_of(winner.label) in HIGH_SEVERITY:
            reasons.append(f"HIGH_SEVERITY:{winner.label}")
        # Trigger 2: low confidence
        if winner.confidence < self.review_threshold:
            reasons.append(
                f"LOW_CONFIDENCE:{winner.confidence:.2f}<{self.review_threshold}"
            )
        # Trigger 3: disagreement between baseline and model
        if not agreement:
            reasons.append(f"DISAGREEMENT:baseline={baseline.label},model={model.label}")

        action = "human_review" if reasons else "auto_route"
        return HybridDecision(
            final_label=winner.label,
            final_confidence=winner.confidence,
            action=action,
            agreement=agreement,
            reasons=reasons,
        )
