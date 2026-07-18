#!/usr/bin/env python3
"""Deploy and smoke-test the Afeng Dify advanced-chat application."""

from __future__ import annotations

import base64
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = "http://127.0.0.1:3080"
APP_NAME = "阿峰"
TEMPLATE_PATH = Path("deploy/dify/workflows/afeng-chatflow.yml")
MAP_PATH = Path("data/dify/document-map-v1.json")
ADMIN_ENV_PATH = Path("D:/Dev/dify-deploy/secrets/admin.env")
SMOKE_OUTPUT_PATH = Path("data/dify/afeng-app-smoke.json")
CITATION_INDEX_PATH = Path("data/dify/afeng-app-index-v1/citation-index.json")


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


class ConsoleClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def login(self, email: str, password: str) -> None:
        encoded_password = base64.b64encode(password.encode("utf-8")).decode("ascii")
        self.request(
            "POST",
            "/console/api/login",
            {"email": email, "password": encoded_password, "remember_me": True},
            include_csrf=False,
        )

    def _csrf_token(self) -> str:
        for cookie in self.jar:
            if cookie.name == "csrf_token":
                return str(cookie.value)
        raise RuntimeError("Dify login succeeded but csrf_token is missing")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        include_csrf: bool = True,
        raw: bool = False,
        timeout: float = 60,
    ) -> Any:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if include_csrf:
            headers["X-CSRF-Token"] = self._csrf_token()
        req = urllib.request.Request(self.base_url + path, data=body, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=timeout) as response:
                data = response.read()
                if raw:
                    return data.decode("utf-8", errors="replace")
                if not data:
                    return {}
                return json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"Dify {method} {path} failed: HTTP {exc.code}: {detail}") from exc


def _find_app(client: ConsoleClient, name: str) -> dict[str, Any] | None:
    result = client.request("GET", "/console/api/apps?page=1&limit=100")
    for app in result.get("data", []):
        if app.get("name") == name:
            return app
    return None


def _parse_sse_answer(text: str) -> tuple[str, list[str]]:
    answer_parts: list[str] = []
    errors: list[str] = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        event_type = event.get("event")
        if event_type in {"message", "agent_message"}:
            answer_parts.append(str(event.get("answer") or ""))
        elif event_type in {"workflow_finished", "message_end"}:
            outputs = (event.get("data") or {}).get("outputs") or {}
            if not answer_parts and outputs:
                answer_parts.append(str(outputs.get("answer") or outputs.get("text") or ""))
        elif event_type in {"error", "workflow_failed"}:
            errors.append(str(event.get("message") or (event.get("data") or {}).get("error") or event))
    return "".join(answer_parts).strip(), errors


def main() -> int:
    admin = _load_env(ADMIN_ENV_PATH)
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    dataset_id = str(mapping.get("dataset_id") or "")
    if not dataset_id:
        raise RuntimeError("document-map-v1.json has no bound dataset_id")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "__DIFY_DATASET_ID__" not in template:
        raise RuntimeError("Afeng DSL template is missing the dataset placeholder")
    runtime_dsl = template.replace("__DIFY_DATASET_ID__", dataset_id)
    if "__AFENG_CITATION_INDEX_JSON__" not in runtime_dsl:
        raise RuntimeError("Afeng DSL template is missing the citation index placeholder")
    citation_index = json.loads(CITATION_INDEX_PATH.read_text(encoding="utf-8"))
    runtime_dsl = runtime_dsl.replace(
        "__AFENG_CITATION_INDEX_JSON__",
        json.dumps(citation_index, ensure_ascii=False),
    )

    client = ConsoleClient(BASE_URL)
    client.login(admin["DIFY_ADMIN_EMAIL"], admin["DIFY_ADMIN_PASSWORD"])
    existing = _find_app(client, APP_NAME)

    import_payload: dict[str, Any] = {
        "mode": "yaml-content",
        "yaml_content": runtime_dsl,
        "name": APP_NAME,
        "description": "基于阿峰课程方法库的课程证据检索与忠实复现助手",
        "icon_type": "emoji",
        "icon": "📚",
        "icon_background": "#E8F5E9",
    }
    if existing:
        import_payload["app_id"] = existing["id"]

    imported = client.request("POST", "/console/api/apps/imports", import_payload)
    if imported.get("status") == "pending":
        import_id = str(imported.get("id") or imported.get("import_id") or "")
        if not import_id:
            raise RuntimeError("Dify returned pending import without import_id")
        imported = client.request("POST", f"/console/api/apps/imports/{import_id}/confirm", {})
    if imported.get("status") not in {"completed", "completed-with-warnings"}:
        raise RuntimeError(f"Afeng DSL import did not complete: {imported.get('status')}: {imported.get('error')}")

    app_id = str(imported.get("app_id") or (existing or {}).get("id") or "")
    if not app_id:
        app = _find_app(client, APP_NAME)
        app_id = str((app or {}).get("id") or "")
    if not app_id:
        raise RuntimeError("Afeng app was imported but could not be found")

    client.request(
        "POST",
        f"/console/api/apps/{app_id}/workflows/publish",
        {"marked_name": "TASK-017", "marked_comment": "DeepSeek + formal v1 Dataset + controlled citation index"},
    )

    smoke_query = "C019 的 ASD 突破方法核心逻辑是什么？"
    raw = client.request(
        "POST",
        f"/console/api/apps/{app_id}/advanced-chat/workflows/draft/run",
        {"inputs": {}, "query": smoke_query, "files": []},
        raw=True,
        timeout=180,
    )
    answer, errors = _parse_sse_answer(raw)
    parsed: dict[str, Any] | None = None
    if answer:
        try:
            parsed = json.loads(answer)
        except json.JSONDecodeError:
            parsed = None

    result = {
        "schema_version": "1.0",
        "test_type": "afeng-app-smoke",
        "query": smoke_query,
        "deployed": True,
        "published": True,
        "answer_received": bool(answer),
        "valid_json": parsed is not None,
        "answer": parsed if parsed is not None else answer,
        "errors": errors,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    SMOKE_OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "deployed": result["deployed"],
                "published": result["published"],
                "answer_received": result["answer_received"],
                "valid_json": result["valid_json"],
                "error_count": len(errors),
                "smoke_output": str(SMOKE_OUTPUT_PATH),
            },
            ensure_ascii=False,
        )
    )
    return 0 if answer and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
