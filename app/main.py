from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .agent import ProteinAgent, ProteinAgentError
from .config import load_config
from .knowledge_base import get_cached_knowledge_base
from .model_clients import ModelClientError


app = FastAPI(title="Protein Agent API", version="0.2.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1, description="包含任务描述的自然语言 query。")
    protein_sequence: Optional[str] = Field(
        default=None,
        description="可选。若 query 中没有直接包含蛋白质序列，可单独传入该字段。",
    )
    include_metrics: bool = Field(default=True, description="是否返回本地计算的评价指标。")


class RouteResponse(BaseModel):
    task_type: str
    matched_keywords: list[str]
    reason: str


class SelectedModelResponse(BaseModel):
    task_type: str
    provider: str
    model_name: str
    base_url: Optional[str] = None
    configured: bool


class RagChunkResponse(BaseModel):
    text: str
    source: str
    score: float


class RunResponse(BaseModel):
    task_type: str
    matched_keywords: list[str]
    route_reason: str
    selected_model: SelectedModelResponse
    protein_sequence: str
    generated_sequence: Optional[str] = None
    output_text: str
    metrics: dict[str, Any]
    rag_context: list[RagChunkResponse]


def _build_agent() -> ProteinAgent:
    return _build_agent_with_options(include_knowledge_base=True)


def _build_agent_with_options(include_knowledge_base: bool) -> ProteinAgent:
    config = load_config()
    knowledge_base = None
    if include_knowledge_base and config.rag_enabled:
        knowledge_base = get_cached_knowledge_base(
            data_path=config.rag_data_path or None,
            backend=config.rag_backend,
            embedding_model=config.rag_embedding_model,
        )
    return ProteinAgent(config=config, knowledge_base=knowledge_base)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, object]:
    agent = _build_agent_with_options(include_knowledge_base=True)
    kb = agent.knowledge_base
    return {
        "status": "ok",
        "service": "protein-agent",
        "models": agent.list_models(),
        "rag": {
            "enabled": kb is not None and kb.ready,
            "entries": kb.entry_count if kb else 0,
            "backend": kb.backend_name if kb else "disabled",
        },
    }


@app.get("/models", response_model=list[SelectedModelResponse])
def list_models() -> list[SelectedModelResponse]:
    agent = _build_agent_with_options(include_knowledge_base=False)
    return [SelectedModelResponse(**item) for item in agent.list_models()]


@app.get("/knowledge")
def knowledge() -> dict[str, object]:
    agent = _build_agent_with_options(include_knowledge_base=True)
    kb = agent.knowledge_base
    if kb is None or not kb.ready:
        return {"ready": False, "count": 0, "entries": []}
    return {
        "ready": True,
        "count": kb.entry_count,
        "backend": kb.backend_name,
        "entries": kb.list_entries(),
    }


@app.post("/route", response_model=RouteResponse)
def route(payload: RunRequest) -> RouteResponse:
    agent = _build_agent_with_options(include_knowledge_base=False)
    try:
        decision = agent.route(payload.query)
    except ProteinAgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RouteResponse(
        task_type=decision.task_type.value,
        matched_keywords=list(decision.matched_keywords),
        reason=decision.reason,
    )


@app.post("/run", response_model=RunResponse)
def run(payload: RunRequest) -> RunResponse:
    agent = _build_agent_with_options(include_knowledge_base=True)
    try:
        result = agent.run(
            query=payload.query,
            protein_sequence=payload.protein_sequence,
            include_metrics=payload.include_metrics,
        )
    except ModelClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProteinAgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    selected_model = SelectedModelResponse(
        task_type=result.task_type.value,
        provider=result.selected_model_provider,
        model_name=result.selected_model_name,
        base_url=result.selected_model_base_url,
        configured=(
            result.selected_model_provider == "local-stub"
            or bool(result.selected_model_base_url)
        ),
    )
    rag_chunks = [
        RagChunkResponse(text=c["text"], source=c["source"], score=c["score"])
        for c in result.rag_context
    ]
    return RunResponse(
        task_type=result.task_type.value,
        matched_keywords=list(result.matched_keywords),
        route_reason=result.route_reason,
        selected_model=selected_model,
        protein_sequence=result.protein_sequence,
        generated_sequence=result.generated_sequence,
        output_text=result.output_text,
        metrics=result.metrics,
        rag_context=rag_chunks,
    )


@app.get("/static/{asset_path:path}", include_in_schema=False)
def static_assets(asset_path: str) -> FileResponse:
    target = (STATIC_DIR / asset_path).resolve()
    if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists():
        raise HTTPException(status_code=404, detail="Static asset not found")
    return FileResponse(target)
