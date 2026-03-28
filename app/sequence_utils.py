from __future__ import annotations

import re


ALLOWED_PROTEIN_CHARS = set("ACDEFGHIKLMNPQRSTVWYBXZJUO")
SEQUENCE_LABEL_PATTERN = re.compile(
    r"(?:蛋白质序列|蛋白序列|protein\s*sequence|protein_sequence|sequence|seq)"
    r"\s*[:：=]?\s*([A-Za-z][A-Za-z\s\-]{7,})",
    re.IGNORECASE,
)
UPPERCASE_SEQUENCE_PATTERN = re.compile(
    r"\b([ACDEFGHIKLMNPQRSTVWYBXZJUO]{8,})\b",
)


class SequenceError(ValueError):
    pass


def extract_protein_sequence(text: str) -> str | None:
    for match in SEQUENCE_LABEL_PATTERN.finditer(text):
        candidate = _normalize_letters(match.group(1))
        if _looks_like_sequence(candidate):
            return candidate

    for match in UPPERCASE_SEQUENCE_PATTERN.finditer(text):
        candidate = match.group(1)
        if _looks_like_sequence(candidate):
            return candidate

    return None


def normalize_protein_sequence(sequence: str, min_length: int = 8) -> str:
    normalized = _normalize_letters(sequence)
    if len(normalized) < min_length:
        raise SequenceError(f"蛋白质序列长度至少需要 {min_length} 个字符。")

    invalid_chars = sorted(set(normalized) - ALLOWED_PROTEIN_CHARS)
    if invalid_chars:
        raise SequenceError(f"蛋白质序列包含非法字符: {', '.join(invalid_chars)}")

    return normalized


def _normalize_letters(raw_text: str) -> str:
    return re.sub(r"[^A-Za-z]", "", raw_text).upper()


def _looks_like_sequence(candidate: str) -> bool:
    return bool(candidate) and set(candidate).issubset(ALLOWED_PROTEIN_CHARS)
