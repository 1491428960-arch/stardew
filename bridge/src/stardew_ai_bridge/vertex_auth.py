"""Vertex AI 的 ADC 短期 access token 获取。

本模块只在进程内读取本机 ADC 文件并按需刷新 access token；不会把
refresh token、client secret 或 access token 写进日志、异常消息或
数据类 `repr`。所有异常都是 `VertexAuthError`，由 Provider 层转换成
不含凭据的 `ProviderError`。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable
import time

import httpx


DEFAULT_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DEFAULT_EXPIRES_IN_SECONDS = 3600.0
DEFAULT_EXPIRY_SKEW_SECONDS = 60.0
_ADC_FILENAME = "application_default_credentials.json"


class VertexAuthError(RuntimeError):
    """Vertex 凭据不可用；消息中不包含任何凭据内容。"""


@runtime_checkable
class AccessTokenSource(Protocol):
    def access_token(self) -> str:
        """返回一个可用的 access token，必要时在内部刷新。"""


def vertex_credentials_path(env: Mapping[str, str] | None = None) -> Path:
    """按固定优先级解析 ADC 文件路径；不读取文件内容。"""

    values = os.environ if env is None else env
    for name in ("BRIDGE_CLOUD_VERTEX_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS"):
        explicit = values.get(name)
        if explicit and explicit.strip():
            return Path(explicit.strip())

    config_dir = values.get("CLOUDSDK_CONFIG")
    if config_dir and config_dir.strip():
        return Path(config_dir.strip()) / _ADC_FILENAME

    appdata = values.get("APPDATA")
    if appdata and appdata.strip():
        return Path(appdata.strip()) / "gcloud" / _ADC_FILENAME

    return Path.home() / ".config" / "gcloud" / _ADC_FILENAME


@dataclass
class AdcAccessTokenSource:
    """从 `authorized_user` 类型的 ADC 刷新 access token，并缓存到过期前。"""

    credentials_path: str | Path | None = None
    timeout: float = 15.0
    transport: httpx.BaseTransport | None = None
    token_endpoint: str = DEFAULT_TOKEN_ENDPOINT
    expiry_skew_seconds: float = DEFAULT_EXPIRY_SKEW_SECONDS
    _cached_token: str | None = field(default=None, repr=False, compare=False)
    _expires_at: float = field(default=0.0, repr=False, compare=False)

    def access_token(self) -> str:
        now = time.monotonic()
        if self._cached_token is not None and now < self._expires_at:
            return self._cached_token

        credentials = self._load_credentials()
        token, expires_in = self._refresh(credentials)
        self._cached_token = token
        self._expires_at = now + max(expires_in - self.expiry_skew_seconds, 0.0)
        return token

    def _resolved_path(self) -> Path:
        if self.credentials_path is not None:
            return Path(self.credentials_path)
        return vertex_credentials_path()

    def _load_credentials(self) -> dict[str, str]:
        path = self._resolved_path()
        if not path.is_file():
            raise VertexAuthError("vertex credentials are not configured")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VertexAuthError("vertex credentials are not readable") from exc
        if not isinstance(payload, Mapping) or payload.get("type") != "authorized_user":
            raise VertexAuthError("vertex credentials type is not supported")

        credentials: dict[str, str] = {}
        for key in ("client_id", "client_secret", "refresh_token"):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise VertexAuthError("vertex credentials are incomplete")
            credentials[key] = value.strip()
        return credentials

    def _refresh(self, credentials: Mapping[str, str]) -> tuple[str, float]:
        data = {"grant_type": "refresh_token", **credentials}
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(self.token_endpoint, data=data)
        except httpx.HTTPError as exc:
            raise VertexAuthError("vertex credential refresh failed") from exc
        if response.is_error:
            raise VertexAuthError("vertex credential refresh failed")
        try:
            payload = response.json()
        except ValueError as exc:
            raise VertexAuthError("vertex credential refresh failed") from exc
        if not isinstance(payload, Mapping):
            raise VertexAuthError("vertex credential refresh failed")

        token = payload.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise VertexAuthError("vertex credential refresh failed")

        expires_in = payload.get("expires_in")
        if (
            isinstance(expires_in, (int, float))
            and not isinstance(expires_in, bool)
            and expires_in > 0
        ):
            seconds = float(expires_in)
        else:
            seconds = DEFAULT_EXPIRES_IN_SECONDS
        return token.strip(), seconds
