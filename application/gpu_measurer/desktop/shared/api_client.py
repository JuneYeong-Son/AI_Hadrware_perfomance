"""Thin HTTP client for the GPU-Perf backend.

Uses only the standard library (urllib) so the desktop app gains no new
dependency. All methods raise ``ApiError`` on failure with a Korean, user-facing
message and (when available) the HTTP status code.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = os.environ.get("GPUPERF_API_URL", "http://127.0.0.1:8000")


class ApiError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _extract_detail(error: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(error.read().decode("utf-8"))
        detail = body.get("detail")
        if isinstance(detail, list) and detail:  # pydantic validation errors
            first = detail[0]
            return str(first.get("msg", first))
        if detail:
            return str(detail)
    except Exception:
        pass
    return f"요청이 실패했어요 (HTTP {error.code})."


class ApiClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raise ApiError(_extract_detail(error), status=error.code) from None
        except urllib.error.URLError as error:
            raise ApiError(
                f"서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인하세요.\n({self.base_url})",
                status=None,
            ) from error

    # --- Auth ---------------------------------------------------------------
    def signup(self, email: str, password: str, display_name: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/auth/signup",
            body={"email": email, "password": password, "display_name": display_name},
        )

    def login(self, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST", "/api/auth/login", body={"email": email, "password": password}
        )

    def logout(self, token: str) -> dict[str, Any]:
        return self._request("POST", "/api/auth/logout", token=token)

    def me(self, token: str) -> dict[str, Any]:
        return self._request("GET", "/api/auth/me", token=token)

    # --- Devices & measurements --------------------------------------------
    def register_device(
        self, token: str, fingerprint: str, gpu_name: str = "", label: str = ""
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/devices/register",
            token=token,
            body={"fingerprint": fingerprint, "gpu_name": gpu_name, "label": label},
        )

    def submit_measurement(
        self, token: str, submission: dict[str, Any]
    ) -> dict[str, Any]:
        # Drop keys the caller left as None so backend defaults apply cleanly.
        body = {k: v for k, v in submission.items() if v is not None}
        return self._request("POST", "/api/measurements", token=token, body=body)
