"""三个小函数的补测：参与者提示词收集、关系状态拷贝、事件条件保留。

按函数级覆盖率排序挑出来的，各缺 1/3 左右，而缺的多是**容错与拒绝分支**——
这类分支不测的后果是“一个坏输入让整条链路不可用”，而它们存在的意义恰恰是防这个。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.corpus import _event_conditions
from stardew_ai_bridge.group_conversation import GroupConversationService
from stardew_ai_bridge.models import ProviderUsage
from stardew_ai_bridge.providers import ProviderRouter
from stardew_ai_bridge.relationship_world import _copy_state


# --- _participant_prompts ---------------------------------------------------


def _service(prompt_provider=None):  # type: ignore[no-untyped-def]
    return GroupConversationService(ProviderRouter(), prompt_provider=prompt_provider)


def test_no_prompt_provider_yields_an_empty_mapping() -> None:
    assert _service()._participant_prompts([], None) == {}  # type: ignore[arg-type]


def test_a_failing_prompt_provider_does_not_break_group_chat() -> None:
    # 取卡失败不该让整个群聊不可用。
    def boom(participants, request):  # type: ignore[no-untyped-def]
        raise RuntimeError("角色卡服务炸了")

    assert _service(boom)._participant_prompts([], None) == {}  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["不是映射", 42, ["a"], None])
def test_a_non_mapping_result_is_discarded(bad: object) -> None:
    def provider(participants, request):  # type: ignore[no-untyped-def]
        return bad

    assert _service(provider)._participant_prompts([], None) == {}  # type: ignore[arg-type]


def test_keys_are_case_folded_and_values_must_be_sequences() -> None:
    card = [{"role": "system", "content": "你是 Shane。"}]

    def provider(participants, request):  # type: ignore[no-untyped-def]
        return {
            "Shane": card,          # 保留，键折叠成小写
            "EMILY": ("x",),        # tuple 也算序列
            "bad-string": "文本",   # 字符串被排除
            "bad-bytes": b"x",      # bytes 被排除
            "bad-int": 42,          # 非序列被排除
        }

    result = _service(provider)._participant_prompts([], None)  # type: ignore[arg-type]

    assert set(result) == {"shane", "emily"}
    assert result["shane"] is card


# --- _copy_state ------------------------------------------------------------


def test_a_mapping_is_copied_deeply() -> None:
    original = {"views": [{"visibility": "known"}]}

    copied = _copy_state(original)
    copied["views"].append({"visibility": "unknown"})  # type: ignore[union-attr]

    assert copied == {"views": [{"visibility": "known"}, {"visibility": "unknown"}]}
    # 原对象不受影响：这是 deepcopy 而非浅拷贝
    assert original == {"views": [{"visibility": "known"}]}


def test_a_pydantic_model_is_dumped_with_aliases_and_without_nones() -> None:
    usage = ProviderUsage(inputTokens=3)

    # by_alias=True → 驼峰键；exclude_none=True → 没给的字段不出现
    assert _copy_state(usage) == {"inputTokens": 3}


@pytest.mark.parametrize("value", [None, "文本", 42, ["a"], (1,)])
def test_anything_else_is_a_type_error(value: object) -> None:
    with pytest.raises(TypeError, match="关系状态必须是 Mapping 或 Pydantic 模型"):
        _copy_state(value)  # type: ignore[arg-type]


# --- _event_conditions ------------------------------------------------------


def test_a_non_empty_event_key_is_kept_verbatim() -> None:
    # 保留原始键供审计用，不猜游戏内部语义。
    assert _event_conditions("fall_13") == {"raw": "fall_13"}
    assert _event_conditions("  fall_13  ") == {"raw": "fall_13"}


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_event_key_yields_no_conditions(value: str) -> None:
    assert _event_conditions(value) == {}
