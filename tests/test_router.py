from __future__ import annotations

import unittest

from app.router import RouteError, route_query
from app.schemas import TaskType


class RouterTests(unittest.TestCase):
    def test_route_peptide_generation(self) -> None:
        decision = route_query("给这个蛋白质序列 MKTAYIAKQRQISFVKSHFS 设计一个配对多肽")
        self.assertEqual(decision.task_type, TaskType.PEPTIDE_GENERATION)
        self.assertIn("多肽", decision.matched_keywords)

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


if __name__ == "__main__":
    unittest.main()

