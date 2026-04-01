from __future__ import annotations

import unittest

from app.agent import ProteinAgent, ProteinAgentError
from app.config import AppConfig, ModelConfig
from app.schemas import TaskType


def make_config() -> AppConfig:
    return AppConfig(
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
        min_protein_sequence_length=8,
        rag_enabled=False,
    )


class ProteinAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ProteinAgent(make_config())
        self.sequence = "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP"

    def test_run_peptide_generation(self) -> None:
        result = self.agent.run(
            query=f"请根据蛋白质序列 {self.sequence} 生成一个配对多肽",
        )
        self.assertEqual(result.task_type, TaskType.PEPTIDE_GENERATION)
        self.assertTrue(result.generated_sequence)
        self.assertIn("binding_proxy_score", result.metrics)
        self.assertEqual(result.trace_events[0]["step"], "route")
        self.assertEqual(result.trace_events[-1]["step"], "complete")

    def test_run_aptamer_generation_with_explicit_sequence(self) -> None:
        result = self.agent.run(
            query="请设计一个核酸适配体",
            protein_sequence=self.sequence,
        )
        self.assertEqual(result.task_type, TaskType.APTAMER_GENERATION)
        self.assertTrue(result.generated_sequence)
        self.assertIn("gc_content", result.metrics)

    def test_run_protein_prediction(self) -> None:
        result = self.agent.run(
            query="请帮我预测这个蛋白质的结合潜力",
            protein_sequence=self.sequence,
        )
        self.assertEqual(result.task_type, TaskType.PROTEIN_PREDICTION)
        self.assertIn("prediction_label", result.metrics)
        trace_steps = [event["step"] for event in result.trace_events]
        self.assertIn("prediction", trace_steps)
        self.assertIn("metrics", trace_steps)

    def test_run_requires_sequence(self) -> None:
        with self.assertRaises(ProteinAgentError):
            self.agent.run(query="请帮我生成多肽")

    def test_run_rejects_plain_english_without_sequence(self) -> None:
        with self.assertRaises(ProteinAgentError):
            self.agent.run(query="please design a peptide for this protein target")


if __name__ == "__main__":
    unittest.main()
