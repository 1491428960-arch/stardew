"""`vertex_auth` 的路径解析、凭据校验、刷新与缓存。

2026-09-20 用覆盖率定位到 `vertex_auth.py` 92%、7 行未覆盖。它的模块 docstring 有一条
明确的安全承诺：**不会把 refresh token、client secret 或 access token 写进日志、
异常消息或数据类 `repr`**——这条承诺值得用测试钉住。

覆盖四层：

- **路径解析的优先级**（显式环境变量 → `CLOUDSDK_CONFIG` → `APPDATA` → `~/.config`）；
- **凭据文件的四种拒绝理由**（不存在／不可读／类型不支持／字段不全）；
- **刷新端点的六种失败**与 `expires_in` 的宽松回退；
- **缓存**：未过期不再请求，`expiry_skew_seconds` 能把缓存提前作废。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from stardew_ai_bridge.vertex_auth import (
    DEFAULT_EXPIRES_IN_SECONDS,
    DEFAULT_TOKEN_ENDPOINT,
    AccessTokenSource,
    AdcAccessTokenSource,
    VertexAuthError,
    vertex_credentials_path,
)

_ADC = {
    "type": "authorized_user",
    "client_id": "client-id.apps.googleusercontent.com",
    "client_secret": "super-secret-value",
    "refresh_token": "refresh-token-value",
}


def _write_adc(tmp_path: Path, payload: object = None) -> Path:
    path = tmp_path / "application_default_credentials.json"
    path.write_text(
        json.dumps(_ADC if payload is None else payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _source(path: Path, handler=None, **kwargs: object) -> AdcAccessTokenSource:  # type: ignore[no-untyped-def]
    transport = httpx.MockTransport(handler) if handler is not None else None
    return AdcAccessTokenSource(credentials_path=path, transport=transport, **kwargs)  # type: ignore[arg-type]


def _ok_handler(token: str = "access-token-value", expires_in: object = 3600):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": token, "expires_in": expires_in})

    return handler


# --- 路径解析的优先级 -------------------------------------------------------


def test_explicit_env_vars_win_over_the_rest(tmp_path: Path) -> None:
    env = {
        "BRIDGE_CLOUD_VERTEX_CREDENTIALS": str(tmp_path / "explicit.json"),
        "GOOGLE_APPLICATION_CREDENTIALS": str(tmp_path / "google.json"),
        "CLOUDSDK_CONFIG": str(tmp_path / "cloudsdk"),
        "APPDATA": str(tmp_path / "appdata"),
    }

    assert vertex_credentials_path(env) == tmp_path / "explicit.json"


def test_google_application_credentials_is_the_second_choice(tmp_path: Path) -> None:
    env = {
        "GOOGLE_APPLICATION_CREDENTIALS": str(tmp_path / "google.json"),
        "CLOUDSDK_CONFIG": str(tmp_path / "cloudsdk"),
    }

    assert vertex_credentials_path(env) == tmp_path / "google.json"


def test_cloudsdk_config_dir_is_used_when_no_explicit_file(tmp_path: Path) -> None:
    path = vertex_credentials_path({"CLOUDSDK_CONFIG": str(tmp_path / "cloudsdk")})

    assert path == tmp_path / "cloudsdk" / "application_default_credentials.json"


def test_appdata_falls_back_to_the_gcloud_subdirectory(tmp_path: Path) -> None:
    path = vertex_credentials_path({"APPDATA": str(tmp_path / "appdata")})

    assert path == tmp_path / "appdata" / "gcloud" / "application_default_credentials.json"


def test_a_final_fallback_goes_to_the_home_directory(tmp_path: Path) -> None:
    path = vertex_credentials_path({})

    assert path == Path.home() / ".config" / "gcloud" / "application_default_credentials.json"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_env_values_are_skipped(blank: str, tmp_path: Path) -> None:
    env = {"BRIDGE_CLOUD_VERTEX_CREDENTIALS": blank, "APPDATA": str(tmp_path / "appdata")}

    assert vertex_credentials_path(env) == (
        tmp_path / "appdata" / "gcloud" / "application_default_credentials.json"
    )


# --- 凭据文件的四种拒绝理由 -------------------------------------------------


def test_a_missing_credentials_file_is_reported_as_not_configured(tmp_path: Path) -> None:
    source = _source(tmp_path / "nope.json")

    with pytest.raises(VertexAuthError, match="not configured"):
        source.access_token()


def test_unreadable_json_is_reported_as_not_readable(tmp_path: Path) -> None:
    path = tmp_path / "application_default_credentials.json"
    path.write_text("{不是 JSON", encoding="utf-8")

    with pytest.raises(VertexAuthError, match="not readable"):
        _source(path).access_token()


def test_an_unsupported_credential_type_is_rejected(tmp_path: Path) -> None:
    path = _write_adc(tmp_path, {**_ADC, "type": "service_account"})

    with pytest.raises(VertexAuthError, match="not supported"):
        _source(path).access_token()


@pytest.mark.parametrize("missing", ["client_id", "client_secret", "refresh_token"])
def test_incomplete_credentials_are_rejected(tmp_path: Path, missing: str) -> None:
    payload = {key: value for key, value in _ADC.items() if key != missing}
    path = _write_adc(tmp_path, payload)

    with pytest.raises(VertexAuthError, match="incomplete"):
        _source(path).access_token()


def test_blank_credential_fields_are_rejected(tmp_path: Path) -> None:
    path = _write_adc(tmp_path, {**_ADC, "refresh_token": "   "})

    with pytest.raises(VertexAuthError, match="incomplete"):
        _source(path).access_token()


# --- 刷新端点的失败与回退 ---------------------------------------------------


def test_a_successful_refresh_returns_the_token(tmp_path: Path) -> None:
    source = _source(_write_adc(tmp_path), handler=_ok_handler("tok-123"))

    assert source.access_token() == "tok-123"


def test_a_transport_error_becomes_a_vertex_auth_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(VertexAuthError, match="refresh failed"):
        _source(_write_adc(tmp_path), handler=handler).access_token()


@pytest.mark.parametrize("status", [400, 401, 500])
def test_an_error_status_becomes_a_vertex_auth_error(tmp_path: Path, status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "invalid_grant"})

    with pytest.raises(VertexAuthError, match="refresh failed"):
        _source(_write_adc(tmp_path), handler=handler).access_token()


def test_a_non_json_refresh_body_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>nope</html>")

    with pytest.raises(VertexAuthError, match="refresh failed"):
        _source(_write_adc(tmp_path), handler=handler).access_token()


def test_a_missing_access_token_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"expires_in": 3600})

    with pytest.raises(VertexAuthError, match="refresh failed"):
        _source(_write_adc(tmp_path), handler=handler).access_token()


def test_a_non_string_access_token_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": 12345})

    with pytest.raises(VertexAuthError, match="refresh failed"):
        _source(_write_adc(tmp_path), handler=handler).access_token()


def test_the_token_is_sent_as_a_refresh_grant(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 60})

    _source(_write_adc(tmp_path), handler=handler).access_token()

    assert seen["url"] == DEFAULT_TOKEN_ENDPOINT
    assert "grant_type=refresh_token" in seen["body"]
    assert "refresh_token=refresh-token-value" in seen["body"]


# --- expires_in 的宽松回退 --------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, "3600", True, None])
def test_a_bad_expires_in_falls_back_to_the_default(tmp_path: Path, bad: object) -> None:
    # expires_in 只影响缓存时长，取值不可信时用默认值而不是报错。
    source = _source(_write_adc(tmp_path), handler=_ok_handler("tok", bad))

    assert source.access_token() == "tok"


def test_the_default_expiry_is_an_hour() -> None:
    assert DEFAULT_EXPIRES_IN_SECONDS == 3600.0


# --- 缓存 -------------------------------------------------------------------


def test_a_cached_token_is_reused_without_another_request(tmp_path: Path) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})

    source = _source(_write_adc(tmp_path), handler=handler)

    assert source.access_token() == "tok"
    assert source.access_token() == "tok"
    assert calls["count"] == 1


def test_the_skew_window_can_expire_the_cache_immediately(tmp_path: Path) -> None:
    # 把 skew 设得比 expires_in 还大 → 缓存立刻视为已过期，于是每次都刷新。
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 60})

    source = _source(_write_adc(tmp_path), handler=handler, expiry_skew_seconds=9999)

    source.access_token()
    source.access_token()

    assert calls["count"] == 2


# --- 安全承诺 ---------------------------------------------------------------


def test_repr_never_exposes_credentials_or_tokens(tmp_path: Path) -> None:
    # 模块 docstring 的承诺：token 与 secret 不进 repr。
    source = _source(_write_adc(tmp_path), handler=_ok_handler("access-token-value"))
    source.access_token()

    rendered = repr(source)

    assert "access-token-value" not in rendered
    assert "super-secret-value" not in rendered
    assert "refresh-token-value" not in rendered


def test_error_messages_never_expose_credentials(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(VertexAuthError) as excinfo:
        _source(_write_adc(tmp_path), handler=handler).access_token()

    message = str(excinfo.value)
    assert "super-secret-value" not in message
    assert "refresh-token-value" not in message
    # 原始异常里可能带着请求体，所以文案必须是固定的那句
    assert message == "vertex credential refresh failed"


def test_the_source_satisfies_the_protocol(tmp_path: Path) -> None:
    assert isinstance(_source(tmp_path / "x.json"), AccessTokenSource)


def test_a_json_array_refresh_body_is_rejected(tmp_path: Path) -> None:
    # 合法 JSON 但**不是对象**（例如上游回了数组）也要拒。
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    with pytest.raises(VertexAuthError, match="refresh failed"):
        _source(_write_adc(tmp_path), handler=handler).access_token()


def test_the_env_based_path_is_used_when_none_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 不显式传 credentials_path 时，走 vertex_credentials_path() 读环境变量。
    monkeypatch.setenv("BRIDGE_CLOUD_VERTEX_CREDENTIALS", str(_write_adc(tmp_path)))
    source = AdcAccessTokenSource(transport=httpx.MockTransport(_ok_handler("tok-env")))

    assert source.access_token() == "tok-env"
