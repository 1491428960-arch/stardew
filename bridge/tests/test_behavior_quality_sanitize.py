"""评测工件的脱敏：`sanitize_quality_artifact` 与 `_sanitize_text`。

这是**安全相关**的路径——它决定写进 `artifacts/` 的评测结果里会不会残留 Key、Cookie
或玩家输入。原有测试只有一条，而规则并不平凡：键名要先 `casefold` 并把 `-` 归一成 `_`
再比对；容器键被**置空但保留键名**；字符串还要再过一遍 `key=[REDACTED]` 的正则替换。
"""

from __future__ import annotations

from stardew_ai_bridge.behavior_quality import (
    _sanitize_text,
    sanitize_quality_artifact,
)


# --- 键层面的过滤 -----------------------------------------------------------


def test_sensitive_keys_are_dropped_regardless_of_spelling() -> None:
    # 三种写法都要命中：驼峰、大写下划线、连字符。
    sanitized = sanitize_quality_artifact(
        {"apiKey": "a", "API-KEY": "b", "api_key": "c", "token": "d", "Cookie": "e"}
    )

    assert sanitized == {}


def test_prompt_and_payload_are_treated_as_sensitive_keys() -> None:
    # 它们可能承载玩家输入，所以在键层面直接丢弃。
    assert sanitize_quality_artifact({"prompt": "玩家说的话", "payload": {"x": 1}}) == {}


def test_container_keys_are_emptied_but_kept() -> None:
    # request/response/config 换成空字典：保留键名（下游脚本按名字取值）但丢掉内容。
    sanitized = sanitize_quality_artifact(
        {
            "request": {"apiKey": "x", "npcId": "Shane"},
            "response": "大段文本",
            "config": [1, 2],
        }
    )

    assert sanitized == {"request": {}, "response": {}, "config": {}}


def test_unrelated_keys_and_scalar_values_survive() -> None:
    sanitized = sanitize_quality_artifact(
        {"npcId": "Shane", "score": 2, "ok": True, "missing": None}
    )

    assert sanitized == {"npcId": "Shane", "score": 2, "ok": True, "missing": None}


# --- 字符串层面的正则替换 ---------------------------------------------------


def test_secret_labels_inside_text_are_redacted() -> None:
    assert _sanitize_text("api_key=sk-123456") == "api_key=[REDACTED]"
    assert _sanitize_text("token: abc") == "token=[REDACTED]"
    # 标签本身按原文保留（只替换值），大小写与连字符写法不动
    assert _sanitize_text("API-KEY = sk-9") == "API-KEY=[REDACTED]"


def test_bearer_prefix_is_swallowed_with_the_token() -> None:
    assert _sanitize_text("Authorization: Bearer abc.def") == "Authorization=[REDACTED]"


def test_plain_text_without_labels_is_untouched() -> None:
    assert _sanitize_text("谢恩今天心情不错。") == "谢恩今天心情不错。"


def test_redaction_stops_at_the_first_whitespace_which_is_a_known_limit() -> None:
    # 已知局限：值里含空格时只脱掉第一段，后面的内容仍会留下。
    # 把它固化成契约——若将来改成“脱到行尾”，这条会失败并提醒更新。
    assert _sanitize_text("prompt: 你好 世界") == "prompt=[REDACTED] 世界"


# --- 递归与类型处理 ---------------------------------------------------------


def test_nested_structures_are_sanitized_recursively() -> None:
    sanitized = sanitize_quality_artifact(
        {"cases": [{"apiKey": "x", "npcId": "Shane", "notes": ["token=abc", "正常"]}]}
    )

    assert sanitized == {
        "cases": [{"npcId": "Shane", "notes": ["token=[REDACTED]", "正常"]}]
    }


def test_tuples_become_lists() -> None:
    # JSON 没有元组，统一成列表。
    assert sanitize_quality_artifact(("a", "b")) == ["a", "b"]
    assert sanitize_quality_artifact({"k": ("a",)}) == {"k": ["a"]}


def test_scalars_pass_through_unchanged() -> None:
    for value in (1, 1.5, True, False, None):
        assert sanitize_quality_artifact(value) == value


def test_non_string_keys_are_stringified() -> None:
    assert sanitize_quality_artifact({1: "a"}) == {"1": "a"}
