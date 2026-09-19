"""`config` 的边界：`.env` 行解析、环境变量取值、Vertex 端点拼装。

原有 2 条测试只覆盖“进程环境变量优先”和“云端默认超时”，而这里每个函数都有容易踩的语义：
超时传 0 或负数会回落默认值、布尔变量写了非法值是 **False 而不是默认值**、
Vertex 模式只在**没有显式 URL** 时才拼端点……配置解析错了会让整个 Bridge 行为不对。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from stardew_ai_bridge.config import (
    ProviderSettings,
    _env_bool,
    _env_float,
    _parse_local_env_value,
    build_vertex_url,
    load_local_env,
)


# --- build_vertex_url -------------------------------------------------------


def test_vertex_url_uses_global_location_by_default() -> None:
    url = build_vertex_url(project="my-project")

    assert url == (
        "https://aiplatform.googleapis.com/v1/projects/my-project"
        "/locations/global/endpoints/openapi/chat/completions"
    )


def test_vertex_url_accepts_an_explicit_location_and_stays_https() -> None:
    url = build_vertex_url(project="p", location="us-central1")

    assert "/locations/us-central1/" in url
    assert url.startswith("https://")


# --- _parse_local_env_value -------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("plain", "plain"),
        ("  spaced  ", "spaced"),
        ('"double"', "double"),
        ("'single'", "single"),
        ("\"mismatch'", "\"mismatch'"),  # 首尾引号不同 → 原样保留
        ('"', '"'),  # 单字符不构成成对引号
        ("", ""),
    ],
)
def test_parse_local_env_value_strips_only_matching_quotes(
    raw: str, expected: str
) -> None:
    assert _parse_local_env_value(raw) == expected


# --- _env_float / _env_bool -------------------------------------------------


def test_env_float_falls_back_for_non_positive_or_unparsable_values(monkeypatch) -> None:
    monkeypatch.setenv("TEST_TIMEOUT", "0")
    assert _env_float("TEST_TIMEOUT", default=10.0) == 10.0
    monkeypatch.setenv("TEST_TIMEOUT", "-3")
    assert _env_float("TEST_TIMEOUT", default=10.0) == 10.0
    monkeypatch.setenv("TEST_TIMEOUT", "not-a-number")
    assert _env_float("TEST_TIMEOUT", default=10.0) == 10.0
    monkeypatch.setenv("TEST_TIMEOUT", "2.5")
    assert _env_float("TEST_TIMEOUT", default=10.0) == 2.5
    monkeypatch.delenv("TEST_TIMEOUT")
    assert _env_float("TEST_TIMEOUT", default=10.0) == 10.0


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "On"])
def test_env_bool_accepts_the_truthy_spellings(monkeypatch, value: str) -> None:
    monkeypatch.setenv("TEST_FLAG", value)

    assert _env_bool("TEST_FLAG", default=False) is True
    assert _env_bool("TEST_FLAG", default=True) is True


def test_env_bool_treats_anything_else_as_false_without_falling_back(monkeypatch) -> None:
    # 关键语义：写了非真值就是 False，**不会**回落到 default。
    monkeypatch.setenv("TEST_FLAG", "maybe")
    assert _env_bool("TEST_FLAG", default=True) is False

    monkeypatch.setenv("TEST_FLAG", "off")
    assert _env_bool("TEST_FLAG", default=True) is False


def test_env_bool_uses_default_only_when_unset_or_blank(monkeypatch) -> None:
    monkeypatch.delenv("TEST_FLAG", raising=False)
    assert _env_bool("TEST_FLAG", default=True) is True

    monkeypatch.setenv("TEST_FLAG", "   ")  # 只有空白 → 视为未设置
    assert _env_bool("TEST_FLAG", default=True) is True


# --- load_local_env ---------------------------------------------------------


def test_load_local_env_skips_comments_blanks_and_unknown_keys(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "# 注释行",
                "",
                "export BRIDGE_CLOUD_ENABLED=true",  # export 前缀
                'BRIDGE_CLOUD_MODEL="quoted-model"',  # 成对引号
                "TOTALLY_UNRELATED_KEY=1",  # 白名单之外
                "这一行没有等号",  # 不匹配赋值正则
            ]
        ),
        encoding="utf-8",
    )
    for key in ("BRIDGE_CLOUD_ENABLED", "BRIDGE_CLOUD_MODEL", "TOTALLY_UNRELATED_KEY"):
        monkeypatch.delenv(key, raising=False)

    load_local_env(env_file)

    assert os.environ["BRIDGE_CLOUD_ENABLED"] == "true"
    assert os.environ["BRIDGE_CLOUD_MODEL"] == "quoted-model"  # 引号被剥掉
    assert "TOTALLY_UNRELATED_KEY" not in os.environ  # 白名单外不加载


def test_load_local_env_is_silent_when_the_file_is_missing(tmp_path: Path) -> None:
    load_local_env(tmp_path / "根本没有这个文件.env")


# --- ProviderSettings.from_env ---------------------------------------------


def test_from_env_prefers_url_over_base_url_and_exposes_it_as_base_url(monkeypatch) -> None:
    monkeypatch.setenv("X_URL", "https://primary")
    monkeypatch.setenv("X_BASE_URL", "https://fallback")

    settings = ProviderSettings.from_env("X", name="x")

    assert settings.url == "https://primary"
    assert settings.base_url == "https://primary"  # base_url 是 url 的别名


def test_from_env_builds_a_vertex_endpoint_only_without_an_explicit_url(monkeypatch) -> None:
    for key in ("X_URL", "X_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("X_API_MODE", "vertex")
    monkeypatch.setenv("X_VERTEX_PROJECT", "proj")

    settings = ProviderSettings.from_env("X", name="x")

    assert settings.api_mode == "vertex"
    assert "projects/proj" in (settings.url or "")
    assert "locations/global" in (settings.url or "")

    # 显式 URL 优先：即便标了 vertex 模式也用它（便于临时指向本地网关排查）
    monkeypatch.setenv("X_URL", "http://127.0.0.1:9999/v1/chat/completions")
    override = ProviderSettings.from_env("X", name="x")

    assert override.url == "http://127.0.0.1:9999/v1/chat/completions"


def test_from_env_leaves_vertex_url_empty_without_a_project(monkeypatch) -> None:
    for key in ("X_URL", "X_BASE_URL", "X_VERTEX_PROJECT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("X_API_MODE", "vertex")

    settings = ProviderSettings.from_env("X", name="x")

    # 没有 project 就拼不出端点，也不该凭空造一个。
    assert settings.url is None
    assert settings.enabled is False


def test_from_env_defaults_enabled_to_whether_a_url_exists(monkeypatch) -> None:
    for key in ("X_URL", "X_BASE_URL", "X_ENABLED", "X_API_MODE", "X_VERTEX_PROJECT"):
        monkeypatch.delenv(key, raising=False)

    assert ProviderSettings.from_env("X", name="x").enabled is False

    monkeypatch.setenv("X_URL", "https://somewhere")
    assert ProviderSettings.from_env("X", name="x").enabled is True


def test_from_env_lowercases_the_api_mode(monkeypatch) -> None:
    monkeypatch.setenv("X_API_MODE", "  VERTEX  ")
    monkeypatch.setenv("X_VERTEX_PROJECT", "proj")
    monkeypatch.delenv("X_URL", raising=False)
    monkeypatch.delenv("X_BASE_URL", raising=False)

    assert ProviderSettings.from_env("X", name="x").api_mode == "vertex"
