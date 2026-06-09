"""LLM gateway contracts and adapters for bank-ready synthesis."""

from __future__ import annotations

import os
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, Field

from .models import EvidenceItem

LLMGatewayMode = Literal["offline_template", "openai_compatible", "gigachat"]


class LLMGatewayConfig(BaseModel):
    """Configuration boundary for model-backed report synthesis."""

    mode: LLMGatewayMode = "offline_template"
    provider: str = "offline"
    model: str = "template-report-v1"
    endpoint_url: str | None = None
    api_key_env_var: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_output_tokens: int = Field(default=1200, ge=1)
    timeout_seconds: int = Field(default=60, ge=1)
    external_calls_enabled: bool = False


class LLMGatewayMetadata(BaseModel):
    """Auditable model metadata stored with every research run."""

    mode: LLMGatewayMode
    provider: str
    model: str
    endpoint_url: str | None
    api_key_env_var: str | None
    api_key_configured: bool
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    external_llm_calls: bool
    synthesis_status: str = "not_requested"
    last_error: str | None = None


class LLMGatewayError(RuntimeError):
    """Raised when a model gateway cannot safely complete a request."""


class LLMGateway(Protocol):
    """Minimal model interface used by future synthesizers."""

    def metadata(self) -> LLMGatewayMetadata:
        """Return auditable model metadata without exposing secrets."""

    def synthesize_report(self, topic: str, evidence_items: list[EvidenceItem]) -> str:
        """Generate a report from evidence items."""


class OfflineTemplateLLMGateway:
    """Offline gateway used for bank-safe MVP runs."""

    def __init__(self, config: LLMGatewayConfig | None = None) -> None:
        self.config = config or LLMGatewayConfig()

    def metadata(self) -> LLMGatewayMetadata:
        """Return metadata showing that no external model calls are used."""

        return _metadata_from_config(self.config, external_llm_calls=False)

    def synthesize_report(self, topic: str, evidence_items: list[EvidenceItem]) -> str:
        """Return a deterministic placeholder without external calls."""

        lines = [
            f"# Offline synthesis for {topic}",
            "",
            "This placeholder does not call an external LLM.",
            f"Evidence items available: {len(evidence_items)}.",
        ]
        return "\n".join(lines)


class OpenAICompatibleLLMGateway:
    """Adapter for future OpenAI-compatible corporate model endpoints."""

    def __init__(self, config: LLMGatewayConfig) -> None:
        if config.mode != "openai_compatible":
            raise LLMGatewayError("OpenAI-compatible gateway requires mode='openai_compatible'.")
        self.config = config

    def metadata(self) -> LLMGatewayMetadata:
        """Return metadata for audit logging without exposing the API key."""

        return _metadata_from_config(
            self.config,
            external_llm_calls=self.config.external_calls_enabled,
        )

    def synthesize_report(self, topic: str, evidence_items: list[EvidenceItem]) -> str:
        """Call an OpenAI-compatible chat completions endpoint when explicitly enabled."""

        if not self.config.external_calls_enabled:
            raise LLMGatewayError("External LLM calls are disabled by configuration.")
        if not self.config.endpoint_url:
            raise LLMGatewayError("OpenAI-compatible endpoint_url is required.")

        api_key = _read_api_key(self.config)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a bank research assistant. Use only provided evidence "
                        "and preserve source ids in every claim."
                    ),
                },
                {
                    "role": "user",
                    "content": _build_prompt(topic, evidence_items),
                },
            ],
        }

        response = httpx.post(
            self.config.endpoint_url,
            json=payload,
            headers=headers,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMGatewayError("Unexpected OpenAI-compatible response format.") from exc


class GigaChatLLMGateway(OpenAICompatibleLLMGateway):
    """Adapter for GigaChat chat-completions-style endpoints with pre-issued token."""

    def __init__(self, config: LLMGatewayConfig) -> None:
        if config.mode != "gigachat":
            raise LLMGatewayError("GigaChat gateway requires mode='gigachat'.")
        self.config = config

    def synthesize_report(self, topic: str, evidence_items: list[EvidenceItem]) -> str:
        """Call a GigaChat endpoint when an access token and external calls are enabled."""

        if not self.config.external_calls_enabled:
            raise LLMGatewayError("External LLM calls are disabled by configuration.")
        if not self.config.endpoint_url:
            raise LLMGatewayError("GigaChat endpoint_url is required.")
        if not _read_api_key(self.config):
            raise LLMGatewayError("GigaChat access token is required.")

        return super().synthesize_report(topic, evidence_items)


class MockLLMGateway(OfflineTemplateLLMGateway):
    """Backward-compatible alias for the offline gateway."""


def build_llm_gateway(config: LLMGatewayConfig | None = None) -> LLMGateway:
    """Build a gateway implementation from config."""

    cfg = config or LLMGatewayConfig()
    if cfg.mode == "offline_template":
        return OfflineTemplateLLMGateway(cfg)
    if cfg.mode == "openai_compatible":
        return OpenAICompatibleLLMGateway(cfg)
    if cfg.mode == "gigachat":
        return GigaChatLLMGateway(cfg)
    raise LLMGatewayError(f"Unsupported LLM gateway mode: {cfg.mode}")


def llm_gateway_config_from_env(prefix: str = "LLM_") -> LLMGatewayConfig:
    """Create gateway config from environment variables."""

    mode = _env(prefix, "GATEWAY_MODE", "offline_template")
    provider = _env(prefix, "PROVIDER", _default_provider_for_mode(mode))
    return LLMGatewayConfig(
        mode=mode,
        provider=provider,
        model=_env(prefix, "MODEL", _default_model_for_provider(provider, mode)),
        endpoint_url=_env(prefix, "ENDPOINT_URL", None),
        api_key_env_var=_env(prefix, "API_KEY_ENV_VAR", _default_api_key_env_var(provider, mode)),
        temperature=float(_env(prefix, "TEMPERATURE", "0.2")),
        max_output_tokens=int(_env(prefix, "MAX_OUTPUT_TOKENS", "1200")),
        timeout_seconds=int(_env(prefix, "TIMEOUT_SECONDS", "60")),
        external_calls_enabled=_env_bool(prefix, "EXTERNAL_CALLS_ENABLED", default=False),
    )


def default_llm_gateway_metadata() -> dict:
    """Return serializable metadata for the configured gateway."""

    return build_llm_gateway(llm_gateway_config_from_env()).metadata().model_dump(mode="json")


def _metadata_from_config(
    config: LLMGatewayConfig,
    *,
    external_llm_calls: bool,
) -> LLMGatewayMetadata:
    return LLMGatewayMetadata(
        mode=config.mode,
        provider=config.provider,
        model=config.model,
        endpoint_url=config.endpoint_url,
        api_key_env_var=config.api_key_env_var,
        api_key_configured=bool(_read_api_key(config)),
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
        timeout_seconds=config.timeout_seconds,
        external_llm_calls=external_llm_calls,
    )


def _read_api_key(config: LLMGatewayConfig) -> str | None:
    if not config.api_key_env_var:
        return None
    return os.getenv(config.api_key_env_var)


def _env(prefix: str, name: str, default: str | None) -> str | None:
    value = os.getenv(f"{prefix}{name}")
    if value is None or value == "":
        return default
    return value


def _env_bool(prefix: str, name: str, *, default: bool) -> bool:
    value = os.getenv(f"{prefix}{name}")
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_provider_for_mode(mode: str | None) -> str:
    if mode == "gigachat":
        return "gigachat"
    if mode == "openai_compatible":
        return "openai_compatible"
    return "offline"


def _default_model_for_provider(provider: str | None, mode: str | None) -> str:
    if provider == "local_qwen":
        return "qwen3:1.7b"
    if provider == "alfagen":
        return "alfagen-default"
    if provider == "gigachat" or mode == "gigachat":
        return "GigaChat"
    if mode == "openai_compatible":
        return "local-model"
    return "template-report-v1"


def _default_api_key_env_var(provider: str | None, mode: str | None) -> str | None:
    if provider == "alfagen":
        return "ALFAGEN_API_KEY"
    if provider == "gigachat" or mode == "gigachat":
        return "GIGACHAT_ACCESS_TOKEN"
    if mode == "openai_compatible":
        return "LLM_API_KEY"
    return None


def _build_prompt(topic: str, evidence_items: list[EvidenceItem]) -> str:
    evidence_lines = []
    for item in evidence_items[:20]:
        evidence_lines.append(
            "\n".join(
                [
                    f"Evidence: {item.source_id}/{item.chunk_id}",
                    f"Title: {item.title or item.source_id}",
                    f"URL: {item.url or ''}",
                    f"Text: {' '.join(item.text.split())}",
                ]
            )
        )

    return "\n\n".join(
        [
            f"Topic: {topic}",
            "Write a concise analytical report using only the evidence below.",
            "Every claim must include evidence ids in square brackets.",
            "\n\n".join(evidence_lines),
        ]
    )
