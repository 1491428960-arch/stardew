"""`guard.retry_for_format_noise` 的重试与失败回退。

2026-09-20 用覆盖率定位到 `guard.py` 93%，其中 **L1427–1439（13 行连续）** 是
“重试时抛非预算异常”的分支，从未被执行。它的契约是：**不把异常抛给调用方**，
而是保留已有回复、记两条警告，交给调用方现有兜底链路。

**2026-10-01 补了一条例外**：保留的前提是“保留下来的还是一句台词”。若那是元叙述
（模型把任务说明说了出来），兜底链路认不出来，就会原样进玩家输出 —— 实测 417 字的
自言自语正是这样漏出去的。所以该分支现在会丢弃元叙述、改发沉默兜底。

顺带钉住两条相关契约：

- 重试**成功但更差**时不采用它（只留一条“已重试”的警告）。
- 经济模式耗尽预算（`EvaluationBudgetExceeded`）时，把“预算停止”**如实**写进警告，
  不伪装成 ProviderError。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.evaluation_budget import EvaluationBudgetExceeded
from stardew_ai_bridge.guard import (
    META_NARRATION_FALLBACK,
    ResponseGuard,
    is_meta_narration,
    retry_for_format_noise,
)
from stardew_ai_bridge.models import ProviderResult

_PROMPT = [
    {"role": "system", "content": "你是 Shane。"},
    {"role": "user", "content": "你好"},
]

_DIRTY_REPLY = "（笑了笑）你好。"  # stage_direction


def _result(reply: str, warnings: list[str] | None = None) -> ProviderResult:
    return ProviderResult(
        reply=reply,
        provider="fake",
        fallback=False,
        latencyMs=1,
        warnings=list(warnings or []),
    )


# --- format_issue 的分类 ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("你好。", None),
        ("（笑了笑）你好。", "stage_direction"),
        ("你好（笑）", "stage_direction"),
        ("*微笑* 你好", "markdown"),
        ("**你好**", "markdown"),
        ("你好 [pause]", "english"),
        # 中文引号是正常排版，不该被判成 markdown
        ("他说“你好”。", None),
    ],
)
def test_format_issue_classifies_common_noise(text: str, expected: str | None) -> None:
    assert ResponseGuard.format_issue(text) == expected


# --- 重试失败：绝不抛给调用方 -----------------------------------------------


def test_a_failing_retry_keeps_the_original_reply_and_records_two_warnings() -> None:
    # 这是本次补测的核心契约：上游在重试时炸了，也不该让整轮对话失败。
    def boom(messages: list[dict[str, str]]) -> ProviderResult:
        raise RuntimeError("上游炸了")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, boom)

    assert outcome.reply == _DIRTY_REPLY
    assert outcome.warnings == [
        "response_format_retry: stage_direction",
        "response_format_retry_failed: provider_error",
    ]
    # 重试本身炸了 ⇒ 根本没比较过，只能是 None（无从判断），不是 False
    assert outcome.retry_improved is None


def test_a_retry_failure_does_not_mutate_the_input_result() -> None:
    def boom(messages: list[dict[str, str]]) -> ProviderResult:
        raise RuntimeError("上游炸了")

    original = _result(_DIRTY_REPLY)
    retry_for_format_noise(original, _PROMPT, boom)

    # 原对象保持干净（内部用的是 model_copy）
    assert original.warnings == []


def test_budget_exhaustion_is_reported_as_budget_not_as_a_provider_error() -> None:
    # 经济模式可能在初始回复后耗尽预算；这不该被伪装成上游故障。
    def exhausted(messages: list[dict[str, str]]) -> ProviderResult:
        raise EvaluationBudgetExceeded("max_requests")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, exhausted)

    assert outcome.reply == _DIRTY_REPLY
    # 与“重试失败”分支的区别值得注意：预算不足时**根本没有发起重试**，
    # 所以只有一条“已跳过”，不会出现“尝试过/失败”的记录。
    assert outcome.warnings == ["response_format_retry_skipped: budget_max_requests"]
    assert not any("provider_error" in warning for warning in outcome.warnings)


# --- 重试成功但结果更差 -----------------------------------------------------


def test_a_worse_retry_is_not_adopted() -> None:
    def still_dirty(messages: list[dict[str, str]]) -> ProviderResult:
        return _result("（还是带动作）嗯。")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, still_dirty)

    assert outcome.reply == _DIRTY_REPLY
    # 只有一条“已重试”的警告，没有失败标记
    assert outcome.warnings == ["response_format_retry: stage_direction"]
    # 重试**没有**改善 ⇒ 明确记 False。这是回答「480 次 affection 重试白跑了多少」的关键字段。
    assert outcome.retry_improved is False


def test_a_better_retry_replaces_the_reply() -> None:
    def clean(messages: list[dict[str, str]]) -> ProviderResult:
        return _result("鸡舍那边挺忙的，不过还行。")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, clean)

    assert outcome.reply == "鸡舍那边挺忙的，不过还行。"
    assert outcome.warnings == ["response_format_retry: stage_direction"]
    assert outcome.retry_improved is True


def test_clean_reply_is_returned_untouched_without_calling_generate() -> None:
    def should_not_be_called(messages: list[dict[str, str]]) -> ProviderResult:
        raise AssertionError("干净回复不该触发重试")

    original = _result("鸡舍那边挺忙的，不过还行。")
    outcome = retry_for_format_noise(original, _PROMPT, should_not_be_called)

    assert outcome is original
    # 没发生重试 ⇒ 无从判断，必须是 None（而不是 False —— 那会把「没跑」算成「跑了没用」）
    assert outcome.retry_improved is None


def test_skip_short_circuits_the_retry() -> None:
    def should_not_be_called(messages: list[dict[str, str]]) -> ProviderResult:
        raise AssertionError("skip=True 时不该重试")

    original = _result(_DIRTY_REPLY)
    outcome = retry_for_format_noise(original, _PROMPT, should_not_be_called, skip=True)

    assert outcome is original


# --- 元叙述：模型把任务说明当台词说出来 ---------------------------------------
#
# 实测（2026-10-01，`_length_retry_probe.py`，Sebastian hearts=12 第 1 轮）：
#     「没有玩家输入，需要主动聊起一个话题。根据角色设定，喜欢独处、摩托车、
#       音乐、编程，当前关系……」                              —— 417 字，进了玩家输出
# 那一轮先命中 format retry，重试又撞 provider_error，于是按“重试失败”分支
# **原样放行**。上面那条「不把异常抛给调用方、保留已有回复」的契约，
# 对「保留的这段根本不是人话」是不成立的。

_META_REPLY = (
    "没有玩家输入，需要主动聊起一个话题。根据角色设定，喜欢独处、摩托车、"
    "音乐、编程，当前关系阶段应该聊得深一些。"
)


def test_meta_narration_is_detected() -> None:
    assert is_meta_narration(_META_REPLY)
    assert is_meta_narration("根据角色设定，他不太爱说话。")
    assert is_meta_narration("玩家输入是空的，需要开场。")


def test_ordinary_dialogue_is_not_flagged() -> None:
    for line in (
        "唔，这季节的蕨草长得倒是比笔记里画的还快。",
        "摩托的化油器，油针卡住了，拆到一半。",
        "……你喜欢闻汽油味吗，还是只有我这样。",
    ):
        assert not is_meta_narration(line)
        assert not is_meta_narration(line, at_start_only=True)


def test_late_mention_only_counts_for_retry_not_for_discarding() -> None:
    """全文命中 ⇒ 值得重试；但只有**开头**命中才允许丢弃整段。

    两者严格程度不同是刻意的：触发重试多花一次请求，误报可容忍；
    丢弃文本不可逆，所以必须更紧。
    """

    late = (
        "唔，这季节的蕨草长得倒是比笔记里画的还快，我今早才在塔西侧岩缝里"
        "发现两株新的孢子囊，顺手记了一笔，回头还得对一对去年那本旧册子。"
        "你刚才说的玩家输入是什么意思？"
    )
    assert is_meta_narration(late)
    assert not is_meta_narration(late, at_start_only=True)


def test_meta_narration_triggers_a_retry() -> None:
    """元叙述必须触发重试。

    只钉「触发了」，不钉「重试版一定被采纳」—— 采纳与否由 `_retry_quality_key`
    择优决定，那是另一条契约（见 `test_a_better_retry_replaces_the_reply`）。
    """

    def clean(messages: list[dict[str, str]]) -> ProviderResult:
        return _result("……没什么。就铁路线上有辆车的编号，好像是新调的。")

    outcome = retry_for_format_noise(_result(_META_REPLY), _PROMPT, clean)

    assert "response_meta_narration_retry: meta_narration" in outcome.warnings


def test_failed_retry_does_not_release_meta_narration() -> None:
    """回归：这句以前会原样进玩家输出（417 字那次的路径）。"""

    def boom(messages: list[dict[str, str]]) -> ProviderResult:
        raise RuntimeError("provider_error")

    outcome = retry_for_format_noise(_result(_META_REPLY), _PROMPT, boom)

    assert outcome.reply == META_NARRATION_FALLBACK
    assert outcome.reply != _META_REPLY
    assert "response_meta_narration_retry_failed: provider_error" in outcome.warnings
    assert "response_meta_narration_discarded" in outcome.warnings


def test_failed_retry_still_releases_ordinary_dialogue() -> None:
    """只有元叙述才丢弃；普通脏回复仍按原契约保留，交给调用方兜底。"""

    def boom(messages: list[dict[str, str]]) -> ProviderResult:
        raise RuntimeError("provider_error")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, boom)

    assert outcome.reply == _DIRTY_REPLY
    assert "response_meta_narration_discarded" not in outcome.warnings
