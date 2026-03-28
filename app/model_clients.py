from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request

from .config import ModelConfig
from .schemas import ModelExecutionRequest, ModelExecutionResult, TaskType


class ModelClientError(Exception):
    pass


class SequenceModelClient:
    def run(
        self,
        model_request: ModelExecutionRequest,
        model_config: ModelConfig,
    ) -> ModelExecutionResult:
        raise NotImplementedError


@dataclass
class LocalStubSequenceModelClient(SequenceModelClient):
    def run(
        self,
        model_request: ModelExecutionRequest,
        model_config: ModelConfig,
    ) -> ModelExecutionResult:
        if model_request.task_type == TaskType.PEPTIDE_GENERATION:
            peptide = _generate_stub_peptide(model_request.protein_sequence)
            return ModelExecutionResult(
                output_text=(
                    "本次返回的是本地 stub 多肽候选，用于验证 agent 路由、序列提取和接口联调。"
                ),
                generated_sequence=peptide,
                raw_payload={"mode": "local-stub", "task_type": model_request.task_type.value},
            )

        if model_request.task_type == TaskType.APTAMER_GENERATION:
            aptamer = _generate_stub_aptamer(
                model_request.protein_sequence,
                prefer_rna="rna" in model_request.query.lower(),
            )
            return ModelExecutionResult(
                output_text=(
                    "本次返回的是本地 stub 适配体候选，用于验证 agent 路由、序列提取和接口联调。"
                ),
                generated_sequence=aptamer,
                raw_payload={"mode": "local-stub", "task_type": model_request.task_type.value},
            )

        summary = (
            "本次返回的是本地 stub 蛋白质预测摘要，用于验证 agent 路由和预测分支的数据结构。"
        )
        return ModelExecutionResult(
            output_text=summary,
            raw_payload={"mode": "local-stub", "task_type": model_request.task_type.value},
        )


@dataclass
class GenericJsonSequenceModelClient(SequenceModelClient):
    def run(
        self,
        model_request: ModelExecutionRequest,
        model_config: ModelConfig,
    ) -> ModelExecutionResult:
        if not model_config.base_url:
            raise ModelClientError(f"{model_config.task_type} 缺少 MODEL_BASE_URL 配置。")

        payload = json.dumps(
            {
                "model": model_config.model_name,
                "task_type": model_request.task_type.value,
                "query": model_request.query,
                "protein_sequence": model_request.protein_sequence,
            }
        ).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if model_config.api_key:
            headers["Authorization"] = f"Bearer {model_config.api_key}"

        http_request = request.Request(
            model_config.base_url,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=model_config.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ModelClientError(
                f"{model_config.model_name} 请求失败，状态码 {exc.code}: {detail or exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise ModelClientError(
                f"{model_config.model_name} 网络请求失败: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ModelClientError(f"{model_config.model_name} 返回了非 JSON 响应。") from exc

        return _parse_generic_json_response(response_payload)


def build_model_client(provider: str) -> SequenceModelClient:
    if provider == "local-stub":
        return LocalStubSequenceModelClient()
    if provider == "generic-json":
        return GenericJsonSequenceModelClient()
    raise ModelClientError(
        f"不支持的模型 provider: {provider}。当前只支持 local-stub 和 generic-json。"
    )


def _parse_generic_json_response(payload: dict) -> ModelExecutionResult:
    generated_sequence = _first_string(
        payload.get("generated_sequence"),
        payload.get("sequence"),
        payload.get("candidate_sequence"),
        payload.get("candidate"),
    )
    output_text = _first_string(
        payload.get("summary"),
        payload.get("prediction"),
        payload.get("message"),
        payload.get("result"),
        payload.get("text"),
    )

    if not output_text:
        if generated_sequence:
            output_text = "模型已返回候选序列。"
        else:
            output_text = json.dumps(payload, ensure_ascii=False)

    metrics = payload.get("metrics")
    return ModelExecutionResult(
        output_text=output_text,
        generated_sequence=generated_sequence,
        metrics=metrics if isinstance(metrics, dict) else {},
        raw_payload=payload,
    )


def _first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _generate_stub_peptide(protein_sequence: str) -> str:
    normalized = (
        protein_sequence.replace("X", "A")
        .replace("B", "N")
        .replace("Z", "Q")
        .replace("U", "C")
        .replace("O", "K")
    )
    candidate_length = min(14, max(8, len(normalized) // 3))
    best_start = 0
    best_score = float("-inf")

    for start in range(0, len(normalized) - candidate_length + 1):
        window = normalized[start : start + candidate_length]
        score = _peptide_window_score(window)
        if score > best_score:
            best_score = score
            best_start = start

    return normalized[best_start : best_start + candidate_length]


def _generate_stub_aptamer(protein_sequence: str, prefer_rna: bool) -> str:
    aa_to_base = {
        "A": "A",
        "C": "C",
        "D": "G",
        "E": "G",
        "F": "T",
        "G": "G",
        "H": "C",
        "I": "T",
        "K": "A",
        "L": "T",
        "M": "C",
        "N": "A",
        "P": "G",
        "Q": "A",
        "R": "G",
        "S": "C",
        "T": "C",
        "V": "T",
        "W": "T",
        "Y": "C",
        "X": "A",
        "B": "G",
        "Z": "A",
        "U": "C",
        "O": "A",
        "J": "T",
    }
    scaffold = "".join(aa_to_base.get(residue, "A") for residue in protein_sequence[:28])
    if len(scaffold) < 28:
        scaffold = (scaffold + "GACT" * 8)[:28]
    if prefer_rna:
        return scaffold.replace("T", "U")
    return scaffold


def _peptide_window_score(window: str) -> float:
    positive_bonus = sum(1 for residue in window if residue in {"K", "R", "H"})
    aromatic_bonus = sum(1 for residue in window if residue in {"F", "W", "Y"})
    glycine_penalty = sum(1 for residue in window if residue == "G")
    return positive_bonus * 1.2 + aromatic_bonus - glycine_penalty * 0.3

