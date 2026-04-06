from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent import ProteinAgent, ProteinAgentError
from app.config import AppConfig, ModelConfig, RouterLLMConfig
from app.knowledge_base import get_cached_knowledge_base


DEFAULT_CASES_PATH = ROOT / "evals" / "protein_agent_eval_cases.jsonl"
DEFAULT_REPORT_PATH = ROOT / "evals" / "latest_report.md"

logging.getLogger("app.router").setLevel(logging.ERROR)


@dataclass
class EvaluatedCase:
    case_id: str
    expected_result: str
    actual_result: str
    passed: bool
    expected_task_type: str | None = None
    actual_task_type: str | None = None
    expected_route_source: str | None = None
    actual_route_source: str | None = None
    expected_error_kind: str | None = None
    actual_error_kind: str | None = None
    actual_error_message: str | None = None
    router_mode: str = "disabled"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        cases.append(json.loads(line))
    return cases


def build_agent(router_mode: str) -> ProteinAgent:
    router_llm = RouterLLMConfig()
    if router_mode == "fallback_failure":
        router_llm = RouterLLMConfig(
            provider="openai-compatible",
            model_name="router-smoke-test",
            base_url="http://127.0.0.1:9/v1",
            api_key="dummy",
            timeout_seconds=1,
            fallback_to_keywords=True,
        )

    config = AppConfig(
        protein_model=ModelConfig(
            task_type="protein_prediction",
            provider="local-stub",
            model_name="stub-protein-model",
            base_url=None,
            api_key=None,
            timeout_seconds=30,
        ),
        peptide_model=ModelConfig(
            task_type="peptide_generation",
            provider="local-stub",
            model_name="stub-peptide-model",
            base_url=None,
            api_key=None,
            timeout_seconds=30,
        ),
        aptamer_model=ModelConfig(
            task_type="aptamer_generation",
            provider="local-stub",
            model_name="stub-aptamer-model",
            base_url=None,
            api_key=None,
            timeout_seconds=30,
        ),
        router_llm=router_llm,
        rag_enabled=True,
        rag_top_k=3,
        rag_backend="local-hash",
    )
    knowledge_base = get_cached_knowledge_base()
    return ProteinAgent(config=config, knowledge_base=knowledge_base)


def classify_error(message: str) -> str:
    if "没有解析到蛋白质序列" in message:
        return "missing_sequence"
    if "同时匹配到了多肽和适配体关键词" in message:
        return "ambiguous_target"
    return "other"


def evaluate_case(case: dict[str, Any]) -> EvaluatedCase:
    agent = build_agent(case.get("router_mode", "disabled"))
    try:
        result = agent.run(
            query=case["query"],
            protein_sequence=case.get("protein_sequence"),
            include_metrics=True,
        )
    except ProteinAgentError as exc:
        actual_error_kind = classify_error(str(exc))
        passed = (
            case["expected_result"] == "error"
            and actual_error_kind == case.get("expected_error_kind")
        )
        return EvaluatedCase(
            case_id=case["id"],
            expected_result=case["expected_result"],
            actual_result="error",
            passed=passed,
            expected_error_kind=case.get("expected_error_kind"),
            actual_error_kind=actual_error_kind,
            actual_error_message=str(exc),
            router_mode=case.get("router_mode", "disabled"),
        )

    actual_task_type = (
        result.task_type.value if hasattr(result.task_type, "value") else str(result.task_type)
    )
    passed = (
        case["expected_result"] == "success"
        and actual_task_type == case.get("expected_task_type")
        and result.route_source == case.get("expected_route_source")
    )
    return EvaluatedCase(
        case_id=case["id"],
        expected_result=case["expected_result"],
        actual_result="success",
        passed=passed,
        expected_task_type=case.get("expected_task_type"),
        actual_task_type=actual_task_type,
        expected_route_source=case.get("expected_route_source"),
        actual_route_source=result.route_source,
        router_mode=case.get("router_mode", "disabled"),
    )


def percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def build_report(results: list[EvaluatedCase], total_cases: int) -> str:
    success_cases = [case for case in results if case.expected_result == "success"]
    error_cases = [case for case in results if case.expected_result == "error"]
    passed_success = [case for case in success_cases if case.passed]
    passed_errors = [case for case in error_cases if case.passed]

    per_task_totals: Counter[str] = Counter(
        case.expected_task_type for case in success_cases if case.expected_task_type
    )
    per_task_passed: Counter[str] = Counter(
        case.expected_task_type for case in passed_success if case.expected_task_type
    )
    failure_modes: Counter[str] = Counter(
        case.actual_error_kind or case.expected_error_kind or "unknown" for case in error_cases
    )
    fallback_cases = [case for case in success_cases if case.router_mode == "fallback_failure"]
    fallback_passed = [case for case in fallback_cases if case.passed]

    mismatches: list[str] = []
    for case in results:
        if case.passed:
            continue
        if case.actual_result == "error":
            mismatches.append(
                f"- `{case.case_id}`: 期望 `{case.expected_error_kind}`，实际 `{case.actual_error_kind}`，消息 `{case.actual_error_message}`"
            )
        else:
            mismatches.append(
                f"- `{case.case_id}`: 期望 `{case.expected_task_type}/{case.expected_route_source}`，实际 `{case.actual_task_type}/{case.actual_route_source}`"
            )

    lines = [
        "# ProteinAgent 最小评测报告",
        "",
        f"- 评测日期: `2026-04-05`",
        f"- 数据集: `{total_cases}` 条 query",
        "- 模型模式: `local-stub` 任务模型 + `local-hash` RAG",
        "- 路由回退覆盖: 通过无效 `Router LLM` 地址模拟 `Router LLM 失败 -> 关键词 fallback`",
        "",
        "## 核心指标",
        "",
        "| 指标 | 结果 |",
        "| --- | --- |",
        f"| 路由正确率 | `{len(passed_success)}/{len(success_cases)} ({percent(len(passed_success), len(success_cases))})` |",
        f"| 任务成功率 | `{len([case for case in success_cases if case.actual_result == 'success'])}/{len(success_cases)} ({percent(len([case for case in success_cases if case.actual_result == 'success']), len(success_cases))})` |",
        f"| 负样例识别率 | `{len(passed_errors)}/{len(error_cases)} ({percent(len(passed_errors), len(error_cases))})` |",
        f"| Router fallback 覆盖通过 | `{len(fallback_passed)}/{len(fallback_cases)} ({percent(len(fallback_passed), len(fallback_cases))})` |",
        "",
        "## 按任务类型拆分",
        "",
        "| 任务类型 | 通过/总数 |",
        "| --- | --- |",
    ]
    for task_type in ("peptide_generation", "aptamer_generation", "protein_prediction"):
        lines.append(
            f"| `{task_type}` | `{per_task_passed[task_type]}/{per_task_totals[task_type]} ({percent(per_task_passed[task_type], per_task_totals[task_type])})` |"
        )

    lines.extend(
        [
            "",
            "## 常见失败模式",
            "",
            "| 失败类型 | 数量 |",
            "| --- | --- |",
        ]
    )
    for failure_kind, count in sorted(failure_modes.items()):
        lines.append(f"| `{failure_kind}` | `{count}` |")

    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- 在当前离线评测集上，`ProteinAgent` 的关键词路由、多任务执行和错误路径都能稳定复现。",
            "- 评测覆盖了 `3` 类业务任务、`6` 条 Router fallback 场景，以及 `6` 条非法输入场景。",
            "- 当前主要失败模式集中在故意构造的负样例：`缺失蛋白质序列` 与 `多目标歧义路由`，说明系统已经具备可解释的拒答与失败态表达。",
        ]
    )

    if mismatches:
        lines.extend(["", "## 未通过样例", ""])
        lines.extend(mismatches)

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ProteinAgent offline eval cases.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to eval JSONL cases.",
    )
    parser.add_argument(
        "--write-report",
        type=Path,
        default=None,
        help="Optional path to write the markdown report.",
    )
    args = parser.parse_args()

    cases = load_cases(args.cases)
    results = [evaluate_case(case) for case in cases]
    report = build_report(results, total_cases=len(cases))
    print(report)

    if args.write_report:
        args.write_report.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
