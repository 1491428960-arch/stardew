"""前导标点：`leading_punctuation` 的识别与兜底剥离（2026-09-21）。

上游偶发把整段开头的标点留下（删掉前一分句却没删标点，或从长句中间截断），
玩家看到的就是「，哇，今天……」这种标点排在气泡最前面的形态。两条契约：

1. `format_issue` 把它当**最轻**的一类噪声报出来，于是现有的 format 重试
   会顺手修一次（不新增重试种类、不新增预算）；
2. `check` 在重试没修好时**兜底剥离**再按同一条回复验收 —— 不按其他格式噪声
   那样判死（判死会换成 fallback 回复，比开头多一个逗号糟得多）。

**刻意不含「……」**：省略号是中文里合法的停顿开场（历史工件 6142 条真实回复里
12 条以它起句，占比 0.195%），拦它会把「……嗯。」这类正常犹豫也判成噪声。

同时钉住 `_retry_quality_key` 的择优方向：剥干净的版本必须**比带标点的版本好**，
否则重试链路会把已经修好的回复又换回脏的那条。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.guard import (
    ResponseGuard,
    _retry_quality_key,
    retry_for_format_noise,
)
from stardew_ai_bridge.models import ProviderResult

_PROMPT = [
    {"role": "system", "content": "你是 Shane。"},
    {"role": "user", "content": "你好"},
]

_DIRTY = "，哇，我刚把新画晾到窗边，颜料还没干。"
_CLEAN = "哇，我刚把新画晾到窗边，颜料还没干。"


def _result(reply: str) -> ProviderResult:
    return ProviderResult(
        reply=reply,
        provider="fake",
        fallback=False,
        latencyMs=1,
        warnings=[],
    )


# --- format_issue：识别集合 --------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["，哇，你好。", ", hi 你好。", "  ，哇。", "、嗯。", "；咦？", "：唔。"],
)
def test_format_issue_detects_leading_punctuation(text: str) -> None:
    assert ResponseGuard.format_issue(text) == "leading_punctuation"


@pytest.mark.parametrize(
    "text",
    [
        "……嗯，你先坐。",  # 省略号是合法停顿开场，刻意不拦
        "…好。",
        "哇，等等。",  # 正常的句首反应
        "。好。",  # 句号／问号／破折号不在本次范围内（获批的正则只有这两组）
        "！好。",
        "——好。",
        "你好，哇。",
    ],
)
def test_format_issue_leaves_legal_openings_alone(text: str) -> None:
    assert ResponseGuard.format_issue(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("，（笑了笑）你好。", "stage_direction"),
        ("，**你好**", "markdown"),
        ("，hello 你好", "english"),
    ],
)
def test_heavier_noise_outranks_leading_punctuation(
    text: str, expected: str
) -> None:
    """别的噪声先报出来，重试方向才不会被一个逗号带跑。"""

    assert ResponseGuard.format_issue(text) == expected


# --- check：兜底剥离而不是判死 -----------------------------------------------


def test_check_strips_leading_punctuation_and_accepts() -> None:
    outcome = ResponseGuard().check(_DIRTY)

    assert outcome.accepted
    assert outcome.reason == "accepted"
    assert outcome.text == _CLEAN


def test_check_strips_repeated_punctuation_and_spaces() -> None:
    outcome = ResponseGuard().check("，, 、 哇，你看。")

    assert outcome.accepted
    assert outcome.text == "哇，你看。"


def test_check_rejects_reply_that_is_only_punctuation() -> None:
    outcome = ResponseGuard().check("，、；：")

    assert not outcome.accepted
    assert outcome.reason == "empty"


def test_check_still_rejects_other_format_noise() -> None:
    for text, reason in (
        ("（笑了笑）你好。", "format_stage_direction"),
        ("**你好**", "format_markdown"),
        ("hello 你好", "format_english"),
    ):
        outcome = ResponseGuard().check(text)
        assert not outcome.accepted, text
        assert outcome.reason == reason


def test_check_reports_the_heavier_issue_hidden_behind_punctuation() -> None:
    """剥掉前导标点后暴露出来的问题照旧要拦。"""

    outcome = ResponseGuard().check("，（笑了笑）你好。")

    assert not outcome.accepted
    assert outcome.reason == "format_stage_direction"


def test_check_truncates_after_stripping() -> None:
    guard = ResponseGuard(max_chars=5)

    outcome = guard.check("，一二三四五六七八")

    assert outcome.accepted
    assert outcome.reason == "truncated"
    assert outcome.text == "一二三四五"


def test_strip_helper_is_total_and_idempotent() -> None:
    guard = ResponseGuard()

    assert guard.strip_leading_punctuation("，，好。") == "好。"
    assert guard.strip_leading_punctuation("，，好。") == "好。"
    assert guard.strip_leading_punctuation(None) == ""
    assert guard.strip_leading_punctuation(42) == ""


# --- 重试链路：清洗后的版本必须更好，不能被换回去 -----------------------------


def test_retry_quality_key_prefers_the_cleaned_reply() -> None:
    """`_best_retry_result` 按这个 key 择优；方向反了就等于重试白做。"""

    dirty = _retry_quality_key(_PROMPT, _DIRTY)
    clean = _retry_quality_key(_PROMPT, _CLEAN)

    assert clean > dirty


def test_retry_adopts_the_cleaned_reply() -> None:
    def cleaned(messages: list[dict[str, str]]) -> ProviderResult:
        return _result(_CLEAN)

    outcome = retry_for_format_noise(_result(_DIRTY), _PROMPT, cleaned)

    assert outcome.reply == _CLEAN
    assert outcome.warnings == ["response_format_retry: leading_punctuation"]


def test_still_dirty_retry_keeps_the_original_reply() -> None:
    """重试又给一条同样脏的回复时，保留原回复并如实记一条警告。"""

    def still_dirty(messages: list[dict[str, str]]) -> ProviderResult:
        return _result("，还是带标点。")

    outcome = retry_for_format_noise(_result(_DIRTY), _PROMPT, still_dirty)

    assert outcome.reply == _DIRTY
    assert outcome.warnings == ["response_format_retry: leading_punctuation"]


def test_ellipsis_opening_does_not_trigger_a_retry() -> None:
    def should_not_be_called(messages: list[dict[str, str]]) -> ProviderResult:
        raise AssertionError("省略号开场不是噪声，不该重试")

    original = _result("……嗯，你先坐。")
    outcome = retry_for_format_noise(original, _PROMPT, should_not_be_called)

    assert outcome is original
