from __future__ import annotations

import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, String, lambda_stmt
from sqlalchemy.sql import func

from .database import Base


class JobStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class AgentExecutionRecord(Base):
    __tablename__ = "agent_executions"

    # UUID Primary Key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    
    # Celery task ID
    task_id = Column(String(36), unique=True, index=True, nullable=False)
    
    # Execution Status
    status = Column(String(20), default=JobStatus.PENDING, index=True, nullable=False)
    
    # Inputs
    request_query = Column(String, nullable=False)
    input_sequence = Column(String, nullable=True)
    
    # Outputs / Results
    task_type = Column(String(50), nullable=True)
    matched_keywords = Column(JSON, nullable=True)
    model_provider = Column(String(50), nullable=True)
    model_name = Column(String(100), nullable=True)
    generated_sequence = Column(String, nullable=True)
    route_reason = Column(String, nullable=True)
    output_text = Column(String, nullable=True)
    
    # JSON Fields (For nested metadata)
    metrics = Column(JSON, nullable=True)
    rag_context = Column(JSON, nullable=True)
    trace_events = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "status": self.status,
            "request_query": self.request_query,
            "input_sequence": self.input_sequence,
            "task_type": self.task_type,
            "matched_keywords": self.matched_keywords or [],
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "generated_sequence": self.generated_sequence,
            "route_reason": self.route_reason,
            "output_text": self.output_text,
            "metrics": self.metrics,
            "rag_context": self.rag_context,
            "trace_events": self.trace_events or [],
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
