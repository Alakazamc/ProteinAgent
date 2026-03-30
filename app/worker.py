from __future__ import annotations
import asyncio

import logging
from typing import Any

from celery import Celery

from .agent import ProteinAgent
from .config import load_config
from .database import AsyncSessionLocal
from .models import AgentExecutionRecord, JobStatus

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
            # 1. First, fetch and mark the record as RUNNING
            # (Note: Usually the record is created in the API endpoint as PENDING)
            # 2. Run the agent (Agent run is synchronous, but we just call it here. 
            # In a heavy load scenario, one might run this in a threadpool)
            agent = get_agent()
            result = agent.run(query=query, protein_sequence=protein_sequence, include_metrics=include_metrics)
            
            # 3. Update the database record with success results
            import sqlalchemy as sa
            stmt = sa.select(AgentExecutionRecord).where(AgentExecutionRecord.task_id == task_id)
            db_result = await db.execute(stmt)
            record = db_result.scalar_one_or_none()
            
            if record:
                record.status = JobStatus.SUCCESS
                record.task_type = result.task_type.value if hasattr(result.task_type, "value") else str(result.task_type)
                record.model_provider = result.selected_model_provider
                record.model_name = result.selected_model_name
                record.generated_sequence = result.generated_sequence
                record.route_reason = result.route_reason
                record.output_text = result.output_text
                record.metrics = result.metrics
                record.rag_context = result.rag_context
                record.completed_at = sa.func.now()
                await db.commit()
                
            return {"status": "success", "task_id": task_id}
            
        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            import sqlalchemy as sa
            stmt = sa.select(AgentExecutionRecord).where(AgentExecutionRecord.task_id == task_id)
            db_result = await db.execute(stmt)
            record = db_result.scalar_one_or_none()
            if record:
                record.status = JobStatus.FAILED
                record.error_message = str(e)
                record.completed_at = sa.func.now()
                await db.commit()
            raise e


@celery_app.task(bind=True, name="protein_agent.run_agent_task")
def run_agent_task(self, task_id: str, query: str, protein_sequence: str | None, include_metrics: bool) -> dict[str, Any]:
    """Celery task entry point."""
    logger.info(f"Starting agent task {task_id} for query: {query}")
    
    # Run the async execution logic synchronously
    return asyncio.run(_run_and_save_async(task_id, query, protein_sequence, include_metrics))
