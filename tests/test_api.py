from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from fastapi.testclient import TestClient


_TMPDIR = tempfile.TemporaryDirectory(prefix="protein_agent_api_tests_")
_DB_PATH = Path(_TMPDIR.name) / "protein_agent_api_test.db"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"
os.environ["PROTEIN_MODEL_PROVIDER"] = "local-stub"
os.environ["PEPTIDE_MODEL_PROVIDER"] = "local-stub"
os.environ["APTAMER_MODEL_PROVIDER"] = "local-stub"
os.environ["RAG_ENABLED"] = "true"
os.environ["RAG_BACKEND"] = "local-hash"
os.environ["ROUTER_LLM_PROVIDER"] = ""
os.environ["ROUTER_LLM_MODEL_NAME"] = ""
os.environ["ROUTER_LLM_BASE_URL"] = ""
os.environ["ROUTER_LLM_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = ""
os.environ["MODEL_NAME"] = ""
os.environ["MODEL_BASE_URL"] = ""
os.environ["MODEL_API_KEY"] = ""
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/9"

from app import main as main_module
from app import worker as worker_module
from app.database import AsyncSessionLocal, initialize_database
from app.models import AgentExecutionRecord, JobStatus
from app.schemas import TraceEvent


class ProteinAgentApiTests(unittest.TestCase):
    sequence = "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP"

    @classmethod
    def setUpClass(cls) -> None:
        asyncio.run(initialize_database())

    def setUp(self) -> None:
        asyncio.run(self._reset_db())

    async def _reset_db(self) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(sa.delete(AgentExecutionRecord))
            await db.commit()

    async def _get_record(self, task_id: str) -> AgentExecutionRecord | None:
        async with AsyncSessionLocal() as db:
            stmt = sa.select(AgentExecutionRecord).where(AgentExecutionRecord.task_id == task_id)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def _create_record(self, task_id: str, status: str) -> None:
        async with AsyncSessionLocal() as db:
            db.add(
                AgentExecutionRecord(
                    task_id=task_id,
                    status=status,
                    request_query="测试任务",
                    trace_events=[
                        TraceEvent(
                            step="seeded",
                            title="写入测试记录",
                            detail=f"当前状态 {status}",
                            status="running" if status == JobStatus.RUNNING else "completed",
                        ).to_dict()
                    ],
                )
            )
            await db.commit()

    @staticmethod
    def _run_task_sync(
        task_id: str,
        query: str,
        protein_sequence: str | None,
        include_metrics: bool,
    ) -> dict[str, object]:
        result_holder: dict[str, object] = {}
        error_holder: list[BaseException] = []

        def _runner() -> None:
            try:
                result_holder["value"] = asyncio.run(
                    worker_module._run_and_save_async(
                        task_id=task_id,
                        query=query,
                        protein_sequence=protein_sequence,
                        include_metrics=include_metrics,
                    )
                )
            except BaseException as exc:  # pragma: no cover - test plumbing
                error_holder.append(exc)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()

        if error_holder:
            return {"status": "failed", "error": str(error_holder[0])}
        return result_holder["value"]

    def test_health_reports_database_queue_model_and_rag_status(self) -> None:
        with TestClient(main_module.app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "protein-agent")
        self.assertEqual(payload["database"], "ok")
        self.assertTrue(payload["queue"]["configured"])
        self.assertEqual(payload["models"]["configured_task_model_count"], 3)
        self.assertEqual(payload["models"]["total_task_model_count"], 3)
        self.assertEqual(payload["models"]["router"]["task_type"], "task_routing")
        self.assertIn("backend", payload["rag"])

    def test_run_returns_pending_task_id_when_job_is_enqueued(self) -> None:
        with patch.object(main_module.run_agent_task, "delay", return_value=None):
            with TestClient(main_module.app) as client:
                response = client.post(
                    "/run",
                    json={
                        "query": f"请根据蛋白质序列 {self.sequence} 设计一个配对多肽",
                        "include_metrics": True,
                    },
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["status"], JobStatus.PENDING)

                task_response = client.get(f"/tasks/{payload['task_id']}")
                self.assertEqual(task_response.status_code, 200)
                task_payload = task_response.json()
                self.assertEqual(task_payload["status"], JobStatus.PENDING)
                self.assertEqual(task_payload["trace_events"][0]["step"], "queued")

    def test_run_can_complete_successfully_and_show_up_in_history(self) -> None:
        with patch.object(main_module.run_agent_task, "delay", side_effect=self._run_task_sync):
            with TestClient(main_module.app) as client:
                response = client.post(
                    "/run",
                    json={
                        "query": "请设计一个 RNA 适配体",
                        "protein_sequence": self.sequence,
                        "include_metrics": True,
                    },
                )
                self.assertEqual(response.status_code, 200)
                task_id = response.json()["task_id"]

                task_response = client.get(f"/tasks/{task_id}")
                self.assertEqual(task_response.status_code, 200)
                task_payload = task_response.json()
                self.assertEqual(task_payload["status"], JobStatus.SUCCESS)
                self.assertEqual(task_payload["task_type"], "aptamer_generation")
                self.assertEqual(task_payload["route_source"], "keyword")
                self.assertTrue(task_payload["trace_events"])
                self.assertEqual(task_payload["trace_events"][-1]["step"], "complete")

                history_response = client.get("/history")
                self.assertEqual(history_response.status_code, 200)
                history_payload = history_response.json()
                self.assertEqual(history_payload[0]["task_id"], task_id)
                self.assertEqual(history_payload[0]["status"], JobStatus.SUCCESS)

    def test_run_marks_record_failed_when_enqueue_fails(self) -> None:
        with patch.object(main_module.run_agent_task, "delay", side_effect=RuntimeError("broker unavailable")):
            with TestClient(main_module.app) as client:
                response = client.post(
                    "/run",
                    json={
                        "query": f"请根据蛋白质序列 {self.sequence} 设计一个配对多肽",
                        "include_metrics": True,
                    },
                )

                self.assertEqual(response.status_code, 503)
                payload = response.json()["detail"]
                self.assertEqual(payload["status"], JobStatus.FAILED)
                task_id = payload["task_id"]

                task_response = client.get(f"/tasks/{task_id}")
                self.assertEqual(task_response.status_code, 200)
                task_payload = task_response.json()
                self.assertEqual(task_payload["status"], JobStatus.FAILED)
                self.assertIn("任务入队失败", task_payload["error_message"])
                self.assertEqual(task_payload["trace_events"][-1]["step"], "enqueue-failed")

    def test_run_surfaces_missing_sequence_as_failed_task(self) -> None:
        with patch.object(main_module.run_agent_task, "delay", side_effect=self._run_task_sync):
            with TestClient(main_module.app) as client:
                response = client.post(
                    "/run",
                    json={
                        "query": "请帮我生成一个多肽候选",
                        "include_metrics": True,
                    },
                )
                self.assertEqual(response.status_code, 200)
                task_id = response.json()["task_id"]

                task_response = client.get(f"/tasks/{task_id}")
                self.assertEqual(task_response.status_code, 200)
                task_payload = task_response.json()
                self.assertEqual(task_payload["status"], JobStatus.FAILED)
                self.assertIn("没有解析到蛋白质序列", task_payload["error_message"])
                self.assertEqual(task_payload["trace_events"][-1]["step"], "failed")

    def test_tasks_endpoint_can_return_running_status(self) -> None:
        task_id = "11111111-1111-1111-1111-111111111111"
        asyncio.run(self._create_record(task_id=task_id, status=JobStatus.RUNNING))

        with TestClient(main_module.app) as client:
            response = client.get(f"/tasks/{task_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], JobStatus.RUNNING)
        self.assertEqual(payload["trace_events"][0]["step"], "seeded")


if __name__ == "__main__":
    unittest.main()
