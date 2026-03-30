from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from .agent import ProteinAgent, ProteinAgentError
from .config import load_config
from .database import Base, engine, get_db
from .knowledge_base import get_cached_knowledge_base
from .model_clients import ModelClientError
from .models import AgentExecutionRecord, JobStatus
from .worker import run_agent_task

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database
    async with engine.begin() as conn:
        # Create all tables (WARNING: this is for development; in production use Alembic)
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Protein Agent API", version="0.3.0", lifespan=lifespan)
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


class TaskCreatedResponse(BaseModel):
    task_id: str
    status: str
    message: str


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
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    agent = _build_agent_with_options(include_knowledge_base=True)
    kb = agent.knowledge_base
    
    # Simple db health check
    db_ok = False
    try:
        await db.execute(sa.text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
        
    return {
        "status": "ok",
        "service": "protein-agent",
        "database": "ok" if db_ok else "error",
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


@app.post("/run", response_model=TaskCreatedResponse)
async def run(payload: RunRequest, db: AsyncSession = Depends(get_db)) -> TaskCreatedResponse:
    """Async endpoint that queues the agent task and returns a task_id immediately."""
    task_id = str(uuid4())
    
    # Save the initial PENDING state in the database
    record = AgentExecutionRecord(
        task_id=task_id,
        status=JobStatus.PENDING,
        request_query=payload.query,
        input_sequence=payload.protein_sequence,
    )
    db.add(record)
    await db.commit()
    
    # Dispatch Celery background task
    run_agent_task.delay(
        task_id, 
        payload.query, 
        payload.protein_sequence, 
        payload.include_metrics
    )
    
    return TaskCreatedResponse(
        task_id=task_id,
        status=JobStatus.PENDING,
        message="Job created and is running in the background."
    )


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Poll for the status of an agent execution task."""
    stmt = sa.select(AgentExecutionRecord).where(AgentExecutionRecord.task_id == task_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return record.to_dict()


@app.get("/history")
async def get_task_history(limit: int = 50, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """Retrieve the history of past agent executions, ordered by latest first."""
    stmt = sa.select(AgentExecutionRecord).order_by(AgentExecutionRecord.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    return [r.to_dict() for r in records]


@app.get("/static/{asset_path:path}", include_in_schema=False)
def static_assets(asset_path: str) -> FileResponse:
    target = (STATIC_DIR / asset_path).resolve()
    if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists():
        raise HTTPException(status_code=404, detail="Static asset not found")
    return FileResponse(target)
