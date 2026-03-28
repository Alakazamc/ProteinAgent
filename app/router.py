from __future__ import annotations

from .schemas import RouteDecision, TaskType


PEPTIDE_KEYWORDS = ("多肽", "peptide")
APTAMER_KEYWORDS = ("适配体", "核酸", "核算", "aptamer", "dna", "rna")
PROTEIN_KEYWORDS = ("蛋白质", "蛋白", "protein", "预测", "打分", "分类")


class RouteError(ValueError):
    pass


def route_query(query: str) -> RouteDecision:
    lowered = query.lower()
    peptide_hits = tuple(keyword for keyword in PEPTIDE_KEYWORDS if keyword in lowered)
    aptamer_hits = tuple(keyword for keyword in APTAMER_KEYWORDS if keyword in lowered)
    protein_hits = tuple(keyword for keyword in PROTEIN_KEYWORDS if keyword in lowered)

    if peptide_hits and aptamer_hits:
        raise RouteError("同时匹配到了多肽和适配体关键词，请只保留一种目标类型。")

    if aptamer_hits:
        return RouteDecision(
            task_type=TaskType.APTAMER_GENERATION,
            matched_keywords=aptamer_hits,
            reason="命中适配体/核酸关键词，路由到核酸适配体生成模型。",
        )

    if peptide_hits:
        return RouteDecision(
            task_type=TaskType.PEPTIDE_GENERATION,
            matched_keywords=peptide_hits,
            reason="命中多肽关键词，路由到多肽生成模型。",
        )

    if protein_hits:
        return RouteDecision(
            task_type=TaskType.PROTEIN_PREDICTION,
            matched_keywords=protein_hits,
            reason="命中蛋白质/预测关键词，路由到蛋白质预测模型。",
        )

    raise RouteError("没有匹配到任务关键词，请在 query 中包含 多肽、适配体、核酸 或 蛋白质。")

