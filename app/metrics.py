from __future__ import annotations

from typing import Any


HYDROPHOBIC_RESIDUES = set("AILMFWVYC")
POSITIVE_RESIDUES = set("KRH")
NEGATIVE_RESIDUES = set("DE")
AROMATIC_RESIDUES = set("FWYH")
APTAMER_BASES = set("ACGTU")


def compute_metrics(
    task_type: str,
    protein_sequence: str,
    generated_sequence: str | None = None,
) -> dict[str, Any]:
    if task_type == "peptide_generation":
        return compute_peptide_metrics(protein_sequence, generated_sequence or "")
    if task_type == "aptamer_generation":
        return compute_aptamer_metrics(generated_sequence or "")
    return compute_protein_prediction_metrics(protein_sequence)


def compute_protein_prediction_metrics(protein_sequence: str) -> dict[str, Any]:
    length = len(protein_sequence)
    hydrophobic_ratio = _ratio(_count_chars(protein_sequence, HYDROPHOBIC_RESIDUES), length)
    charge_proxy = _charge_proxy(protein_sequence)
    aromatic_ratio = _ratio(_count_chars(protein_sequence, AROMATIC_RESIDUES), length)
    complexity_ratio = round(len(set(protein_sequence)) / max(1, min(length, 20)), 3)
    binding_potential_score = _clamp01(
        0.45 * (1 - abs(hydrophobic_ratio - 0.34))
        + 0.30 * _normalize_score(charge_proxy, scale=4.0)
        + 0.25 * aromatic_ratio
    )

    return {
        "sequence_length": length,
        "hydrophobic_ratio": round(hydrophobic_ratio, 3),
        "charge_proxy": round(charge_proxy, 3),
        "aromatic_ratio": round(aromatic_ratio, 3),
        "complexity_ratio": complexity_ratio,
        "binding_potential_score": round(binding_potential_score, 3),
        "prediction_label": (
            "higher_binding_potential"
            if binding_potential_score >= 0.55
            else "baseline_binding_potential"
        ),
    }


def compute_peptide_metrics(protein_sequence: str, peptide_sequence: str) -> dict[str, Any]:
    length = len(peptide_sequence)
    hydrophobic_ratio = _ratio(_count_chars(peptide_sequence, HYDROPHOBIC_RESIDUES), max(1, length))
    charge_proxy = _charge_proxy(peptide_sequence)
    shared_trimer_ratio = _shared_kmer_ratio(protein_sequence, peptide_sequence, k=3)
    binding_proxy_score = _clamp01(
        0.40 * (1 - abs(hydrophobic_ratio - 0.42))
        + 0.35 * _normalize_score(charge_proxy, scale=3.0)
        + 0.25 * shared_trimer_ratio
    )

    return {
        "candidate_length": length,
        "hydrophobic_ratio": round(hydrophobic_ratio, 3),
        "charge_proxy": round(charge_proxy, 3),
        "shared_trimer_ratio": round(shared_trimer_ratio, 3),
        "binding_proxy_score": round(binding_proxy_score, 3),
    }


def compute_aptamer_metrics(aptamer_sequence: str) -> dict[str, Any]:
    normalized = aptamer_sequence.upper()
    length = len(normalized)
    gc_count = normalized.count("G") + normalized.count("C")
    gc_content = _ratio(gc_count, max(1, length))
    diversity_ratio = round(len(set(normalized)) / 4, 3)
    longest_homopolymer = _longest_homopolymer(normalized)
    affinity_proxy_score = _clamp01(
        0.45 * (1 - abs(gc_content - 0.50))
        + 0.30 * min(1.0, diversity_ratio)
        + 0.25 * _normalize_length(length, ideal=28)
        - 0.05 * max(0, longest_homopolymer - 4)
    )

    return {
        "candidate_length": length,
        "gc_content": round(gc_content, 3),
        "diversity_ratio": round(diversity_ratio, 3),
        "longest_homopolymer": longest_homopolymer,
        "affinity_proxy_score": round(affinity_proxy_score, 3),
    }


def _shared_kmer_ratio(reference: str, candidate: str, k: int) -> float:
    if len(candidate) < k or len(reference) < k:
        return 0.0

    reference_kmers = {reference[i : i + k] for i in range(len(reference) - k + 1)}
    candidate_kmers = [candidate[i : i + k] for i in range(len(candidate) - k + 1)]
    shared = sum(1 for kmer in candidate_kmers if kmer in reference_kmers)
    return shared / len(candidate_kmers)


def _count_chars(sequence: str, alphabet: set[str]) -> int:
    return sum(1 for residue in sequence if residue in alphabet)


def _charge_proxy(sequence: str) -> float:
    positives = _count_chars(sequence, POSITIVE_RESIDUES)
    negatives = _count_chars(sequence, NEGATIVE_RESIDUES)
    return (positives - negatives) / max(1, len(sequence))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _normalize_score(score: float, scale: float) -> float:
    return max(0.0, min(1.0, (score + scale) / (2 * scale)))


def _normalize_length(length: int, ideal: int) -> float:
    if ideal <= 0:
        return 0.0
    distance = abs(length - ideal)
    return max(0.0, 1 - distance / ideal)


def _longest_homopolymer(sequence: str) -> int:
    longest = 0
    current = 0
    previous = ""

    for base in sequence:
        if base == previous:
            current += 1
        else:
            current = 1
            previous = base
        longest = max(longest, current)

    return longest


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
