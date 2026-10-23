"""Runtime configuration, validated once at boot.

Every setting comes from the environment. `get_settings()` is cached, so the whole process
shares one frozen `Settings`. In production, `production_problems()` refuses development
defaults and reports every problem at once instead of one per restart.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Shipped so `uvicorn` starts with zero configuration on a laptop. Production refuses it.
DEV_SECRET = "dev-only-insecure-secret-do-not-use-in-production"  # noqa: S105

AppEnv = Literal["development", "test", "production"]
ModelProvider = Literal["none", "openai", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: AppEnv = "development"
    product_name: str = "Euron RAGKit"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "console"] = "json"

    # HTTP
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3160", "http://127.0.0.1:3160"]
    )
    web_url: str = "http://localhost:3160"
    api_url: str = "http://localhost:8160"

    # Postgres (pgvector)
    database_url: str = "postgresql+asyncpg://ragkit:ragkit@localhost:5456/ragkit"
    # On AWS the URL carries no password; it is read from this RDS-managed secret for each
    # new connection, so a rotation needs no redeploy.
    database_secret_arn: str | None = None
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_echo: bool = False
    migrate_on_boot: bool = False

    # Redis or Valkey: embedding and query caches, rate limits, session revocation, leases
    redis_url: str = "redis://localhost:6416/0"

    # Sessions and API keys
    session_secret: SecretStr = SecretStr(DEV_SECRET)
    session_ttl_hours: int = Field(default=168, ge=1, le=2160)
    api_key_pepper: SecretStr = SecretStr(DEV_SECRET)
    cookie_secure: bool = False
    cookie_domain: str | None = None
    allow_signup: bool = False

    # Original files and URL snapshots
    storage_backend: Literal["s3", "local"] = "local"
    storage_dir: Path = Path("data/files")
    s3_bucket: str | None = None
    s3_kms_key_id: str | None = None
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    max_upload_mb: int = Field(default=25, ge=1, le=512)
    max_document_pages: int = Field(default=2000, ge=1)

    # URL loader. Private, loopback and link-local addresses are refused unless this is set
    # (a development convenience; production refuses it).
    url_fetch_allow_private: bool = False
    url_fetch_timeout_s: float = Field(default=20.0, gt=0, le=120)

    # Jobs: parse, index and evaluation
    queue_backend: Literal["sqs", "inline"] = "inline"
    sqs_queue_url: str | None = None
    worker_concurrency: int = Field(default=2, ge=1, le=32)
    job_timeout_s: int = Field(default=900, ge=10)
    stale_job_minutes: int = Field(default=15, ge=1)

    # Embeddings. The registry in ai/embeddings.py names the models; these settings say where
    # local models are cached and how to reach hosted providers.
    default_embedding_model: str = "bge-small-en-v1.5"
    embeddings_cache_dir: Path | None = None
    embeddings_batch_size: int = Field(default=64, ge=1, le=512)
    embeddings_api_base: str = "https://api.openai.com/v1"
    embeddings_api_key: SecretStr | None = None
    embedding_cache_ttl_s: int = Field(default=30 * 24 * 3600, ge=0)

    # Reranking
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    # Model answers and the model judge. "none" keeps RAGKit fully offline: the extractive
    # answerer and deterministic grading need no model.
    llm_provider: ModelProvider = "none"
    llm_model: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    ollama_url: str = "http://localhost:11434"
    llm_temperature: float = Field(default=0.0, ge=0, le=2)
    llm_max_tokens: int = Field(default=600, ge=16, le=8192)
    llm_timeout_s: float = Field(default=90.0, gt=0)
    judge_model: str = ""

    # Serving
    query_cache_ttl_s: int = Field(default=300, ge=0)
    query_log_text: bool = True
    warm_models: bool = True

    # Rate limits, requests per minute
    rate_limit_login: int = Field(default=10, ge=1)
    rate_limit_query: int = Field(default=600, ge=1)
    rate_limit_ingest: int = Field(default=120, ge=1)
    rate_limit_eval: int = Field(default=30, ge=1)

    tokenizer: Literal["tiktoken", "heuristic"] = "tiktoken"
    demo_password: SecretStr | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def models_enabled(self) -> bool:
        return self.llm_provider != "none"

    @property
    def judge_model_name(self) -> str:
        return self.judge_model or self.llm_model

    def production_problems(self) -> list[str]:
        """Every reason this configuration is unsafe to serve real users."""
        problems: list[str] = []
        session = self.session_secret.get_secret_value()
        pepper = self.api_key_pepper.get_secret_value()
        for name, value in (("SESSION_SECRET", session), ("API_KEY_PEPPER", pepper)):
            if value == DEV_SECRET or len(value) < 32:
                problems.append(f"{name} must be a random value of at least 32 characters")
        if session == pepper:
            problems.append("SESSION_SECRET and API_KEY_PEPPER must differ")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true behind HTTPS")
        if not self.cors_origins or "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list the web app origins explicitly")
        if self.storage_backend != "s3" or not self.s3_bucket:
            problems.append("STORAGE_BACKEND=s3 with S3_BUCKET is required")
        if self.queue_backend != "sqs" or not self.sqs_queue_url:
            problems.append("QUEUE_BACKEND=sqs with SQS_QUEUE_URL is required")
        if self.aws_endpoint_url:
            problems.append("AWS_ENDPOINT_URL points at an emulator; unset it in production")
        if self.url_fetch_allow_private:
            problems.append("URL_FETCH_ALLOW_PRIVATE must be false: it lets URLs reach the VPC")
        if self.llm_provider != "none" and not self.llm_model:
            problems.append("LLM_MODEL is required when LLM_PROVIDER is set")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
