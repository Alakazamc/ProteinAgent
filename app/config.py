from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


ENV_FILE_NAME = ".env"


@dataclass(frozen=True)
class ModelConfig:
    task_type: str
    provider: str
    model_name: str
    base_url: str | None
    api_key: str | None
    timeout_seconds: int

    @property
    def is_configured(self) -> bool:
        if self.provider == "local-stub":
            return True
        return bool(self.base_url)


@dataclass(frozen=True)
class RouterLLMConfig:
    provider: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: int = 30
    fallback_to_keywords: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.provider and self.model_name and self.base_url)


@dataclass(frozen=True)
class AppConfig:
    protein_model: ModelConfig
    peptide_model: ModelConfig
    aptamer_model: ModelConfig
    router_llm: RouterLLMConfig = field(default_factory=RouterLLMConfig)
    min_protein_sequence_length: int = 8
    rag_enabled: bool = True
    rag_top_k: int = 3
    rag_data_path: str | None = None
    rag_backend: str = "local-hash"
    rag_embedding_model: str = "all-MiniLM-L6-v2"
    db_url: str = "sqlite+aiosqlite:///./protein_agent.db"
    celery_broker_url: str = "redis://localhost:6379/0"


def load_dotenv(env_path: Path | None = None) -> None:
    target = env_path or Path(__file__).resolve().parents[1] / ENV_FILE_NAME
    if not target.exists():
        return

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config() -> AppConfig:
    load_dotenv()

    return AppConfig(
        protein_model=_load_model_config(
            prefix="PROTEIN_MODEL",
            task_type="protein_prediction",
            default_name="saprot-protein-predictor",
        ),
        peptide_model=_load_model_config(
            prefix="PEPTIDE_MODEL",
            task_type="peptide_generation",
            default_name="paired-peptide-generator",
        ),
        aptamer_model=_load_model_config(
            prefix="APTAMER_MODEL",
            task_type="aptamer_generation",
            default_name="nucleic-aptamer-generator",
        ),
        router_llm=_load_router_llm_config(),
        min_protein_sequence_length=_read_int("MIN_PROTEIN_SEQUENCE_LENGTH", 8),
        rag_enabled=os.getenv("RAG_ENABLED", "true").strip().lower() in ("true", "1", "yes"),
        rag_top_k=_read_int("RAG_TOP_K", 3),
        rag_data_path=_read_optional_env("RAG_DATA_PATH"),
        rag_backend=(os.getenv("RAG_BACKEND", "local-hash").strip().lower() or "local-hash"),
        rag_embedding_model=(
            os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()
            or "all-MiniLM-L6-v2"
        ),
        db_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./protein_agent.db"),
        celery_broker_url=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    )


def _load_model_config(prefix: str, task_type: str, default_name: str) -> ModelConfig:
    provider = (os.getenv(f"{prefix}_PROVIDER", "local-stub").strip() or "local-stub").lower()
    return ModelConfig(
        task_type=task_type,
        provider=provider,
        model_name=os.getenv(f"{prefix}_NAME", default_name).strip() or default_name,
        base_url=_read_optional_env(f"{prefix}_BASE_URL"),
        api_key=_read_optional_env(f"{prefix}_API_KEY"),
        timeout_seconds=_read_int(f"{prefix}_TIMEOUT_SECONDS", 30),
    )


def _load_router_llm_config() -> RouterLLMConfig:
    provider = (
        _read_optional_env("ROUTER_LLM_PROVIDER")
        or _read_optional_env("LLM_PROVIDER")
    )
    model_name = (
        _read_optional_env("ROUTER_LLM_MODEL_NAME")
        or _read_optional_env("MODEL_NAME")
    )
    base_url = (
        _read_optional_env("ROUTER_LLM_BASE_URL")
        or _read_optional_env("MODEL_BASE_URL")
    )
    api_key = (
        _read_optional_env("ROUTER_LLM_API_KEY")
        or _read_optional_env("MODEL_API_KEY")
    )
    timeout_seconds = _read_int(
        "ROUTER_LLM_TIMEOUT_SECONDS",
        _read_int("MODEL_TIMEOUT_SECONDS", 30),
    )
    fallback_to_keywords = (
        os.getenv("ROUTER_LLM_FALLBACK_TO_KEYWORDS", "true").strip().lower()
        in ("true", "1", "yes")
    )
    return RouterLLMConfig(
        provider=provider.lower() if provider else None,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        fallback_to_keywords=fallback_to_keywords,
    )


def _read_optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _read_int(name: str, default: int) -> int:
    raw_value = (os.getenv(name) or str(default)).strip()
    try:
        return int(raw_value)
    except ValueError:
        return default
