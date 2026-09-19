"""Vertex AI / ADC 认证适配的离线回归。

本文件不发起任何真实网络请求：token 端点与 Vertex 端点都通过 httpx.MockTransport
注入假响应，且断言任何失败路径都不会把凭据写进错误消息或结果对象。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from stardew_ai_bridge.config import (
    BridgeSettings,
    ProviderSettings,
    build_vertex_url,
    load_local_env,
)
from stardew_ai_bridge.models import DialogueTestRequest
from stardew_ai_bridge.providers import (
    OpenAICompatibleProvider,
    ProviderError,
    ProviderRouter,
    VertexOpenAICompatibleProvider,
)
from stardew_ai_bridge.vertex_auth import (
    AdcAccessTokenSource,
    VertexAuthError,
    vertex_credentials_path,
)


REQUEST = DialogueTestRequest(npcId="Rasmodia", message="你好")

REFRESH_TOKEN = "demo-refresh-token"
CLIENT_SECRET = "demo-client-secret"

ADC_PAYLOAD = {
    "type": "authorized_user",
    "client_id": "demo-client-id.apps.googleusercontent.com",
    "client_secret": CLIENT_SECRET,
    "refresh_token": REFRESH_TOKEN,
}


def _write_adc(path: Path, payload: dict[str, object] | None = None) -> Path:
    path.write_text(
        json.dumps(ADC_PAYLOAD if payload is None else payload),
        encoding="utf-8",
    )
    return path


def _token_response(token: str = "adc-access-token", expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(
        200,
        json={"access_token": token, "expires_in": expires_in, "token_type": "Bearer"},
    )


def _sse_response(text: str = "顶点回复") -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=(
            'data: {"choices":[{"delta":{"content":"' + text + '"}}]}\n\n'
            'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":7,'
            '"completion_tokens":3,"total_tokens":10}}\n\n'
            "data: [DONE]\n\n"
        ).encode("utf-8"),
    )


class StubTokenSource:
    def __init__(self, token: str = "adc-access-token", error: Exception | None = None):
        self.token = token
        self.error = error
        self.calls = 0

    def access_token(self) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.token


# --- ADC access token 来源 -------------------------------------------------


def test_adc_token_source_refreshes_once_and_reuses_cached_token(tmp_path: Path) -> None:
    credentials = _write_adc(tmp_path / "adc.json")
    posted: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(dict(httpx.QueryParams(request.content.decode("utf-8"))))
        return _token_response()

    source = AdcAccessTokenSource(
        credentials_path=credentials,
        transport=httpx.MockTransport(handler),
    )

    assert source.access_token() == "adc-access-token"
    assert source.access_token() == "adc-access-token"

    assert len(posted) == 1
    assert posted[0]["grant_type"] == "refresh_token"
    assert posted[0]["refresh_token"] == REFRESH_TOKEN
    assert posted[0]["client_id"] == ADC_PAYLOAD["client_id"]


def test_adc_token_source_refreshes_again_after_expiry(tmp_path: Path) -> None:
    credentials = _write_adc(tmp_path / "adc.json")
    tokens = iter(("first-token", "second-token"))

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return _token_response(token=next(tokens), expires_in=1)

    source = AdcAccessTokenSource(
        credentials_path=credentials,
        transport=httpx.MockTransport(handler),
    )

    assert source.access_token() == "first-token"
    # expires_in 已进入预留 skew，缓存立刻失效。
    assert source.access_token() == "second-token"


def test_adc_token_source_reports_missing_credentials(tmp_path: Path) -> None:
    source = AdcAccessTokenSource(credentials_path=tmp_path / "missing.json")

    with pytest.raises(VertexAuthError, match="not configured"):
        source.access_token()


def test_adc_token_source_rejects_unsupported_credential_type_without_leaking(
    tmp_path: Path,
) -> None:
    credentials = _write_adc(
        tmp_path / "service-account.json",
        {"type": "service_account", "private_key": "demo-private-key"},
    )
    source = AdcAccessTokenSource(credentials_path=credentials)

    with pytest.raises(VertexAuthError, match="not supported") as excinfo:
        source.access_token()

    assert "demo-private-key" not in str(excinfo.value)


def test_adc_token_source_reports_refresh_failure_without_leaking_body(
    tmp_path: Path,
) -> None:
    credentials = _write_adc(tmp_path / "adc.json")

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": f"Token {REFRESH_TOKEN} has been revoked.",
            },
        )

    source = AdcAccessTokenSource(
        credentials_path=credentials,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(VertexAuthError, match="refresh failed") as excinfo:
        source.access_token()

    message = str(excinfo.value)
    assert REFRESH_TOKEN not in message
    assert CLIENT_SECRET not in message
    assert "invalid_grant" not in message


def test_adc_token_source_reports_transport_failure_without_leaking(
    tmp_path: Path,
) -> None:
    credentials = _write_adc(tmp_path / "adc.json")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    source = AdcAccessTokenSource(
        credentials_path=credentials,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(VertexAuthError, match="refresh failed") as excinfo:
        source.access_token()

    assert REFRESH_TOKEN not in str(excinfo.value)


def test_adc_token_source_repr_hides_cached_token(tmp_path: Path) -> None:
    credentials = _write_adc(tmp_path / "adc.json")

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return _token_response(token="super-secret-token")

    source = AdcAccessTokenSource(
        credentials_path=credentials,
        transport=httpx.MockTransport(handler),
    )
    source.access_token()

    assert "super-secret-token" not in repr(source)


# --- 凭据路径解析 -----------------------------------------------------------


def test_vertex_credentials_path_prefers_explicit_bridge_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("BRIDGE_CLOUD_VERTEX_CREDENTIALS", str(tmp_path / "explicit.json"))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "adc.json"))

    assert vertex_credentials_path() == tmp_path / "explicit.json"


def test_vertex_credentials_path_uses_adc_under_cloudsdk_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("BRIDGE_CLOUD_VERTEX_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path))

    assert (
        vertex_credentials_path()
        == tmp_path / "application_default_credentials.json"
    )


# --- Vertex Provider -------------------------------------------------------


def test_vertex_url_targets_openapi_chat_completions_endpoint() -> None:
    assert build_vertex_url(project="demo-project", location="global") == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project"
        "/locations/global/endpoints/openapi/chat/completions"
    )
    assert build_vertex_url(project="demo-project", location="asia-northeast1") == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project"
        "/locations/asia-northeast1/endpoints/openapi/chat/completions"
    )


def test_vertex_provider_uses_adc_bearer_token_without_leaking_it() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        received["authorization"] = request.headers.get("authorization")
        received["body"] = request.content
        return _sse_response()

    token_source = StubTokenSource(token="adc-access-token")
    provider = VertexOpenAICompatibleProvider(
        ProviderSettings(
            name="vertex",
            url=build_vertex_url(project="demo-project", location="global"),
            model="gemini-3.7-flash",
            timeout=2.0,
        ),
        token_source=token_source,
        transport=httpx.MockTransport(handler),
    )

    result = provider.generate(REQUEST)

    assert result.reply == "顶点回复"
    assert result.provider == "vertex"
    assert result.fallback is False
    assert result.usage is not None and result.usage.total_tokens == 10
    assert received["authorization"] == "Bearer adc-access-token"
    assert "demo-project" in str(received["url"])
    assert token_source.calls == 1
    assert "adc-access-token" not in repr(result)


def test_vertex_provider_is_an_openai_compatible_provider() -> None:
    provider = VertexOpenAICompatibleProvider(
        ProviderSettings(
            name="vertex",
            url=build_vertex_url(project="demo-project", location="global"),
            model="gemini-3.7-flash",
        ),
        token_source=StubTokenSource(),
    )

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "vertex"


def test_vertex_provider_surfaces_auth_failure_as_provider_error() -> None:
    provider = VertexOpenAICompatibleProvider(
        ProviderSettings(
            name="vertex",
            url=build_vertex_url(project="demo-project", location="global"),
            model="gemini-3.7-flash",
        ),
        token_source=StubTokenSource(
            error=VertexAuthError("vertex credentials are not configured")
        ),
    )

    with pytest.raises(ProviderError, match="not configured"):
        provider.generate(REQUEST)


def test_vertex_provider_reports_http_401_without_leaking_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            401,
            json={
                "error": {
                    "code": 401,
                    "message": "Request had invalid authentication credentials.",
                }
            },
        )

    provider = VertexOpenAICompatibleProvider(
        ProviderSettings(
            name="vertex",
            url=build_vertex_url(project="demo-project", location="global"),
            model="gemini-3.7-flash",
            timeout=2.0,
        ),
        token_source=StubTokenSource(token="adc-access-token"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError, match="HTTP 401") as excinfo:
        provider.generate(REQUEST)

    assert "adc-access-token" not in str(excinfo.value)


def test_vertex_provider_rejects_non_https_endpoint() -> None:
    provider = VertexOpenAICompatibleProvider(
        ProviderSettings(
            name="vertex",
            url="http://aiplatform.googleapis.com/v1/projects/demo/locations/global"
            "/endpoints/openapi/chat/completions",
            model="gemini-3.7-flash",
        ),
        token_source=StubTokenSource(),
    )

    with pytest.raises(ProviderError, match="https"):
        provider.generate(REQUEST)


# --- Router 接线 -----------------------------------------------------------


def test_router_builds_vertex_provider_from_api_mode() -> None:
    settings = BridgeSettings(
        cloud=ProviderSettings(
            name="vertex",
            url=build_vertex_url(project="demo-project", location="global"),
            model="gemini-3.7-flash",
            api_mode="vertex",
            enabled=True,
        ),
        cloud_enabled=True,
    )

    router = ProviderRouter.from_settings(settings)

    assert isinstance(router.cloud_provider, VertexOpenAICompatibleProvider)


def test_vertex_router_falls_back_without_leaking_credentials() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return _sse_response()

    provider = VertexOpenAICompatibleProvider(
        ProviderSettings(
            name="vertex",
            url=build_vertex_url(project="demo-project", location="global"),
            model="gemini-3.7-flash",
            timeout=2.0,
        ),
        token_source=StubTokenSource(
            error=VertexAuthError("vertex credentials are not configured")
        ),
        transport=httpx.MockTransport(handler),
    )
    router = ProviderRouter(
        cloud_provider=provider,
        cloud_enabled=True,
        cloud_only=True,
    )

    result = router.generate(REQUEST, "cloud")

    assert result.fallback is True
    assert result.warnings == ["vertex provider failed"]
    assert "credentials" not in result.reply


# --- 配置接线 ---------------------------------------------------------------


def test_vertex_settings_derive_url_from_project_and_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BRIDGE_CLOUD_URL", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_BASE_URL", raising=False)
    monkeypatch.setenv("BRIDGE_CLOUD_API_MODE", "vertex")
    monkeypatch.setenv("BRIDGE_CLOUD_VERTEX_PROJECT", "demo-project")
    monkeypatch.setenv("BRIDGE_CLOUD_VERTEX_LOCATION", "global")

    settings = BridgeSettings.from_env()

    assert settings.cloud.api_mode == "vertex"
    assert settings.cloud.url == build_vertex_url(
        project="demo-project", location="global"
    )


def test_vertex_settings_default_location_is_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BRIDGE_CLOUD_URL", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_BASE_URL", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_VERTEX_LOCATION", raising=False)
    monkeypatch.setenv("BRIDGE_CLOUD_API_MODE", "vertex")
    monkeypatch.setenv("BRIDGE_CLOUD_VERTEX_PROJECT", "demo-project")

    settings = BridgeSettings.from_env()

    assert settings.cloud.url == build_vertex_url(
        project="demo-project", location="global"
    )


def test_vertex_settings_keep_explicit_url_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRIDGE_CLOUD_API_MODE", "vertex")
    monkeypatch.setenv("BRIDGE_CLOUD_VERTEX_PROJECT", "demo-project")
    monkeypatch.setenv(
        "BRIDGE_CLOUD_URL", "https://gateway.invalid/v1/chat/completions"
    )

    settings = BridgeSettings.from_env()

    assert settings.cloud.url == "https://gateway.invalid/v1/chat/completions"


def test_vertex_settings_without_project_stay_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BRIDGE_CLOUD_URL", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_BASE_URL", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_VERTEX_PROJECT", raising=False)
    monkeypatch.setenv("BRIDGE_CLOUD_API_MODE", "vertex")

    settings = BridgeSettings.from_env()

    assert settings.cloud.url is None
    assert ProviderRouter.from_settings(settings).cloud_provider is None


def test_local_env_loads_vertex_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "BRIDGE_CLOUD_API_MODE",
        "BRIDGE_CLOUD_VERTEX_PROJECT",
        "BRIDGE_CLOUD_VERTEX_LOCATION",
        "BRIDGE_CLOUD_VERTEX_CREDENTIALS",
    ):
        monkeypatch.delenv(name, raising=False)
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            (
                "BRIDGE_CLOUD_API_MODE=vertex",
                "BRIDGE_CLOUD_VERTEX_PROJECT=demo-project",
                "BRIDGE_CLOUD_VERTEX_LOCATION=asia-northeast1",
                "BRIDGE_CLOUD_VERTEX_CREDENTIALS=C:/creds/adc.json",
            )
        ),
        encoding="utf-8",
    )

    load_local_env(env_path)

    assert os.getenv("BRIDGE_CLOUD_API_MODE") == "vertex"
    assert os.getenv("BRIDGE_CLOUD_VERTEX_PROJECT") == "demo-project"
    assert os.getenv("BRIDGE_CLOUD_VERTEX_LOCATION") == "asia-northeast1"
    assert os.getenv("BRIDGE_CLOUD_VERTEX_CREDENTIALS") == "C:/creds/adc.json"
