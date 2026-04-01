from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig, ModelConfig
from .knowledge_base import ProteinKnowledgeBase, get_cached_knowledge_base
from .metrics import compute_metrics
from .model_clients import build_model_client
from .router import RouteError, route_query_with_optional_llm
from .schemas import (
    AgentExecutionResult,
    ModelExecutionRequest,
    ModelExecutionResult,
    RouteDecision,
    TaskType,
    TraceEvent,
)
from .sequence_utils import SequenceError, extract_protein_sequence, normalize_protein_sequence


class ProteinAgentError(Exception):
    pass


@dataclass(frozen=True)
class PreparedAgentRun:
    route_decision: RouteDecision
    protein_sequence: str
    model_config: ModelConfig
    rag_context: list[dict]


class ProteinAgent:
    def __init__(
        self,
        config: AppConfig,
        knowledge_base: ProteinKnowledgeBase | None = None,
    ) -> None:
        self._config = config
        if knowledge_base is not None:
            self._kb = knowledge_base
        elif config.rag_enabled:
            self._kb = get_cached_knowledge_base(
                data_path=config.rag_data_path or None,
                backend=config.rag_backend,
                embedding_model=config.rag_embedding_model,
            )
        else:
            self._kb = None

    def route(self, query: str):
        return route_query_with_optional_llm(query, self._config.router_llm)

    def run(
        self,
        query: str,
        protein_sequence: str | None = None,
        include_metrics: bool = True,
    ) -> AgentExecutionResult:
        prepared = self.prepare_execution(query=query, protein_sequence=protein_sequence)
        model_result = self.run_model(query=query, prepared=prepared)
        return self.finalize_execution(
            prepared=prepared,
            model_result=model_result,
            include_metrics=include_metrics,
        )

    def prepare_execution(
        self,
        query: str,
        protein_sequence: str | None = None,
    ) -> PreparedAgentRun:
        if not query.strip():
            raise ProteinAgentError("query 不能为空。")

        try:
            route_decision = self.route(query)
            resolved_sequence = self._resolve_protein_sequence(protein_sequence, query)
        except (RouteError, SequenceError) as exc:
            raise ProteinAgentError(str(exc)) from exc

        rag_chunks: list[dict] = []
        if self._kb and self._kb.ready:
            retrieved = self._kb.search(query, top_k=self._config.rag_top_k)
            rag_chunks = [chunk.to_dict() for chunk in retrieved]

        model_config = self._select_model_config(route_decision.task_type)
        return PreparedAgentRun(
            route_decision=route_decision,
            protein_sequence=resolved_sequence,
            model_config=model_config,
            rag_context=rag_chunks,
        )

    def run_model(
        self,
        query: str,
        prepared: PreparedAgentRun,
    ) -> ModelExecutionResult:
        model_client = build_model_client(prepared.model_config.provider)
        return model_client.run(
            ModelExecutionRequest(
                task_type=prepared.route_decision.task_type,
                query=query,
                protein_sequence=prepared.protein_sequence,
            ),
            model_config=prepared.model_config,
        )

    def finalize_execution(
        self,
        prepared: PreparedAgentRun,
        model_result: ModelExecutionResult,
        include_metrics: bool = True,
    ) -> AgentExecutionResult:
        metrics = {}
        if include_metrics:
            metrics = _merge_metrics(
                model_result.metrics,
                compute_metrics(
                    task_type=prepared.route_decision.task_type.value,
                    protein_sequence=prepared.protein_sequence,
                    generated_sequence=model_result.generated_sequence,
                ),
            )

        output_text = _compose_output_text(
            task_type=prepared.route_decision.task_type,
            model_text=model_result.output_text,
            generated_sequence=model_result.generated_sequence,
            metrics=metrics,
            rag_chunks=prepared.rag_context,
        )

        return AgentExecutionResult(
            task_type=prepared.route_decision.task_type,
            matched_keywords=prepared.route_decision.matched_keywords,
            route_reason=prepared.route_decision.reason,
            route_source=prepared.route_decision.route_source,
            router_output_text=prepared.route_decision.router_output_text,
            protein_sequence=prepared.protein_sequence,
            selected_model_name=prepared.model_config.model_name,
            selected_model_provider=prepared.model_config.provider,
            selected_model_base_url=prepared.model_config.base_url,
            output_text=output_text,
            generated_sequence=model_result.generated_sequence,
            metrics=metrics,
            rag_context=prepared.rag_context,
            trace_events=_build_trace_events(
                prepared=prepared,
                generated_sequence=model_result.generated_sequence,
                metrics=metrics,
            ),
        )

    @property
    def knowledge_base(self) -> ProteinKnowledgeBase | None:
        return self._kb

    def list_models(self) -> list[dict[str, object]]:
        model_configs = (
            self._config.protein_model,
            self._config.peptide_model,
            self._config.aptamer_model,
        )
        return [
            {
                "task_type": model_config.task_type,
                "provider": model_config.provider,
                "model_name": model_config.model_name,
                "base_url": model_config.base_url,
                "configured": model_config.is_configured,
            }
            for model_config in model_configs
        ] + [
            {
                "task_type": "task_routing",
                "provider": self._config.router_llm.provider or "disabled",
                "model_name": self._config.router_llm.model_name or "--",
                "base_url": self._config.router_llm.base_url,
                "configured": self._config.router_llm.is_configured,
            }
        ]

    def _resolve_protein_sequence(self, protein_sequence: str | None, query: str) -> str:
        sequence = protein_sequence or extract_protein_sequence(query)
        if not sequence:
            raise SequenceError("没有解析到蛋白质序列，请在 query 中附上序列或单独传 protein_sequence。")
        return normalize_protein_sequence(
            sequence,
            min_length=self._config.min_protein_sequence_length,
        )

    def _select_model_config(self, task_type: TaskType) -> ModelConfig:
        if task_type == TaskType.PEPTIDE_GENERATION:
            return self._config.peptide_model
        if task_type == TaskType.APTAMER_GENERATION:
            return self._config.aptamer_model
        return self._config.protein_model


def _merge_metrics(
    remote_metrics: dict[str, object],
    local_metrics: dict[str, object],
) -> dict[str, object]:
    merged = dict(remote_metrics)
    for key, value in local_metrics.items():
        merged.setdefault(key, value)
    return merged


def _compose_output_text(
    task_type: TaskType,
    model_text: str,
    generated_sequence: str | None,
    metrics: dict[str, object],
    rag_chunks: list[dict] | None = None,
) -> str:
    lines = [model_text.strip()]

    if generated_sequence:
        label = "候选多肽序列" if task_type == TaskType.PEPTIDE_GENERATION else "候选适配体序列"
        lines.append(f"{label}: {generated_sequence}")

    if metrics:
        metric_summary = ", ".join(f"{key}={value}" for key, value in metrics.items())
        lines.append(f"评价指标: {metric_summary}")

    if rag_chunks:
        lines.append("")
        lines.append("参考知识:")
        for i, chunk in enumerate(rag_chunks, 1):
            lines.append(f"  [{i}] {chunk['text']}  (来源: {chunk['source']})")

    return "\n".join(line for line in lines if line is not None)


def _build_trace_events(
    prepared: PreparedAgentRun,
    generated_sequence: str | None,
    metrics: dict[str, object],
) -> list[dict[str, str]]:
    trace_events = [
        TraceEvent(
            step="route",
            title="识别任务类型",
            detail=prepared.route_decision.reason,
        ).to_dict(),
        TraceEvent(
            step="sequence",
            title="提取蛋白质序列",
            detail=f"已规范化输入序列，长度 {len(prepared.protein_sequence)}。",
        ).to_dict(),
        TraceEvent(
            step="rag",
            title="检索领域知识",
            detail=f"返回 {len(prepared.rag_context)} 条相关上下文。",
        ).to_dict(),
        TraceEvent(
            step="model",
            title="选择执行模型",
            detail=(
                f"{prepared.model_config.model_name} "
                f"({prepared.model_config.provider})"
            ),
        ).to_dict(),
    ]

    if prepared.route_decision.router_output_text:
        trace_events.append(
            TraceEvent(
                step="router-llm-output",
                title="路由模型输出",
                detail=prepared.route_decision.router_output_text,
            ).to_dict()
        )

    if generated_sequence:
        trace_events.append(
            TraceEvent(
                step="generation",
                title="生成候选结果",
                detail=f"生成候选序列，长度 {len(generated_sequence)}。",
            ).to_dict()
        )
    else:
        trace_events.append(
            TraceEvent(
                step="prediction",
                title="完成预测摘要",
                detail="模型返回文本分析结果，未生成新序列。",
            ).to_dict()
        )

    trace_events.append(
        TraceEvent(
            step="metrics",
            title="整理评价指标",
            detail=f"输出 {len(metrics)} 项结构化指标。",
        ).to_dict()
    )
    trace_events.append(
        TraceEvent(
            step="complete",
            title="生成最终答复",
            detail="结果已可供前端展示和详情页查看。",
        ).to_dict()
    )
    return trace_events
