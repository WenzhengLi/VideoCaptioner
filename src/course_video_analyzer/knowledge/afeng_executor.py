"""Structured-output model adapter for Afeng method stages."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast

from pydantic import BaseModel, ValidationError

from course_video_analyzer.knowledge.afeng import canonical_json
from course_video_analyzer.knowledge.afeng_models import (
    AfengMethodDraft,
    AfengStage,
    FidelityAudit,
    PublicationRecord,
)
from course_video_analyzer.knowledge.afeng_pipeline import StageExecutionResult

PROMPT_FILES: dict[AfengStage, str] = {
    "extract_method": "extract-method.md",
    "audit_fidelity": "audit-fidelity.md",
    "revise": "revise.md",
    "classify_publication": "classify-publication.md",
    "render_markdown": "",
}
STAGE_MODELS: dict[AfengStage, type[BaseModel]] = {
    "extract_method": AfengMethodDraft,
    "audit_fidelity": FidelityAudit,
    "revise": AfengMethodDraft,
    "classify_publication": PublicationRecord,
}
Transport = Callable[[dict[str, Any], dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    endpoint: str
    model: str
    api_key_env: str = "AFENG_LLM_API_KEY"
    timeout_seconds: int = 180
    max_retries: int = 2
    retry_delay_seconds: float = 1.0
    temperature: float = 0.0
    structured_output: bool = True
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    prompt_root: Path = Path("prompts/afeng-method-v001")

    @classmethod
    def from_env(cls) -> "OpenAICompatibleConfig":
        endpoint = os.environ.get("AFENG_LLM_ENDPOINT", "").strip()
        model = os.environ.get("AFENG_LLM_MODEL", "").strip()
        if not endpoint or not model:
            raise RuntimeError("AFENG_LLM_ENDPOINT and AFENG_LLM_MODEL are required")
        return cls(endpoint=endpoint, model=model)


def _extract_json_text(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response does not contain a JSON object")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response JSON root must be an object")
    return value


def _response_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("model response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("model response choice is invalid")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("model response has no message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
        ]
        if texts:
            return "".join(texts)
    raise ValueError("model response content is not text")


class OpenAICompatibleAfengExecutor:
    """Opt-in adapter. It does not claim MiMo compatibility until real API verification."""

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        transport: Transport | None = None,
    ) -> None:
        self.config = config
        self._transport_override = transport

    @property
    def model_name(self) -> str:
        return self.config.model

    def _prompt(self, stage: AfengStage) -> str:
        if stage == "render_markdown":
            raise ValueError("render_markdown is deterministic and must not call a model")
        path = Path(self.config.prompt_root) / PROMPT_FILES[stage]
        if not path.is_file():
            raise FileNotFoundError(f"Afeng prompt is missing: {path}")
        return path.read_text(encoding="utf-8")

    def _headers(self) -> dict[str, str]:
        api_key = os.environ.get(self.config.api_key_env, "").strip()
        if not api_key and self._transport_override is None:
            raise RuntimeError(f"missing API key environment variable: {self.config.api_key_env}")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _request_body(self, stage: AfengStage, payload: dict[str, Any]) -> dict[str, Any]:
        model_type = STAGE_MODELS.get(stage)
        if model_type is None:
            raise ValueError(f"unsupported model stage: {stage}")
        body: dict[str, Any] = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": self._prompt(stage)},
                {
                    "role": "user",
                    "content": "只输出符合契约的 JSON。输入如下：\n" + canonical_json(payload),
                },
            ],
        }
        if self.config.structured_output:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": f"afeng_{stage}",
                    "strict": True,
                    "schema": model_type.model_json_schema(),
                },
            }
        return body

    def _http_transport(
        self, body: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("model HTTP response root must be an object")
        return value

    def execute(
        self, stage: str, payload: dict[str, Any]
    ) -> StageExecutionResult:
        if stage not in STAGE_MODELS:
            raise ValueError(f"unsupported Afeng stage: {stage}")
        typed_stage = cast(AfengStage, stage)
        model_type = STAGE_MODELS[typed_stage]
        body = self._request_body(typed_stage, payload)
        headers = self._headers()
        transport = self._transport_override or self._http_transport
        errors: list[str] = []
        for attempt in range(self.config.max_retries + 1):
            started = time.monotonic()
            try:
                response = transport(body, headers)
                parsed = _extract_json_text(_response_content(response))
                validated = model_type.model_validate(parsed)
                usage_value = response.get("usage")
                usage: dict[str, Any] = usage_value if isinstance(usage_value, dict) else {}
                metadata = {
                    "provider": "openai_compatible",
                    "model": self.config.model,
                    "request_id": str(response.get("id") or ""),
                    "attempt": attempt + 1,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                    "total_tokens": int(usage.get("total_tokens") or 0),
                }
                if (
                    self.config.input_cost_per_million is not None
                    or self.config.output_cost_per_million is not None
                ):
                    metadata["estimated_cost"] = round(
                        metadata["prompt_tokens"]
                        * (self.config.input_cost_per_million or 0)
                        / 1_000_000
                        + metadata["completion_tokens"]
                        * (self.config.output_cost_per_million or 0)
                        / 1_000_000,
                        8,
                    )
                return StageExecutionResult(
                    output=validated.model_dump(mode="json"), metadata=metadata
                )
            except (
                OSError,
                urllib.error.HTTPError,
                urllib.error.URLError,
                json.JSONDecodeError,
                ValidationError,
                ValueError,
            ) as exc:
                errors.append(f"attempt {attempt + 1}: {type(exc).__name__}: {exc}")
                if attempt >= self.config.max_retries:
                    break
                time.sleep(self.config.retry_delay_seconds)
        raise RuntimeError(
            f"Afeng model stage failed after {self.config.max_retries + 1} attempts: "
            + " | ".join(errors)
        )
