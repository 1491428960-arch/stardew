"""两套脱敏的**语义键覆盖**与各自的结构差异。

项目里有两套脱敏，服务不同数据流：

- `behavior_quality.sanitize_quality_artifact`：脱敏**写盘的评测工件**（`artifacts/`）。
- `prompts._sanitize_value`：脱敏**送进 Prompt 的内容**。

它们曾**各漏一边**——behavior_quality 不认 `password`/`secret`（会把它们原样写进工件），
prompts 不认 `cookie`/`payload`/`prompt`/`bearer`（会把它们原样带进 Prompt）。
2026-09-20 已给两套集合**补齐**，使它们覆盖同一组语义键。

两者的**键归一化方向相反**、命中后的处理也不同（一个把值换成说明并保留键，一个丢弃整个键），
这些结构性差异仍在——但下面的断言按**关系**写而不是写死内容，
这样将来**再加敏感键（加固安全）不会被测试挡住**。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.behavior_quality import (
    _SENSITIVE_KEYS as behavior_sensitive_keys,
    _sanitize_text as behavior_redact,
    sanitize_quality_artifact,
)
from stardew_ai_bridge.prompts import (
    _SENSITIVE_KEYS as prompt_sensitive_keys,
    _remove_secret_labels as prompt_redact,
    _sanitize_value as prompt_sanitize,
)

# 这些是必须被两套都处理的键（写死的是**要求**，不是实现的字面内容）。
_CRITICAL_KEYS = (
    "apikey",
    "token",
    "cookie",
    "authorization",
    "bearer",
    "prompt",
    "payload",
    "password",
    "secret",
)


def _normalise(key: str) -> str:
    """抹平两套集合在 `_` / `-` 写法上的差异（`api_key` 与 `api-key` 等价）。"""

    return key.casefold().replace("_", "").replace("-", "")


def test_the_two_key_sets_cover_the_same_semantic_keys() -> None:
    prompt_keys = {_normalise(key) for key in prompt_sensitive_keys}
    behavior_keys = {_normalise(key) for key in behavior_sensitive_keys}

    assert prompt_keys == behavior_keys
    # 断言“至少覆盖这些”而不是“恰好等于这些”——以后加键是加固，不该失败。
    assert prompt_keys >= {_normalise(key) for key in _CRITICAL_KEYS}


@pytest.mark.parametrize(
    "key",
    ["password", "secret", "cookie", "payload", "prompt", "bearer", "token", "authorization"],
)
def test_both_sanitisers_handle_every_critical_key(key: str) -> None:
    # 正向断言：同一个字段无论在“写盘”还是“进 Prompt”这条路上都必须被处理掉。
    assert prompt_sanitize({key: "x"}) == {key: "[已省略]"}  # 保留键、把值换成说明
    assert sanitize_quality_artifact({key: "x"}) == {}  # 直接丢弃整个键


@pytest.mark.parametrize("key", ["api_key", "API-KEY", "apiKey"])
def test_api_key_spellings_are_caught_by_both(key: str) -> None:
    assert prompt_sanitize({key: "x"}) == {key: "[已省略]"}
    assert sanitize_quality_artifact({key: "x"}) == {}


# --- 仍然存在、但只是“写法与处理方式”的差异 --------------------------------


def test_key_normalisation_goes_in_opposite_directions() -> None:
    # 这是两套实现的结构差异：prompts 把 `_` 换成 `-`，behavior_quality 反过来。
    # 因此 API key 的字面写法不同——但如上所证，两者能识别对方那种写法。
    assert "api-key" in prompt_sensitive_keys
    assert "api_key" not in prompt_sensitive_keys
    assert "api_key" in behavior_sensitive_keys
    assert "api-key" not in behavior_sensitive_keys


def test_tuples_are_preserved_by_prompts_but_flattened_to_lists_by_behavior_quality() -> None:
    assert prompt_sanitize(("a", "b")) == ("a", "b")
    assert sanitize_quality_artifact(("a", "b")) == ["a", "b"]


def test_text_redaction_uses_different_placeholders() -> None:
    assert prompt_redact("token: abc") == "token: [已省略]"
    assert behavior_redact("token=abc") == "token=[REDACTED]"
