"""`providers` 里解析上游响应的几个内部辅助。

`_usage_from_mapping` 决定 token 用量怎么从各家格式里读出来（OpenAI 的 `prompt_tokens`／
Ollama 的 `prompt_eval_count`），**成本统计的准确性就压在它身上**；`_non_negative_count`
是它的守门人，有个容易被忽略的细节：`bool` 是 `int` 的子类，必须单独排除，
否则 `True` 会被当成 1 混进用量。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.models import DialogueTestRequest
from stardew_ai_bridge.providers import (
    _default_provider_messages,
    _non_negative_count,
    _open_loop_from_mapping,
    _usage_from_mapping,
)


# --- _non_negative_count ----------------------------------------------------


def test_non_negative_count_accepts_zero_and_positive_ints() -> None:
    assert _non_negative_count(0) == 0
    assert _non_negative_count(42) == 42


@pytest.mark.parametrize("value", [True, False])
def test_non_negative_count_rejects_booleans(value: bool) -> None:
    # bool 是 int 的子类；不排除的话 True 会被当成 1 混进用量统计。
    assert _non_negative_count(value) is None


@pytest.mark.parametrize("value", [-1, 10.0, "10", None, [], {}])
def test_non_negative_count_rejects_everything_else(value: object) -> None:
    # 它**不做类型转换**：浮点与数字字符串都算“没给”。
    assert _non_negative_count(value) is None


# --- _usage_from_mapping ----------------------------------------------------


def test_usage_prefers_the_openai_field_names() -> None:
    usage = _usage_from_mapping(
        {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
    )

    assert usage is not None
    assert usage.input_tokens == 10
    assert usage.output_tokens == 2
    assert usage.total_tokens == 12


def test_usage_falls_back_to_prompt_and_completion_names() -> None:
    usage = _usage_from_mapping({"prompt_tokens": 7, "completion_tokens": 3})

    assert usage is not None
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    # 没给 total，但两边都有 → 推导出来
    assert usage.total_tokens == 10


def test_usage_understands_the_ollama_names() -> None:
    usage = _usage_from_mapping({"prompt_eval_count": 5, "eval_count": 4})

    assert usage is not None
    assert usage.input_tokens == 5
    assert usage.output_tokens == 4


def test_usage_takes_the_first_matching_key() -> None:
    # 两套命名都给时，按 input_tokens → prompt_tokens 的顺序取第一个有效值。
    usage = _usage_from_mapping({"input_tokens": 10, "prompt_tokens": 99})

    assert usage is not None
    assert usage.input_tokens == 10


def test_usage_does_not_derive_total_when_one_side_is_missing() -> None:
    usage = _usage_from_mapping({"prompt_tokens": 7})

    assert usage is not None
    assert usage.input_tokens == 7
    assert usage.output_tokens is None
    assert usage.total_tokens is None  # 只有一边，不能凭空相加


def test_usage_returns_none_when_nothing_usable_is_present() -> None:
    # 全无可读字段 → None，而不是一个三个字段都为空的 ProviderUsage。
    assert _usage_from_mapping({}) is None
    assert _usage_from_mapping({"input_tokens": -1, "output_tokens": True}) is None


def test_usage_returns_none_for_non_mappings() -> None:
    assert _usage_from_mapping(None) is None
    assert _usage_from_mapping([1, 2]) is None
    assert _usage_from_mapping("10") is None


# --- _open_loop_from_mapping ------------------------------------------------


def test_open_loop_returns_nothing_for_none() -> None:
    assert _open_loop_from_mapping(None) == (None, None)


def test_open_loop_reports_invalid_metadata_without_raising() -> None:
    # 上层只想要一个可读的失败原因，不希望这里抛异常打断整轮对话。
    signal, error = _open_loop_from_mapping("这不是字典")

    assert signal is None
    assert error == "openLoop: invalid metadata"


# --- _default_provider_messages ---------------------------------------------


def _request(**overrides: object) -> DialogueTestRequest:
    payload: dict[str, object] = {"npcId": "Shane", "message": "你好"}
    payload.update(overrides)
    return DialogueTestRequest(**payload)


def test_default_messages_use_the_display_name_when_present() -> None:
    messages = _default_provider_messages(_request(displayName="谢恩"))

    assert messages[0]["role"] == "system"
    assert "谢恩" in messages[0]["content"]


def test_default_messages_fall_back_to_the_npc_id() -> None:
    messages = _default_provider_messages(_request())

    assert "Shane" in messages[0]["content"]


def test_topic_intent_uses_an_empty_trigger_message() -> None:
    # topic 意图不传玩家消息，而是放一条带名字的空 user 消息作为触发标记。
    messages = _default_provider_messages(_request(intent="topic", message=""))

    assert messages[-1] == {"role": "user", "name": "topic_trigger", "content": ""}


def test_plain_intent_carries_the_player_message() -> None:
    messages = _default_provider_messages(_request(message="今天还好吗？"))

    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "今天还好吗？"
