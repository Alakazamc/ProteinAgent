from __future__ import annotations

import unittest
from unittest.mock import patch

from app.config import RouterLLMConfig
from app.router import RouteError, RouterLLMError, route_query, route_query_with_optional_llm
from app.schemas import RouteDecision
from app.schemas import TaskType


class RouterTests(unittest.TestCase):
    def test_route_peptide_generation(self) -> None:
        decision = route_query("给这个蛋白质序列 MKTAYIAKQRQISFVKSHFS 设计一个配对多肽")
        self.assertEqual(decision.task_type, TaskType.PEPTIDE_GENERATION)
        self.assertIn("多肽", decision.matched_keywords)

    def test_route_peptide_generation_with_generic_peptide_wording(self) -> None:
        decision = route_query("我想要一个肽类候选，蛋白质序列是 MKTAYIAKQRQISFVKSHFS")
        self.assertEqual(decision.task_type, TaskType.PEPTIDE_GENERATION)
        self.assertIn("肽类", decision.matched_keywords)

    def test_route_aptamer_generation(self) -> None:
        decision = route_query("请根据蛋白质序列 MKTAYIAKQRQISFVKSHFS 设计核酸适配体")
        self.assertEqual(decision.task_type, TaskType.APTAMER_GENERATION)
        self.assertIn("适配体", decision.matched_keywords)

    def test_route_protein_prediction(self) -> None:
        decision = route_query("请帮我预测这个蛋白质序列的结合潜力")
        self.assertEqual(decision.task_type, TaskType.PROTEIN_PREDICTION)
        self.assertIn("预测", decision.matched_keywords)

    def test_route_rejects_ambiguous_target(self) -> None:
        with self.assertRaises(RouteError):
            route_query("给这个蛋白设计多肽适配体")

    @patch("app.router._route_with_openai_compatible")
    def test_route_uses_router_llm_when_available(self, mock_route) -> None:
        mock_route.return_value = RouteDecision(
            task_type=TaskType.APTAMER_GENERATION,
            matched_keywords=(),
            reason="由 Router LLM 判定：用户明确要求设计 RNA 适配体。",
        )
        config = RouterLLMConfig(
            provider="openai-compatible",
            model_name="doubao-router",
            base_url="https://example.com/v1",
            api_key="secret",
            timeout_seconds=30,
        )

        decision = route_query_with_optional_llm("我想要一个 RNA 候选", config)

        self.assertEqual(decision.task_type, TaskType.APTAMER_GENERATION)
        self.assertIn("Router LLM", decision.reason)
        mock_route.assert_called_once()

    @patch("app.router._route_with_openai_compatible")
    def test_route_falls_back_to_keywords_when_router_llm_fails(self, mock_route) -> None:
        mock_route.side_effect = RouterLLMError("route failed")
        config = RouterLLMConfig(
            provider="openai-compatible",
            model_name="doubao-router",
            base_url="https://example.com/v1",
            api_key="secret",
            timeout_seconds=30,
            fallback_to_keywords=True,
        )

        decision = route_query_with_optional_llm("请生成一个多肽候选", config)

        self.assertEqual(decision.task_type, TaskType.PEPTIDE_GENERATION)
        self.assertIn("多肽", decision.matched_keywords)

    @patch("app.router._route_with_openai_compatible")
    def test_route_raises_when_router_llm_fails_and_fallback_disabled(self, mock_route) -> None:
        mock_route.side_effect = RouterLLMError("route failed")
        config = RouterLLMConfig(
            provider="openai-compatible",
            model_name="doubao-router",
            base_url="https://example.com/v1",
            api_key="secret",
            timeout_seconds=30,
            fallback_to_keywords=False,
        )

        with self.assertRaises(RouterLLMError):
            route_query_with_optional_llm("请生成一个多肽候选", config)


if __name__ == "__main__":
    unittest.main()
