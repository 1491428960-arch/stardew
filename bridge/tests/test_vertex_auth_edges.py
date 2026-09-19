"""Vertex 凭据路径解析与 ADC 加载的边界分支。

这些分支此前没有覆盖，而它们都是**安全相关**的：路径回退顺序决定用哪份凭据，
加载错误必须给出不含凭据内容的 `VertexAuthError`。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.vertex_auth import (
    AdcAccessTokenSource,
    VertexAuthError,
    vertex_credentials_path,
)


def test_credentials_path_prefers_the_explicit_environment_variables() -> None:
    # 显式变量优先，且首尾空白会被去掉。
    assert vertex_credentials_path(
        {"BRIDGE_CLOUD_VERTEX_CREDENTIALS": "  C:/explicit.json  "}
    ) == Path("C:/explicit.json")
    # 第一个为空时轮到 GOOGLE_APPLICATION_CREDENTIALS。
    assert vertex_credentials_path(
        {
            "BRIDGE_CLOUD_VERTEX_CREDENTIALS": "   ",
            "GOOGLE_APPLICATION_CREDENTIALS": "C:/google.json",
        }
    ) == Path("C:/google.json")


def test_credentials_path_falls_back_to_cloudsdk_then_appdata() -> None:
    from_cloudsdk = vertex_credentials_path({"CLOUDSDK_CONFIG": "C:/gcloud"})
    assert from_cloudsdk.parent == Path("C:/gcloud")
    assert from_cloudsdk.name.endswith(".json")

    from_appdata = vertex_credentials_path({"APPDATA": "C:/Users/x/AppData/Roaming"})
    assert "gcloud" in from_appdata.parts
    assert from_appdata.name.endswith(".json")


def test_credentials_path_last_resort_is_the_user_config_directory() -> None:
    # 传空映射（而不是 None）可以强制走最后一档，且不受本机环境变量影响。
    fallback = vertex_credentials_path({})

    assert fallback == Path.home() / ".config" / "gcloud" / fallback.name
    assert fallback.name.endswith(".json")


def test_load_credentials_reports_a_missing_file(tmp_path: Path) -> None:
    source = AdcAccessTokenSource(credentials_path=tmp_path / "missing.json")

    with pytest.raises(VertexAuthError, match="not configured"):
        source._load_credentials()


def test_load_credentials_reports_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "adc.json"
    path.write_text("{ 这不是 JSON", encoding="utf-8")
    source = AdcAccessTokenSource(credentials_path=path)

    with pytest.raises(VertexAuthError, match="not readable"):
        source._load_credentials()


def test_load_credentials_rejects_unsupported_credential_types(tmp_path: Path) -> None:
    path = tmp_path / "adc.json"
    # service_account 不受支持：只接受 authorized_user。
    path.write_text(json.dumps({"type": "service_account"}), encoding="utf-8")

    with pytest.raises(VertexAuthError, match="not supported"):
        AdcAccessTokenSource(credentials_path=path)._load_credentials()
