from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class KnowledgeBaseDataTest(unittest.TestCase):
    """Verify the seed JSONL is well-formed."""

    DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "protein_knowledge.jsonl"

    def test_jsonl_file_exists(self) -> None:
        self.assertTrue(self.DATA_PATH.exists(), f"Missing {self.DATA_PATH}")

    def test_all_entries_valid_json(self) -> None:
        for idx, line in enumerate(self.DATA_PATH.read_text("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            with self.subTest(line=idx):
                obj = json.loads(line)
                self.assertIn("text", obj)
                self.assertIsInstance(obj["text"], str)
                self.assertTrue(len(obj["text"]) > 0)

    def test_minimum_entry_count(self) -> None:
        entries = [
            json.loads(l)
            for l in self.DATA_PATH.read_text("utf-8").splitlines()
            if l.strip()
        ]
        self.assertGreaterEqual(len(entries), 10)


class KnowledgeBaseModuleTest(unittest.TestCase):
    """Test ProteinKnowledgeBase with a tiny fixture file."""

    def _make_fixture(self, entries: list[dict]) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        for entry in entries:
            tmp.write(json.dumps(entry, ensure_ascii=False) + "\n")
        tmp.close()
        return Path(tmp.name)

    def test_load_with_missing_file(self) -> None:
        from app.knowledge_base import ProteinKnowledgeBase

        kb = ProteinKnowledgeBase(data_path="/tmp/__nonexistent__.jsonl")
        self.assertFalse(kb.ready)
        self.assertEqual(kb.entry_count, 0)
        self.assertEqual(kb.search("anything"), [])

    def test_load_with_empty_query(self) -> None:
        from app.knowledge_base import ProteinKnowledgeBase

        kb = ProteinKnowledgeBase()
        self.assertTrue(kb.ready)
        self.assertEqual(kb.search(""), [])
        self.assertEqual(kb.search("   "), [])

    def test_search_returns_results(self) -> None:
        from app.knowledge_base import ProteinKnowledgeBase

        fixture = self._make_fixture([
            {"text": "蛋白激酶在细胞信号转导中非常重要。", "source": "test", "category": "test"},
            {"text": "适配体可以通过 SELEX 技术筛选。", "source": "test", "category": "test"},
            {"text": "多肽药物设计需要控制分子量。", "source": "test", "category": "test"},
        ])
        kb = ProteinKnowledgeBase(data_path=fixture)
        self.assertTrue(kb.ready)
        self.assertEqual(kb.entry_count, 3)
        self.assertEqual(kb.backend_name, "local-hash")

        results = kb.search("蛋白激酶信号", top_k=2)
        self.assertLessEqual(len(results), 2)
        self.assertTrue(all(hasattr(r, "text") for r in results))
        self.assertTrue(all(hasattr(r, "score") for r in results))

    def test_list_entries(self) -> None:
        from app.knowledge_base import ProteinKnowledgeBase

        kb = ProteinKnowledgeBase()
        entries = kb.list_entries()
        self.assertIsInstance(entries, list)
        if kb.entry_count > 0:
            self.assertIn("text", entries[0])
            self.assertIn("source", entries[0])



if __name__ == "__main__":
    unittest.main()
