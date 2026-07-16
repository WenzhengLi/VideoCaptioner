"""Structured-output model adapter for Afeng method stages."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, cast

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
CommandRunner = Callable[
    [list[str], str, Path, int], subprocess.CompletedProcess[str]
]


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    endpoint: str
    model: str
    api_key_env: str = "AFENG_LLM_API_KEY"
    timeout_seconds: int = 180
    max_retries: int = 2
    retry_delay_seconds: float = 1.0
    temperature: float = 0.0
    top_p: float | None = None
    max_completion_tokens: int = 16_384
    thinking: Literal["enabled", "disabled"] | None = None
    response_format: Literal["json_schema", "json_object", "none"] = "json_schema"
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    cost_currency: str = ""
    prompt_root: Path = Path("prompts/afeng-method-v001")

    @classmethod
    def from_env(cls) -> "OpenAICompatibleConfig":
        endpoint = os.environ.get("AFENG_LLM_ENDPOINT", "").strip()
        model = os.environ.get("AFENG_LLM_MODEL", "").strip()
        if not endpoint or not model:
            raise RuntimeError("AFENG_LLM_ENDPOINT and AFENG_LLM_MODEL are required")
        return cls(endpoint=endpoint, model=model)

    @classmethod
    def mimo_v25_pro(cls) -> "OpenAICompatibleConfig":
        """Official Xiaomi MiMo API defaults verified from platform documentation."""
        return cls(
            endpoint="https://api.xiaomimimo.com/v1/chat/completions",
            model="mimo-v2.5-pro",
            api_key_env="MIMO_API_KEY",
            temperature=1.0,
            top_p=0.95,
            thinking="enabled",
            response_format="json_object",
            input_cost_per_million=3.0,
            output_cost_per_million=6.0,
            cost_currency="CNY",
        )


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
            "max_completion_tokens": self.config.max_completion_tokens,
            "stream": False,
            "messages": [
                {"role": "system", "content": self._prompt(stage)},
                {
                    "role": "user",
                    "content": "只输出符合契约的 JSON。输入如下：\n" + canonical_json(payload),
                },
            ],
        }
        if self.config.top_p is not None:
            body["top_p"] = self.config.top_p
        if self.config.thinking is not None:
            body["thinking"] = {"type": self.config.thinking}
        if self.config.response_format == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": f"afeng_{stage}",
                    "strict": True,
                    "schema": model_type.model_json_schema(),
                },
            }
        elif self.config.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
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
                    metadata["cost_currency"] = self.config.cost_currency
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


@dataclass(frozen=True)
class ClaudeCodeCcSwitchConfig:
    command: tuple[str, ...] = ("npx.cmd", "-y", "@anthropic-ai/claude-code")
    model: str = "mimo-v2.5-pro"
    timeout_seconds: int = 900
    max_retries: int = 1
    retry_delay_seconds: float = 1.0
    max_budget_usd: float | None = 2.0
    setting_sources: str = "user"
    settings_path: Path = Path.home() / ".claude" / "settings.json"
    prompt_root: Path = Path("prompts/afeng-method-v001")
    working_directory: Path = Path.cwd()


def inspect_cc_switch_claude_settings(path: Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"Claude settings written by CC Switch are missing: {target}")
    payload = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Claude settings root must be an object")
    env = payload.get("env")
    if not isinstance(env, dict):
        raise ValueError("Claude settings do not contain an env object")
    base_url = str(env.get("ANTHROPIC_BASE_URL") or "")
    model = str(env.get("ANTHROPIC_MODEL") or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL") or "")
    auth_configured = bool(
        env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY")
    )
    if not base_url or not model or not auth_configured:
        raise ValueError("CC Switch Claude provider is incomplete")
    return {
        "settings_path": str(target),
        "base_url": base_url,
        "model": model,
        "auth_configured": auth_configured,
    }


def _default_command_runner(
    command: list[str], prompt: str, cwd: Path, timeout_seconds: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=prompt,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )


class ClaudeCodeCcSwitchExecutor:
    """Invoke the provider selected by CC Switch through headless Claude Code."""

    def __init__(
        self,
        config: ClaudeCodeCcSwitchConfig | None = None,
        *,
        runner: CommandRunner | None = None,
    ) -> None:
        self.config = config or ClaudeCodeCcSwitchConfig()
        self._runner = runner or _default_command_runner
        self.provider_info = inspect_cc_switch_claude_settings(self.config.settings_path)
        self.config.working_directory.mkdir(parents=True, exist_ok=True)

    @property
    def model_name(self) -> str:
        return self.config.model

    def _prompt(self, stage: AfengStage, payload: dict[str, Any]) -> str:
        if stage == "render_markdown":
            raise ValueError("render_markdown is deterministic and must not call Claude Code")
        rule_path = Path(self.config.prompt_root) / PROMPT_FILES[stage]
        if not rule_path.is_file():
            raise FileNotFoundError(f"Afeng prompt is missing: {rule_path}")
        return (
            rule_path.read_text(encoding="utf-8")
            + "\n\n只使用以下输入。不要调用工具，不要读取项目文件，不要补充外部知识。"
            + "只输出符合 JSON Schema 的对象。\n\n输入：\n"
            + canonical_json(payload)
        )

    def _command(self, stage: AfengStage) -> list[str]:
        model_type = STAGE_MODELS.get(stage)
        if model_type is None:
            raise ValueError(f"unsupported Afeng stage: {stage}")
        command = [
            *self.config.command,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.config.model,
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--no-session-persistence",
            "--setting-sources",
            self.config.setting_sources,
            "--safe-mode",
            "--prompt-suggestions",
            "false",
            "--json-schema",
            json.dumps(model_type.model_json_schema(), ensure_ascii=False, separators=(",", ":")),
        ]
        if self.config.max_budget_usd is not None:
            command.extend(["--max-budget-usd", str(self.config.max_budget_usd)])
        return command

    def execute(self, stage: str, payload: dict[str, Any]) -> StageExecutionResult:
        if stage not in STAGE_MODELS:
            raise ValueError(f"unsupported Afeng stage: {stage}")
        typed_stage = cast(AfengStage, stage)
        model_type = STAGE_MODELS[typed_stage]
        prompt = self._prompt(typed_stage, payload)
        command = self._command(typed_stage)
        errors: list[str] = []
        for attempt in range(self.config.max_retries + 1):
            started = time.monotonic()
            try:
                completed = self._runner(
                    command,
                    prompt,
                    self.config.working_directory,
                    self.config.timeout_seconds,
                )
                if completed.returncode != 0:
                    error_text = (completed.stderr or completed.stdout or "").strip()
                    raise RuntimeError(
                        f"Claude Code exited {completed.returncode}: {error_text[:1000]}"
                    )
                envelope = json.loads(completed.stdout)
                if not isinstance(envelope, dict):
                    raise ValueError("Claude Code output envelope must be an object")
                if envelope.get("is_error") is True or envelope.get("subtype") != "success":
                    raise RuntimeError(
                        f"Claude Code request failed: {envelope.get('api_error_status') or envelope.get('result')}"
                    )
                structured = envelope.get("structured_output")
                if isinstance(structured, dict):
                    parsed = structured
                else:
                    parsed = _extract_json_text(str(envelope.get("result") or ""))
                validated = model_type.model_validate(parsed)
                usage_value = envelope.get("usage")
                usage: dict[str, Any] = usage_value if isinstance(usage_value, dict) else {}
                model_usage_value = envelope.get("modelUsage")
                model_usage = (
                    model_usage_value if isinstance(model_usage_value, dict) else {}
                )
                selected_usage = model_usage.get(self.config.model)
                selected: dict[str, Any] = (
                    selected_usage if isinstance(selected_usage, dict) else {}
                )
                metadata = {
                    "provider": "cc_switch_claude_code",
                    "model": self.config.model,
                    "base_url": self.provider_info["base_url"],
                    "attempt": attempt + 1,
                    "duration_ms": int(
                        envelope.get("duration_api_ms")
                        or (time.monotonic() - started) * 1000
                    ),
                    "prompt_tokens": int(
                        selected.get("inputTokens") or usage.get("input_tokens") or 0
                    ),
                    "completion_tokens": int(
                        selected.get("outputTokens") or usage.get("output_tokens") or 0
                    ),
                    "cache_read_tokens": int(
                        selected.get("cacheReadInputTokens")
                        or usage.get("cache_read_input_tokens")
                        or 0
                    ),
                    "estimated_cost": float(
                        selected.get("costUSD") or envelope.get("total_cost_usd") or 0
                    ),
                    "cost_currency": "USD",
                    "context_window": int(selected.get("contextWindow") or 0),
                    "max_output_tokens": int(selected.get("maxOutputTokens") or 0),
                    "claude_code_session_id": str(envelope.get("session_id") or ""),
                }
                metadata["total_tokens"] = (
                    metadata["prompt_tokens"] + metadata["completion_tokens"]
                )
                return StageExecutionResult(
                    output=validated.model_dump(mode="json"), metadata=metadata
                )
            except (
                OSError,
                subprocess.SubprocessError,
                json.JSONDecodeError,
                ValidationError,
                ValueError,
                RuntimeError,
            ) as exc:
                errors.append(f"attempt {attempt + 1}: {type(exc).__name__}: {exc}")
                if attempt >= self.config.max_retries:
                    break
                time.sleep(self.config.retry_delay_seconds)
        raise RuntimeError(
            f"CC Switch Claude stage failed after {self.config.max_retries + 1} attempts: "
            + " | ".join(errors)
        )
