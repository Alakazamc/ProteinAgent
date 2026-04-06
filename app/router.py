from __future__ import annotations

import json
import logging
import re
from urllib import error, request

from .config import RouterLLMConfig
from .schemas import RouteDecision, TaskType


logger = logging.getLogger(__name__)

PEPTIDE_KEYWORDS = ("多肽", "肽类", "肽", "peptide")
APTAMER_KEYWORDS = ("适配体", "核酸", "核算", "aptamer", "dna", "rna")
PROTEIN_KEYWORDS = ("蛋白质", "蛋白", "protein", "预测", "打分", "分类")

TASK_TYPE_MAP = {
    TaskType.PEPTIDE_GENERATION.value: TaskType.PEPTIDE_GENERATION,
    TaskType.APTAMER_GENERATION.value: TaskType.APTAMER_GENERATION,
    TaskType.PROTEIN_PREDICTION.value: TaskType.PROTEIN_PREDICTION,
}


class RouteError(ValueError):
    pass


class RouterLLMError(RouteError):
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
            route_source="keyword",
        )

    if peptide_hits:
        return RouteDecision(
            task_type=TaskType.PEPTIDE_GENERATION,
            matched_keywords=peptide_hits,
            reason="命中多肽关键词，路由到多肽生成模型。",
            route_source="keyword",
        )

    if protein_hits:
        return RouteDecision(
            task_type=TaskType.PROTEIN_PREDICTION,
            matched_keywords=protein_hits,
            reason="命中蛋白质/预测关键词，路由到蛋白质预测模型。",
            route_source="keyword",
        )

    raise RouteError("没有匹配到任务关键词，请在 query 中包含 多肽、适配体、核酸 或 蛋白质。")


def route_query_with_optional_llm(
    query: str,
    router_llm: RouterLLMConfig | None = None,
) -> RouteDecision:
    if router_llm and router_llm.is_configured:
        try:
            return route_query_with_llm(query, router_llm)
        except RouterLLMError as exc:
            logger.warning("Router LLM failed, fallback to keyword routing: %s", exc)
            if not router_llm.fallback_to_keywords:
                raise
    return route_query(query)


def route_query_with_llm(query: str, router_llm: RouterLLMConfig) -> RouteDecision:
    provider = (router_llm.provider or "").lower()
    if provider != "openai-compatible":
        raise RouterLLMError(f"当前 Router LLM 暂只支持 openai-compatible，收到: {provider or 'empty'}")
    return _route_with_openai_compatible(query, router_llm)


def _route_with_openai_compatible(query: str, router_llm: RouterLLMConfig) -> RouteDecision:
    if not router_llm.base_url or not router_llm.model_name:
        raise RouterLLMError("Router LLM 缺少 base_url 或 model_name 配置。")

    endpoint = router_llm.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"

    system_prompt = (
        "你是 Protein Agent 的任务路由器，只负责把用户请求分类为一个任务类型。"
        "候选任务只有三类："
        "1. peptide_generation：用户要生成或设计多肽；"
        "2. aptamer_generation：用户要生成或设计 DNA/RNA/核酸适配体；"
        "3. protein_prediction：用户要做蛋白质分析、预测、评分、分类或结合潜力判断。"
        "请仅返回 JSON 对象，不要输出解释性前后缀。"
        "JSON schema: "
        '{"task_type":"peptide_generation|aptamer_generation|protein_prediction|unknown",'
        '"matched_keywords":["string"],'
        '"reason":"中文简短说明，解释你为何这样判断"}。'
        "如果无法判断或请求超出这三类，请返回 task_type=unknown。"
    )

    payload = json.dumps(
        {
            "model": router_llm.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "temperature": 0,
        }
    ).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if router_llm.api_key:
        headers["Authorization"] = f"Bearer {router_llm.api_key}"

    http_request = request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with request.urlopen(http_request, timeout=router_llm.timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RouterLLMError(
            f"Router LLM 请求失败，状态码 {exc.code}: {detail or exc.reason}"
        ) from exc
    except error.URLError as exc:
        raise RouterLLMError(f"Router LLM 网络请求失败: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RouterLLMError("Router LLM 返回了非 JSON 响应。") from exc

    choices = response_payload.get("choices", [])
    if not choices:
        raise RouterLLMError("Router LLM 响应中没有 choices。")

    content = choices[0].get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RouterLLMError("Router LLM 返回内容为空。")

    parsed = _parse_router_llm_content(content)
    task_type_value = parsed.get("task_type")
    if task_type_value == "unknown":
        raise RouterLLMError("Router LLM 无法确定任务类型。")
    if task_type_value not in TASK_TYPE_MAP:
        raise RouterLLMError(f"Router LLM 返回了不支持的任务类型: {task_type_value!r}")

    reason = str(parsed.get("reason") or "").strip() or "Router LLM 已完成任务分类。"
    matched_keywords = tuple(_normalize_matched_keywords(parsed.get("matched_keywords")))
    return RouteDecision(
        task_type=TASK_TYPE_MAP[task_type_value],
        matched_keywords=matched_keywords,
        reason=f"由 Router LLM 判定：{reason}",
        route_source="router_llm",
        router_output_text=_format_router_output(content, parsed),
    )


def _parse_router_llm_content(content: str) -> dict[str, object]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise RouterLLMError("Router LLM 返回的 JSON 无法解析。") from exc

    raise RouterLLMError("Router LLM 未返回可解析的 JSON 对象。")


def _normalize_matched_keywords(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _format_router_output(content: str, parsed: dict[str, object]) -> str:
    stripped = content.strip()
    if stripped.startswith("{"):
        return stripped
    return json.dumps(parsed, ensure_ascii=False, indent=2)
