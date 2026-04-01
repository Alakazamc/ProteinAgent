from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.metrics import compute_metrics  # noqa: E402
from app.models import AgentExecutionRecord, JobStatus  # noqa: E402

TARGET_SEQUENCES = {
    "kinase": "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP",
    "enzyme": "MSDVEKGKKIFIMKCSQCHTVEKGGKHKTGPNLHGLFGRK",
    "receptor": "MNNRWLFSTNHKDIGTLYLLFGAWAGVLGTALSLLIRAEL",
}

SEEDED_RECORD_DEFS: list[dict[str, Any]] = [
    {
        "task_id": "7c21fd95-1d1a-4d90-a6ba-0f15b18f4101",
        "status": JobStatus.SUCCESS,
        "query": "请根据蛋白质序列生成一个配对多肽",
        "task_type": "peptide_generation",
        "provider": "local-stub",
        "model_name": "paired-peptide-generator",
        "protein_key": "kinase",
        "generated_sequence": "KQRQISFVKSHF",
        "summary": "已生成一个候选多肽序列，可作为后续筛选与联调的初始结果。",
        "topic": "peptide",
        "age_minutes": 11,
        "duration_seconds": 12,
    },
    {
        "task_id": "5607d6b9-bf06-4d80-bf50-cbe9d204efa1",
        "status": JobStatus.SUCCESS,
        "query": "请为这个蛋白质设计 RNA 核酸适配体",
        "task_type": "aptamer_generation",
        "provider": "local-stub",
        "model_name": "nucleic-aptamer-generator",
        "protein_key": "kinase",
        "generated_sequence": "AGCACGAUCGAAGCACAGCCAUCGGAUC",
        "summary": "已生成一个候选适配体序列，并给出可用于初筛的理化指标。",
        "topic": "aptamer",
        "age_minutes": 10,
        "duration_seconds": 15,
    },
    {
        "task_id": "45f296a0-a9c9-47b7-94d7-99373a435f52",
        "status": JobStatus.SUCCESS,
        "query": "请帮我预测这个蛋白质的结合潜力",
        "task_type": "protein_prediction",
        "provider": "local-stub",
        "model_name": "saprot-protein-predictor",
        "protein_key": "kinase",
        "generated_sequence": None,
        "summary": "该蛋白在当前启发式规则下表现为较高结合潜力，建议进入进一步筛选。",
        "topic": "protein",
        "age_minutes": 9,
        "duration_seconds": 18,
    },
    {
        "task_id": "18e7d541-4dfd-475a-a6d5-8dfac1e6f55d",
        "status": JobStatus.SUCCESS,
        "query": "请为该酶靶点推荐一个短肽候选",
        "task_type": "peptide_generation",
        "provider": "generic-json",
        "model_name": "peptide-json-service-v1",
        "protein_key": "enzyme",
        "generated_sequence": "CSQCHTVEKGGK",
        "summary": "已返回一个偏向正电荷与局部结构保守片段的短肽候选。",
        "topic": "peptide",
        "age_minutes": 8,
        "duration_seconds": 17,
    },
    {
        "task_id": "0ff3ec50-7c61-4d4c-9ef3-5b9a2ef8dd09",
        "status": JobStatus.SUCCESS,
        "query": "请设计一个 DNA 适配体用于初筛",
        "task_type": "aptamer_generation",
        "provider": "generic-json",
        "model_name": "aptamer-screening-json-v1",
        "protein_key": "enzyme",
        "generated_sequence": "GCGTACGATCGGACTTAGCGGATCCTGA",
        "summary": "已返回一个可用于初筛的 DNA 适配体候选，并附带基础序列指标。",
        "topic": "aptamer",
        "age_minutes": 7,
        "duration_seconds": 16,
    },
    {
        "task_id": "1ecf1e55-e01b-4135-a473-45273f8feef3",
        "status": JobStatus.SUCCESS,
        "query": "请预测该受体蛋白是否具有较高结合可能",
        "task_type": "protein_prediction",
        "provider": "local-stub",
        "model_name": "saprot-protein-predictor",
        "protein_key": "receptor",
        "generated_sequence": None,
        "summary": "当前结果显示该受体蛋白具有中高水平的结合潜力，建议进入下一轮筛选。",
        "topic": "protein",
        "age_minutes": 6,
        "duration_seconds": 21,
    },
    {
        "task_id": "c7f70415-c46a-4c6c-90e7-9b37b5edfe44",
        "status": JobStatus.SUCCESS,
        "query": "请基于该受体序列生成一个短多肽配体",
        "task_type": "peptide_generation",
        "provider": "openai-compatible",
        "model_name": "peptide-candidate-chat-v1",
        "protein_key": "receptor",
        "generated_sequence": "GTLYLLFGAWAG",
        "summary": "已返回一个受体结合导向的候选多肽序列，可用于后续人工复核。",
        "topic": "peptide",
        "age_minutes": 5,
        "duration_seconds": 19,
    },
    {
        "task_id": "f6d378bc-c40d-4cd9-9ef7-14dfe2d0672f",
        "status": JobStatus.SUCCESS,
        "query": "请为这个靶蛋白设计一个 RNA 适配体候选",
        "task_type": "aptamer_generation",
        "provider": "openai-compatible",
        "model_name": "aptamer-rna-designer-v1",
        "protein_key": "receptor",
        "generated_sequence": "AUGGCUACGGAUCCAGUACGCUAGGAUC",
        "summary": "已返回一个 RNA 适配体候选，可结合 GC 含量与长度指标进行初筛。",
        "topic": "aptamer",
        "age_minutes": 4,
        "duration_seconds": 20,
    },
    {
        "task_id": "2ae19739-c453-47c7-ae87-8fa4f4309212",
        "status": JobStatus.FAILED,
        "query": "请调用远端模型生成多肽",
        "task_type": "peptide_generation",
        "provider": "openai-compatible",
        "model_name": "remote-peptide-v1",
        "protein_key": "kinase",
        "generated_sequence": None,
        "error_message": "remote-peptide-v1 请求失败，状态码 502: upstream timeout",
        "age_minutes": 3,
        "duration_seconds": 9,
    },
    {
        "task_id": "d17e9b3c-2eb6-44b0-ab1e-261e1c5ea091",
        "status": JobStatus.SUCCESS,
        "query": "请为该蛋白重新生成一条更短的候选多肽",
        "task_type": "peptide_generation",
        "provider": "generic-json",
        "model_name": "peptide-json-service-v2",
        "protein_key": "kinase",
        "generated_sequence": "RQDILDLWIYHT",
        "summary": "已返回一条更短的候选多肽序列，便于后续做长度敏感场景筛选。",
        "topic": "peptide",
        "age_minutes": 2,
        "duration_seconds": 13,
    },
    {
        "task_id": "1bc69f31-1ec5-41d8-aa08-9486020fdf72",
        "status": JobStatus.FAILED,
        "query": "请生成一个高稳定性的 DNA 适配体",
        "task_type": "aptamer_generation",
        "provider": "generic-json",
        "model_name": "aptamer-screening-json-v2",
        "protein_key": "enzyme",
        "generated_sequence": None,
        "error_message": "aptamer-screening-json-v2 返回了非 JSON 响应。",
        "age_minutes": 1,
        "duration_seconds": 11,
    },
]


def _rag_context(topic: str) -> list[dict[str, object]]:
    if topic == "peptide":
        return [
            {
                "text": "多肽候选常结合疏水性、带电性和共享 motif 作为快速筛选信号。",
                "source": "protein-agent-notes",
                "score": 0.9124,
            },
            {
                "text": "配对多肽的工程联调阶段通常先看长度、理化特征和局部序列相似性。",
                "source": "protein-agent-notes",
                "score": 0.8611,
            },
        ]
    if topic == "aptamer":
        return [
            {
                "text": "适配体筛选常以 SELEX 为核心，并关注 GC 含量和连续同聚物风险。",
                "source": "protein-agent-notes",
                "score": 0.9038,
            },
            {
                "text": "DNA/RNA 适配体的结果通常会搭配长度和多样性指标一起展示。",
                "source": "protein-agent-notes",
                "score": 0.8426,
            },
        ]
    return [
        {
            "text": "蛋白预测类任务通常先给出结合潜力摘要和启发式打分。",
            "source": "protein-agent-notes",
            "score": 0.8872,
        },
        {
            "text": "结构化预测输出适合进一步用于 rerank、筛选和人工复核。",
            "source": "protein-agent-notes",
            "score": 0.7995,
        },
    ]


def _route_reason(task_type: str) -> str:
    if task_type == "peptide_generation":
        return "命中多肽关键词，路由到多肽生成模型。"
    if task_type == "aptamer_generation":
        return "命中适配体/核酸关键词，路由到核酸适配体生成模型。"
    return "命中蛋白质/预测关键词，路由到蛋白质预测模型。"


def _output_text(summary: str, generated_sequence: str | None, metrics: dict[str, object]) -> str:
    lines = [summary]
    if generated_sequence:
        lines.append(f"候选序列: {generated_sequence}")
    if metrics:
        metric_summary = ", ".join(f"{key}={value}" for key, value in metrics.items())
        lines.append(f"评价指标: {metric_summary}")
    return "\n".join(lines)


def _build_record(defn: dict[str, Any], now: datetime) -> AgentExecutionRecord:
    protein_sequence = TARGET_SEQUENCES[defn["protein_key"]]
    created_at = now - timedelta(minutes=defn["age_minutes"])
    completed_at = created_at + timedelta(seconds=defn["duration_seconds"])

    generated_sequence = defn.get("generated_sequence")
    is_success = defn["status"] == JobStatus.SUCCESS
    metrics = (
        compute_metrics(
            task_type=defn["task_type"],
            protein_sequence=protein_sequence,
            generated_sequence=generated_sequence,
        )
        if is_success
        else None
    )
    output_text = (
        _output_text(defn["summary"], generated_sequence, metrics or {})
        if is_success
        else None
    )
    rag_context = _rag_context(defn["topic"]) if is_success else None

    return AgentExecutionRecord(
        task_id=defn["task_id"],
        status=defn["status"],
        request_query=defn["query"],
        input_sequence=protein_sequence,
        task_type=defn["task_type"],
        model_provider=defn["provider"],
        model_name=defn["model_name"],
        generated_sequence=generated_sequence,
        route_reason=_route_reason(defn["task_type"]),
        output_text=output_text,
        metrics=metrics,
        rag_context=rag_context,
        error_message=defn.get("error_message"),
        created_at=created_at,
        completed_at=completed_at,
    )


async def seed_history_records() -> None:
    now = datetime.now(timezone.utc)
    seeded_records = [_build_record(defn, now) for defn in SEEDED_RECORD_DEFS]

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await session.execute(
            sa.delete(AgentExecutionRecord).where(
                AgentExecutionRecord.task_id.in_(
                    tuple(defn["task_id"] for defn in SEEDED_RECORD_DEFS)
                )
            )
        )
        session.add_all(seeded_records)
        await session.commit()

    print(f"Loaded {len(seeded_records)} history records into the configured database.")


if __name__ == "__main__":
    asyncio.run(seed_history_records())
