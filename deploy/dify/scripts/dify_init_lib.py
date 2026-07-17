"""Idempotent Dify console bootstrap helpers (admin + dataset API key + dataset).

Secrets are written only under DeployRoot/secrets/. Never print secret values.
APIs match Dify 1.15.0 controllers under repo/api/controllers/console and service_api.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import string
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:3080"
DEFAULT_DATASET_NAME = "阿峰课程方法库-研究版"
ADMIN_ENV_NAME = "admin.env"
RUNTIME_ENV_NAME = "dify-runtime.env"
STATUS_NAME = "bootstrap-status.json"


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _gen_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isalpha() for c in pwd) and any(c.isdigit() for c in pwd) and len(pwd) >= 8:
            return pwd


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        out[key.strip()] = value.strip()
    return out


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={values[key]}" for key in values]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _restrict_acl_windows(path: Path) -> None:
    """Allow only the current Windows user to read secrets (best-effort)."""
    if os.name != "nt":
        return
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if not user:
        return
    targets = [path]
    if path.is_file():
        targets.insert(0, path.parent)
    for target in targets:
        # icacls: reset inheritance then grant current user full, remove Everyone/Users.
        subprocess.run(
            ["icacls", str(target), "/inheritance:r"],
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["icacls", str(target), "/grant:r", f"{user}:(F)"],
            check=False,
            capture_output=True,
            text=True,
        )


def _write_public_status(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ConsoleClient:
    """Cookie + CSRF console client for Dify 1.15.0."""

    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf: str | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        auth_bearer: str | None = None,
        expect: set[int] | None = None,
    ) -> tuple[int, Any]:
        url = f"{self.base}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if auth_bearer:
            headers["Authorization"] = f"Bearer {auth_bearer}"
        if method.upper() not in {"GET", "HEAD"} and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with self.opener.open(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
                code = int(resp.getcode() or 0)
                self._capture_csrf()
                parsed: Any
                if body:
                    try:
                        parsed = json.loads(body)
                    except json.JSONDecodeError:
                        parsed = body
                else:
                    parsed = {}
                if expect is not None and code not in expect:
                    raise RuntimeError(f"{method} {path} -> HTTP {code}")
                return code, parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if expect is not None and exc.code in expect:
                try:
                    return exc.code, json.loads(detail) if detail else {}
                except json.JSONDecodeError:
                    return exc.code, detail
            # Never include Authorization; body truncated.
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc

    def _capture_csrf(self) -> None:
        for cookie in self.jar:
            if cookie.name in {"csrf_token", "__Host-csrf_token"} and cookie.value:
                self.csrf = cookie.value


def initialize_admin(
    *,
    deploy_root: Path,
    base_url: str = DEFAULT_BASE,
) -> dict[str, Any]:
    secrets_dir = deploy_root / "secrets"
    admin_path = secrets_dir / ADMIN_ENV_NAME
    status_path = deploy_root / STATUS_NAME
    legacy = _load_env_file(deploy_root / "local-credentials.env")
    existing = {**legacy, **_load_env_file(admin_path)}

    client = ConsoleClient(base_url)
    _, setup = client.request("GET", "/console/api/setup", expect={200})
    if not isinstance(setup, dict):
        raise RuntimeError("setup status response invalid")
    step = str(setup.get("step") or "")

    email = existing.get("DIFY_ADMIN_EMAIL") or "admin@videocaptioner.local"
    name = existing.get("DIFY_ADMIN_NAME") or "VideoCaptioner Admin"
    password = existing.get("DIFY_ADMIN_PASSWORD") or _gen_password()

    if step != "finished":
        client.request(
            "POST",
            "/console/api/setup",
            payload={
                "email": email,
                "name": name,
                "password": password,
                "language": "zh-Hans",
            },
            expect={201},
        )
        _, setup2 = client.request("GET", "/console/api/setup", expect={200})
        if not isinstance(setup2, dict) or setup2.get("step") != "finished":
            raise RuntimeError("admin setup did not finish")
        admin_state = "created"
    else:
        admin_state = "already_finished"

    # Login validates credentials (password Base64 per decrypt_password_field).
    if "DIFY_ADMIN_PASSWORD" not in existing and admin_state == "already_finished":
        # Cannot invent password for an already-initialized instance.
        _write_env_file(
            admin_path,
            {
                "DIFY_ADMIN_EMAIL": email,
                "DIFY_ADMIN_NAME": name,
                # password intentionally omitted when unknown
            },
        )
        _restrict_acl_windows(secrets_dir)
        _restrict_acl_windows(admin_path)
        _write_public_status(
            status_path,
            {
                "admin_setup": "finished",
                "admin_login_verified": False,
                "admin_credentials_path": str(admin_path),
                "note": "setup already finished; password missing — cannot verify login",
            },
        )
        return {
            "admin_setup": "finished",
            "admin_login_verified": False,
            "admin_env": str(admin_path),
        }

    code, login_body = client.request(
        "POST",
        "/console/api/login",
        payload={"email": email, "password": _b64(password), "remember_me": True},
        expect={200, 401, 400},
    )
    if code != 200:
        raise RuntimeError("admin login verification failed")
    if not client.csrf:
        raise RuntimeError("admin login missing CSRF cookie")

    _write_env_file(
        admin_path,
        {
            "DIFY_ADMIN_EMAIL": email,
            "DIFY_ADMIN_NAME": name,
            "DIFY_ADMIN_PASSWORD": password,
        },
    )
    _restrict_acl_windows(secrets_dir)
    _restrict_acl_windows(admin_path)
    _write_public_status(
        status_path,
        {
            "admin_setup": "finished",
            "admin_login_verified": True,
            "admin_credentials_path": str(admin_path),
            "base_url": base_url,
        },
    )
    return {
        "admin_setup": "finished",
        "admin_login_verified": True,
        "admin_env": str(admin_path),
        "login_result_present": isinstance(login_body, dict),
    }


def initialize_dataset(
    *,
    deploy_root: Path,
    base_url: str = DEFAULT_BASE,
    dataset_name: str = DEFAULT_DATASET_NAME,
    indexing_technique: str = "economy",
) -> dict[str, Any]:
    secrets_dir = deploy_root / "secrets"
    admin_path = secrets_dir / ADMIN_ENV_NAME
    runtime_path = secrets_dir / RUNTIME_ENV_NAME
    status_path = deploy_root / STATUS_NAME
    legacy = _load_env_file(deploy_root / "local-credentials.env")
    admin = {**legacy, **_load_env_file(admin_path)}
    runtime = {**legacy, **_load_env_file(runtime_path)}

    email = admin.get("DIFY_ADMIN_EMAIL")
    password = admin.get("DIFY_ADMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError("admin credentials missing; run initialize-admin first")

    client = ConsoleClient(base_url)
    code, _ = client.request(
        "POST",
        "/console/api/login",
        payload={"email": email, "password": _b64(password), "remember_me": True},
        expect={200},
    )
    if code != 200 or not client.csrf:
        raise RuntimeError("admin login failed while preparing dataset")

    api_key = runtime.get("DIFY_API_KEY") or ""
    api_key_created = False
    if not api_key:
        _, key_resp = client.request("POST", "/console/api/datasets/api-keys", expect={200})
        if not isinstance(key_resp, dict):
            raise RuntimeError("dataset API key response invalid")
        api_key = str(key_resp.get("token") or "")
        if not api_key:
            raise RuntimeError("dataset API key token missing")
        api_key_created = True

    dataset_id = runtime.get("DIFY_DATASET_ID") or ""
    dataset_created = False
    dataset_reused = False

    def service_request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
        api_path = path if path.startswith("/v1/") else f"/v1{path}"
        return client.request(
            method,
            api_path,
            payload=payload,
            auth_bearer=api_key,
            expect={200, 201, 400, 404, 409},
        )

    if dataset_id:
        code, detail = service_request("GET", f"/datasets/{dataset_id}")
        if (
            code == 200
            and isinstance(detail, dict)
            and detail.get("id")
            and str(detail.get("name") or "") == dataset_name
        ):
            dataset_reused = True
        else:
            dataset_id = ""

    if not dataset_id:
        # Prefer an existing dataset with the target name.
        query = urllib.parse.urlencode({"page": 1, "limit": 100})
        code, listed = service_request("GET", f"/datasets?{query}")
        if code == 200 and isinstance(listed, dict):
            for item in listed.get("data") or []:
                if isinstance(item, dict) and item.get("name") == dataset_name and item.get("id"):
                    dataset_id = str(item["id"])
                    dataset_reused = True
                    break

    if not dataset_id:
        code, created = service_request(
            "POST",
            "/datasets",
            {
                "name": dataset_name,
                "description": "阿峰课程方法库（研究版，本地 Dify）",
                "indexing_technique": indexing_technique,
                "permission": "only_me",
            },
        )
        if code not in {200, 201} or not isinstance(created, dict) or not created.get("id"):
            # high_quality may fail without embedding; caller may retry economy.
            raise RuntimeError(
                f"create dataset failed HTTP {code} (indexing_technique={indexing_technique})"
            )
        dataset_id = str(created["id"])
        dataset_created = True

    # Confirm readable via service API.
    code, detail = service_request("GET", f"/datasets/{dataset_id}")
    if code != 200 or not isinstance(detail, dict):
        raise RuntimeError("dataset exists but service API GET failed")

    runtime_values = {
        "DIFY_BASE_URL": f"{base_url.rstrip('/')}/v1",
        "DIFY_API_KEY": api_key,
        "DIFY_DATASET_ID": dataset_id,
        "DIFY_DATASET_NAME": dataset_name,
        "DIFY_DATASET_INDEXING": indexing_technique,
    }

    _write_env_file(runtime_path, runtime_values)
    _restrict_acl_windows(secrets_dir)
    _restrict_acl_windows(runtime_path)

    prev = {}
    if status_path.is_file():
        try:
            prev = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    status = {
        **prev,
        "dataset_created": True,
        "dataset_id_present": True,
        "api_key_present": True,
        "dataset_name": dataset_name,
        "dataset_mode": indexing_technique,
        "dataset_reused": dataset_reused,
        "api_key_created_this_run": api_key_created,
        "dataset_created_this_run": dataset_created,
        "runtime_credentials_path": str(runtime_path),
        "base_url": runtime_values["DIFY_BASE_URL"],
    }
    _write_public_status(status_path, status)
    return {
        "dataset_id_present": True,
        "api_key_present": True,
        "dataset_created": dataset_created,
        "dataset_reused": dataset_reused,
        "api_key_created": api_key_created,
        "indexing_technique": indexing_technique,
        "runtime_env": str(runtime_path),
        "dataset_name": dataset_name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dify local init (no secret stdout)")
    parser.add_argument("--deploy-root", type=Path, default=Path(r"D:\Dev\dify-deploy"))
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("admin")
    ds = sub.add_parser("dataset")
    ds.add_argument("--name", default=DEFAULT_DATASET_NAME)
    ds.add_argument("--indexing-technique", default="economy", choices=["economy", "high_quality"])
    args = parser.parse_args(argv)

    try:
        if args.command == "admin":
            result = initialize_admin(deploy_root=args.deploy_root, base_url=args.base_url)
        else:
            try:
                result = initialize_dataset(
                    deploy_root=args.deploy_root,
                    base_url=args.base_url,
                    dataset_name=args.name,
                    indexing_technique=args.indexing_technique,
                )
            except RuntimeError:
                if args.indexing_technique == "high_quality":
                    result = initialize_dataset(
                        deploy_root=args.deploy_root,
                        base_url=args.base_url,
                        dataset_name=args.name,
                        indexing_technique="economy",
                    )
                    result["fallback_to_economy"] = True
                else:
                    raise
        # Public-safe summary only.
        safe = {
            k: v
            for k, v in result.items()
            if k
            not in {
                "password",
                "api_key",
                "token",
                "email",
            }
        }
        print(json.dumps(safe, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"dify_init_failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
