from __future__ import annotations

from .config import AppConfig, ModelConfig
from .knowledge_base import ProteinKnowledgeBase, get_cached_knowledge_base
from .metrics import compute_metrics
from .model_clients import build_model_client
from .router import RouteError, route_query
from .schemas import AgentExecutionResult, ModelExecutionRequest, TaskType
from .sequence_utils import SequenceError, extract_protein_sequence, normalize_protein_sequence


class ProteinAgentError(Exception):
    pass


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
        return route_query(query)

    def run(
        self,
        query: str,
        protein_sequence: str | None = None,
        include_metrics: bool = True,
    ) -> AgentExecutionResult:
        if not query.strip():
            raise ProteinAgentError("query 不能为空。")

        try:
            route_decision = self.route(query)
            resolved_sequence = self._resolve_protein_sequence(protein_sequence, query)
        except (RouteError, SequenceError) as exc:
            raise ProteinAgentError(str(exc)) from exc

        # --- RAG retrieval ---
        rag_chunks: list[dict] = []
        if self._kb and self._kb.ready:
            retrieved = self._kb.search(query, top_k=self._config.rag_top_k)
            rag_chunks = [chunk.to_dict() for chunk in retrieved]

        model_config = self._select_model_config(route_decision.task_type)
        model_client = build_model_client(model_config.provider)
        model_result = model_client.run(
            ModelExecutionRequest(
                task_type=route_decision.task_type,
                query=query,
                protein_sequence=resolved_sequence,
            ),
            model_config=model_config,
        )

        metrics = {}
        if include_metrics:
            metrics = _merge_metrics(
                model_result.metrics,
                compute_metrics(
                    task_type=route_decision.task_type.value,
                    protein_sequence=resolved_sequence,
                    generated_sequence=model_result.generated_sequence,
                ),
            )

        output_text = _compose_output_text(
            task_type=route_decision.task_type,
            model_text=model_result.output_text,
            generated_sequence=model_result.generated_sequence,
            metrics=metrics,
            rag_chunks=rag_chunks,
        )

        return AgentExecutionResult(
            task_type=route_decision.task_type,
            matched_keywords=route_decision.matched_keywords,
            route_reason=route_decision.reason,
            protein_sequence=resolved_sequence,
            selected_model_name=model_config.model_name,
            selected_model_provider=model_config.provider,
            selected_model_base_url=model_config.base_url,
            output_text=output_text,
            generated_sequence=model_result.generated_sequence,
            metrics=metrics,
            rag_context=rag_chunks,
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
