from __future__ import annotations

import unittest

from app.sequence_utils import extract_protein_sequence, normalize_protein_sequence


class SequenceUtilsTests(unittest.TestCase):
    def test_extracts_labeled_sequence(self) -> None:
        result = extract_protein_sequence(
            "请根据蛋白质序列 MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP 生成一个配对多肽"
        )
        self.assertEqual(result, "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP")

    def test_extracts_labeled_lowercase_sequence(self) -> None:
        result = extract_protein_sequence(
            "protein sequence: mktayiakqrqisfvkshfsrqdildlwiyhtqgyfp"
        )
        self.assertEqual(result, "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP")

    def test_does_not_treat_plain_english_as_sequence(self) -> None:
        self.assertIsNone(
            extract_protein_sequence("please design a peptide for this protein target")
        )

    def test_normalize_sequence_strips_spaces(self) -> None:
        result = normalize_protein_sequence("MKTAYIAK QRQISFVK SHFS")
        self.assertEqual(result, "MKTAYIAKQRQISFVKSHFS")


if __name__ == "__main__":
    unittest.main()
