"""Pydantic schemas for data throughout the pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Preprocessed input ──────────────────────────────────────

class ContextMessage(BaseModel):
    speaker: str
    sender_type: str  # "student" or "agent"
    content: str


class CodingInput(BaseModel):
    id: str
    group_id: str
    turn_index: int
    created_at: Optional[str] = None
    speaker: str
    sender_type: str = "student"
    content: str
    previous_3_messages: list[ContextMessage] = Field(default_factory=list)
    low_information_candidate: bool = False


# ── Coding output ───────────────────────────────────────────

class CodingResult(BaseModel):
    id: str
    label: Optional[str] = None  # IS1|IS2|IS3|IS4 or None on parse failure
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    evidence_span: Optional[str] = None
    uncertainty: Optional[str] = None
    alternative_label: Optional[str] = None
    why_not_alternative: Optional[str] = None
    agent: str  # "A" or "B"
    model: str
    raw_response: Optional[str] = None
    parse_ok: bool = False
    error: Optional[str] = None


# ── Metrics ─────────────────────────────────────────────────

class Disagreement(BaseModel):
    id: str
    content: str
    agent_a_label: Optional[str]
    agent_b_label: Optional[str]
    agent_a_rationale: Optional[str] = None
    agent_b_rationale: Optional[str] = None
    agent_a_alternative_label: Optional[str] = None
    agent_b_alternative_label: Optional[str] = None
    agent_a_why_not_alternative: Optional[str] = None
    agent_b_why_not_alternative: Optional[str] = None
    possible_boundary: Optional[str] = None
    group_id: Optional[str] = None
    turn_index: Optional[int] = None


class PerLabelMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    support: int


class KappaReport(BaseModel):
    unweighted_kappa: float
    weighted_kappa: Optional[float] = None
    n_total: int
    n_valid: int
    n_invalid: int
    invalid_rate: float
    label_distribution_agent_a: dict[str, int] = Field(default_factory=dict)
    label_distribution_agent_b: dict[str, int] = Field(default_factory=dict)
    per_label_metrics: dict[str, PerLabelMetrics] = Field(default_factory=dict)


# ── Good evaluation ─────────────────────────────────────────

class GoodEvaluationResult(BaseModel):
    model_kappa_vs_good: float
    model_accuracy_vs_good: float
    n_matched: int
    n_total: int
    per_label_metrics: dict[str, PerLabelMetrics] = Field(default_factory=dict)
