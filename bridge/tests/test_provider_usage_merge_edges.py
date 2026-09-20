"""两个 usage 合并器的口径差异：`app` 给部分和，`group_conversation` 给保守值。

- `app._merge_provider_usages`（网页一轮内多次 provider 尝试）：**部分和**——某条目缺某字段就
  跳过它、其余照常累加；只有**所有**条目都没报的字段才是 `None`。
- `group_conversation._merge_usage`（群聊多回合）：**保守**——只要有一条缺该字段，该字段整体
  为 `None`，宁可空着也不给一个偏小的数。

`app` 那个此前**没有任何测试**。本文件只保留 app 侧的边界与**两者差异的对照**；
`group_conversation` 侧自身的行为断言在 `test_group_usage_merge.py` 里，不在这里重复。
"""

from __future__ import annotations

from stardew_ai_bridge.app import _merge_provider_usages
from stardew_ai_bridge.group_conversation import _merge_usage
from stardew_ai_bridge.models import ProviderUsage


def _usage(
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
) -> ProviderUsage:
    return ProviderUsage(
        inputTokens=input_tokens,
        outputTokens=output_tokens,
        totalTokens=total_tokens,
    )


# --- app 侧（部分和）-------------------------------------------------------


def test_app_merge_returns_none_when_nothing_was_reported() -> None:
    assert _merge_provider_usages([]) is None
    assert _merge_provider_usages([None, None]) is None


def test_app_merge_sums_complete_entries() -> None:
    merged = _merge_provider_usages([_usage(10, 2, 12), _usage(5, 1, 6)])

    assert merged is not None
    assert (merged.input_tokens, merged.output_tokens, merged.total_tokens) == (15, 3, 18)


def test_app_merge_leaves_a_field_empty_when_one_entry_misses_it() -> None:
    """2026-09-20（语义层审计）统一口径。

    此前私聊逐字段累加、群聊保守，同一上游两条路径给出不同结果。
    现统一到**保守口径**：只要有一个 chunk 没报该字段就留空——
    token 用量用于成本统计，「缺失」比「偏小」安全。
    """
    merged = _merge_provider_usages([_usage(10, 2, 12), _usage(5)])

    assert merged is not None
    assert merged.input_tokens == 15
    assert (merged.output_tokens, merged.total_tokens) == (None, None)


def test_app_merge_omits_fields_that_no_entry_reported() -> None:
    merged = _merge_provider_usages([_usage(input_tokens=7), _usage(input_tokens=3)])

    assert merged is not None
    assert merged.input_tokens == 10
    assert merged.output_tokens is None
    assert merged.total_tokens is None


def test_app_merge_ignores_none_entries_among_real_ones() -> None:
    merged = _merge_provider_usages([None, _usage(4, 1, 5), None])

    assert merged is not None
    assert (merged.input_tokens, merged.total_tokens) == (4, 5)


# --- 差异本身（group 侧自身的行为见 test_group_usage_merge.py）-------------


def test_the_two_mergers_agree_on_partially_reported_fields() -> None:
    usages = [_usage(10, 2, 12), _usage(5)]

    app_side = _merge_provider_usages(usages)
    group_side = _merge_usage(usages)

    assert app_side is not None and group_side is not None
    # 两边都报了的字段，口径一致
    assert app_side.input_tokens == group_side.input_tokens == 15
    # 只有部分条目报了的字段，两边都留空（保守口径：缺失比偏小安全）
    assert app_side.output_tokens is None
    assert group_side.output_tokens is None
