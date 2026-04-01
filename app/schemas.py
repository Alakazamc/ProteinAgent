from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    PEPTIDE_GENERATION = "peptide_generation"
    APTAMER_GENERATION = "aptamer_generation"
    PROTEIN_PREDICTION = "protein_prediction"


@dataclass(frozen=True)
class RouteDecision:
    task_type: TaskType
    matched_keywords: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ModelExecutionRequest:
    task_type: TaskType
    query: str
    protein_sequence: str


@dataclass(frozen=True)
class ModelExecutionResult:
    output_text: str
    generated_sequence: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class TraceEvent:
    step: str
    title: str
    detail: str = ""
    status: str = "completed"

    def to_dict(self) -> dict[str, str]:
        return {
            "step": self.step,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
        }


@dataclass(frozen=True)
class AgentExecutionResult:
    task_type: TaskType
    matched_keywords: tuple[str, ...]
    route_reason: str
    protein_sequence: str
    selected_model_name: str
    selected_model_provider: str
    selected_model_base_url: str | None
    output_text: str
    generated_sequence: str | None
    metrics: dict[str, Any]
    rag_context: list[dict[str, Any]] = field(default_factory=list)
    trace_events: list[dict[str, str]] = field(default_factory=list)

