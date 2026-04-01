from __future__ import annotations
import asyncio

import logging
from typing import Any

import sqlalchemy as sa
from celery import Celery

from .agent import PreparedAgentRun, ProteinAgent
from .config import load_config
from .database import AsyncSessionLocal
from .models import AgentExecutionRecord, JobStatus
from .schemas import TraceEvent

logger = logging.getLogger(__name__)

# Initialize configurations
config = load_config()

# Initialize Celery app
celery_app = Celery(
    "protein_agent_tasks",
    broker=config.celery_broker_url,
    backend=config.celery_broker_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Global lazy-initialized agent to avoid reloading RAG FAISS index for every task
_agent_instance = None


def get_agent() -> ProteinAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = ProteinAgent(config)
    return _agent_instance


async def _run_and_save_async(task_id: str, query: str, protein_sequence: str | None, include_metrics: bool) -> dict[str, Any]:
    """Async wrapper to handle DB operations while running the synchronous agent."""
    async with AsyncSessionLocal() as db:
        try:
            record = await _load_record(db, task_id)
            if record is None:
                raise RuntimeError(f"任务 {task_id} 不存在，无法更新执行状态。")

            record.status = JobStatus.RUNNING
            _append_trace_event(
                record,
                TraceEvent(
                    step="running",
                    title="开始执行任务",
                    detail="worker 已接管任务，正在分析请求并准备执行。",
                    status="running",
                ),
            )
            await db.commit()

            agent = get_agent()
            prepared = agent.prepare_execution(query=query, protein_sequence=protein_sequence)
            _apply_prepared_state(record, prepared)
            await db.commit()

            model_result = agent.run_model(query=query, prepared=prepared)
            _append_model_completion(record, prepared, model_result.generated_sequence)
            await db.commit()

            result = agent.finalize_execution(
                prepared=prepared,
                model_result=model_result,
                include_metrics=include_metrics,
            )

            record.status = JobStatus.SUCCESS
            record.task_type = (
                result.task_type.value if hasattr(result.task_type, "value") else str(result.task_type)
            )
            record.matched_keywords = list(result.matched_keywords)
            record.input_sequence = result.protein_sequence
            record.model_provider = result.selected_model_provider
            record.model_name = result.selected_model_name
            record.generated_sequence = result.generated_sequence
            record.route_reason = result.route_reason
            record.route_source = result.route_source
            record.router_output_text = result.router_output_text
            record.output_text = result.output_text
            record.metrics = result.metrics
            record.rag_context = result.rag_context
            record.trace_events = _merge_trace_events(record.trace_events, result.trace_events)
            record.completed_at = sa.func.now()
            await db.commit()

            return {"status": "success", "task_id": task_id}

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            record = await _load_record(db, task_id)
            if record:
                record.status = JobStatus.FAILED
                record.error_message = str(e)
                _append_trace_event(
                    record,
                    TraceEvent(
                        step="failed",
                        title="任务执行失败",
                        detail=str(e),
                        status="failed",
                    ),
                )
                record.completed_at = sa.func.now()
                await db.commit()
            raise e


@celery_app.task(bind=True, name="protein_agent.run_agent_task")
def run_agent_task(self, task_id: str, query: str, protein_sequence: str | None, include_metrics: bool) -> dict[str, Any]:
    """Celery task entry point."""
    logger.info(f"Starting agent task {task_id} for query: {query}")
    
    # Run the async execution logic synchronously
    return asyncio.run(_run_and_save_async(task_id, query, protein_sequence, include_metrics))


async def _load_record(db, task_id: str) -> AgentExecutionRecord | None:
    stmt = sa.select(AgentExecutionRecord).where(AgentExecutionRecord.task_id == task_id)
    db_result = await db.execute(stmt)
    return db_result.scalar_one_or_none()


def _append_trace_event(record: AgentExecutionRecord, event: TraceEvent) -> None:
    current_events = list(record.trace_events or [])
    current_events.append(event.to_dict())
    record.trace_events = current_events


def _apply_prepared_state(record: AgentExecutionRecord, prepared: PreparedAgentRun) -> None:
    record.task_type = prepared.route_decision.task_type.value
    record.matched_keywords = list(prepared.route_decision.matched_keywords)
    record.input_sequence = prepared.protein_sequence
    record.model_provider = prepared.model_config.provider
    record.model_name = prepared.model_config.model_name
    record.route_reason = prepared.route_decision.reason
    record.route_source = prepared.route_decision.route_source
    record.router_output_text = prepared.route_decision.router_output_text

    _append_trace_event(
        record,
        TraceEvent(
            step="route",
            title="识别任务类型",
            detail=prepared.route_decision.reason,
        ),
    )
    if prepared.route_decision.router_output_text:
        _append_trace_event(
            record,
            TraceEvent(
                step="router-llm-output",
                title="路由模型输出",
                detail=prepared.route_decision.router_output_text,
            ),
        )
    _append_trace_event(
        record,
        TraceEvent(
            step="sequence",
            title="提取蛋白质序列",
            detail=f"已规范化输入序列，长度 {len(prepared.protein_sequence)}。",
        ),
    )
    _append_trace_event(
        record,
        TraceEvent(
            step="rag",
            title="检索领域知识",
            detail=f"返回 {len(prepared.rag_context)} 条相关上下文。",
        ),
    )
    _append_trace_event(
        record,
        TraceEvent(
            step="model",
            title="选择执行模型",
            detail=(
                f"{prepared.model_config.model_name} "
                f"({prepared.model_config.provider})"
            ),
        ),
    )


def _append_model_completion(
    record: AgentExecutionRecord,
    prepared: PreparedAgentRun,
    generated_sequence: str | None,
) -> None:
    if generated_sequence:
        detail = (
            f"模型返回候选序列，长度 {len(generated_sequence)}，"
            f"任务类型为 {prepared.route_decision.task_type.value}。"
        )
    else:
        detail = (
            f"模型已返回分析文本，任务类型为 {prepared.route_decision.task_type.value}。"
        )
    _append_trace_event(
        record,
        TraceEvent(
            step="model-output",
            title="完成模型执行",
            detail=detail,
        ),
    )


def _merge_trace_events(
    existing_events: list[dict[str, Any]] | None,
    new_events: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged = list(existing_events or [])
    seen = {
        (
            event.get("step"),
            event.get("title"),
            event.get("detail"),
            event.get("status"),
        )
        for event in merged
    }

    for event in new_events or []:
        key = (
            event.get("step"),
            event.get("title"),
            event.get("detail"),
            event.get("status"),
        )
        if key in seen:
            continue
        merged.append(event)
        seen.add(key)
    return merged
