"""群聊 usage 合并的边界。

`_merge_usage()` 是全项目最后一个“整段未覆盖的函数”（覆盖率一度把 29 个
`app.py` 端点误报为未覆盖，那是 `test_api.py` 收集失败造成的假象）。它的口径是
“缺条目可忽略，但**任一条目缺某个字段，该字段整体为 None**”，值得钉住。
"""

from __future__ import annotations

from stardew_ai_bridge.group_conversation import _merge_usage
from stardew_ai_bridge.models import ProviderUsage


def test_merge_usage_returns_none_when_nothing_was_reported() -> None:
    assert _merge_usage([]) is None
    assert _merge_usage([None, None]) is None


def test_merge_usage_sums_complete_entries() -> None:
    merged = _merge_usage(
        [
            ProviderUsage(inputTokens=10, outputTokens=2, totalTokens=12),
            ProviderUsage(inputTokens=5, outputTokens=1, totalTokens=6),
        ]
    )

    assert merged is not None
    assert merged.input_tokens == 15
    assert merged.output_tokens == 3
    assert merged.total_tokens == 18


def test_merge_usage_skips_missing_entries_but_keeps_the_sum() -> None:
    merged = _merge_usage(
        [None, ProviderUsage(inputTokens=4, outputTokens=1, totalTokens=5)]
    )

    assert merged is not None
    assert merged.input_tokens == 4
    assert merged.total_tokens == 5


def test_merge_usage_reports_none_for_a_field_missing_somewhere() -> None:
    # 保守口径：只要有一个条目没报该字段，合并结果就不给这个字段一个偏小的数。
    merged = _merge_usage(
        [
            ProviderUsage(inputTokens=10, outputTokens=2, totalTokens=12),
            ProviderUsage(inputTokens=5),
        ]
    )

    assert merged is not None
    assert merged.input_tokens == 15
    assert merged.output_tokens is None
    assert merged.total_tokens is None
