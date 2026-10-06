"""`player_meta_word` 判据：NPC 用旁白写动作、并用「玩家」称呼对方。

2026-10-07 新增。起因是一条真实漏出的回复（语料 `dialogue-live.jsonl`）：

    抱住玩家，把下巴搁在她肩窝里，声音闷闷的带着点得意。……再抱会儿。

它**没有括号**，所以 `_stage_direction` 抓不到（那条判据只认 `（…）`）；
没括号 ⇒ `format_issue` 返回 None ⇒ 交给 `is_meta_narration`，
而后者只认「没有玩家输入」「根据角色设定」这类**任务说明复述**，也不认它。
于是这段旁白直接进了玩家可见的台词。

实测语料 255 条非兜底回复里这种形态只出现 1 次（0.4%），但它是**零假阳性**的
确定性错误：Alex 永远不会管对面叫「玩家」。

======================================================================
改这个判据前必须先读的两条设计红线
======================================================================

1. **只触发重试，不丢弃文本。**
   所以它走 `format_issue`（→ format 重试），**不**加进
   `_META_NARRATION_MARKERS`。那条路径的兜底 `_discard_meta_narration`
   会把整段换成「……」，玩家连台词都看不到 —— 比读到一段旁白更糟。
   下面 `test_does_not_pollute_the_discard_path` 钉住这一点。

2. **必须带标点边界，不能只匹配「玩家」两个字。**
   第一版写成 `玩家|用户`，当场打断两条既有链路：
     ① 任务说明「没有玩家输入，需要主动聊起一个话题」被判成 player_meta_word，
        抢在 `is_meta_narration` 之前，本该**丢弃**的回复改走了**重试**；
     ② group 对话的记忆标记「玩家下周要交一份报告。」被当成旁白，重试后
        `memory_highlights` 解析不出来，断言 `[] == ['玩家下周要交一份报告。']`。
   真正的旁白里「玩家」是一个名词短语的**结尾**（「抱住玩家，」「看着玩家。」），
   任务说明／记忆里它后面接的是**动词**（输入／下周要交）。
   标点边界就是把这两类切开的刀。`test_task_instruction_is_not_captured`
   和 `test_memory_marker_is_not_captured` 钉住这一点。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.guard import (
    PLAYER_META_WORD_RETRY_CONTENT,
    ProviderResult,
    ResponseGuard,
    is_meta_narration,
    retry_for_format_noise,
)

#: 真实漏出的那条。判据就是为它加的。
_LEAKED = "抱住玩家，把下巴搁在她肩窝里，声音闷闷的带着点得意。……再抱会儿。"

#: 既有元叙述链路（丢弃路径）的样本，绝不能被我这条判据抢走。
_TASK_INSTRUCTION = (
    "没有玩家输入，需要主动聊起一个话题。根据角色设定，喜欢独处、摩托车、"
    "晨跑。"
)


# --- 判据本身 --------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        _LEAKED,
        "看着玩家。",
        "他拍拍玩家的头。",
        "转身看向用户，笑了一下。",
    ],
)
def test_player_meta_word_is_detected(text: str) -> None:
    """旁白用「玩家」「用户」称呼对方时报 player_meta_word。"""

    assert ResponseGuard.format_issue(text) == "player_meta_word"


@pytest.mark.parametrize(
    "text",
    [
        # 任务说明：玩家后面接动词
        _TASK_INSTRUCTION,
        "玩家输入是空的，需要开场。",
        # 台词里正常提到「玩家输入」这个概念
        "你刚才说的玩家输入是什么意思？",
        # group 对话的记忆标记
        "玩家下周要交一份报告。",
        # 完全正常的对白
        "嘿，我不走。你抱这么紧，我能去哪儿。",
        "……行，不走。早餐在桌上，面包和蛋。",
    ],
)
def test_task_instruction_is_not_captured(text: str) -> None:
    """任务说明／记忆标记／正常对白都不能被抓 —— 否则打断既有链路。"""

    assert ResponseGuard.format_issue(text) is None


def test_memory_marker_is_not_captured() -> None:
    """group 对话的记忆标记单独钉一条。

    回归现场：这个形态被判成旁白后触发重试，重试的回复解析不出 memory，
    `test_multi_turn_service_exposes_memory_highlights_on_the_response`
    报 `[] == ['玩家下周要交一份报告。']`。
    """

    assert ResponseGuard.format_issue("玩家下周要交一份报告。") is None
    # 这个形态含全角括号，本来就该走 `stage_direction`（既有行为，保持不变）；
    # 这里要钉的是它**不要**被判成 player_meta_word。
    assert (
        ResponseGuard.format_issue("记忆（14）：玩家说：“早上好”")
        == "stage_direction"
    )


def test_stage_direction_still_wins_when_both_present() -> None:
    """既带括号又带「玩家」时按括号重试：模型对「去掉括号」的理解更直接。"""

    assert ResponseGuard.format_issue("（我抱住玩家）别走。") == "stage_direction"


def test_leading_punctuation_is_still_the_lightest() -> None:
    """新判据不能把既有判据的轻重顺序挤乱。"""

    assert ResponseGuard.format_issue("，你好。") == "leading_punctuation"
    assert ResponseGuard.format_issue("**你好。**") == "markdown"


# --- 红线 1：不污染丢弃路径 ------------------------------------------------

def test_does_not_pollute_the_discard_path() -> None:
    """旁白不该被 `is_meta_narration` 认领 —— 那样整段会被换成「……」。

    `is_meta_narration` 的兜底 `_discard_meta_narration` 是不可逆的：
    命中就把整段文本丢掉。玩家读到一段旁白，也好过什么都读不到。
    """

    assert is_meta_narration(_LEAKED) is False
    assert is_meta_narration(_LEAKED, at_start_only=True) is False


def test_existing_meta_narration_behaviour_is_intact() -> None:
    """既有的任务说明检测必须原样工作。"""

    assert is_meta_narration(_TASK_INSTRUCTION) is True
    assert is_meta_narration("玩家输入是空的，需要开场。") is True
    assert is_meta_narration("我今天没心情聊天。") is False


# --- 重试内容 --------------------------------------------------------------

def test_retry_content_tells_the_model_what_to_do_instead() -> None:
    """重试话术要给**替代动作**，不能只说「不要」。"""

    assert PLAYER_META_WORD_RETRY_CONTENT.strip()
    # 点名了要改成的目标
    assert "台词" in PLAYER_META_WORD_RETRY_CONTENT
    # 与既有的任务说明重试话术不是同一条
    from stardew_ai_bridge.guard import META_NARRATION_RETRY_CONTENT

    assert PLAYER_META_WORD_RETRY_CONTENT != META_NARRATION_RETRY_CONTENT


# --- 端到端 ----------------------------------------------------------------

def test_check_rejects_the_leaked_reply_with_its_own_reason() -> None:
    """`check` 给出的 reason 要能与 `meta_narration` 区分开。"""

    result = ResponseGuard().check(_LEAKED)

    assert result.accepted is False
    assert result.reason == "format_player_meta_word"


def _result(reply: str) -> ProviderResult:
    return ProviderResult(
        reply=reply,
        provider="fake",
        fallback=False,
        latencyMs=1,
        warnings=[],
    )


_PROMPT = [{"role": "system", "content": "你是亚历克斯。"}]


def test_a_retry_is_triggered_for_player_meta_word() -> None:
    """不是丢弃，是重试：重试后拿到干净台词就该放行。"""

    def clean(messages: list[dict[str, str]]) -> ProviderResult:
        return _result("……再抱会儿。心跳还挺快的。")

    outcome = retry_for_format_noise(_result(_LEAKED), _PROMPT, clean)

    assert outcome.reply == "……再抱会儿。心跳还挺快的。"
    assert outcome.retry_kinds is not None
    assert "player_meta_word" in outcome.retry_kinds
    assert outcome.fallback is False


def test_the_two_meta_paths_are_distinguishable_in_warnings() -> None:
    """`player_meta_word` 与 `meta_narration` 是两条路，诊断上必须能分开。"""

    def clean(messages: list[dict[str, str]]) -> ProviderResult:
        return _result("……再抱会儿。")

    mine = retry_for_format_noise(_result(_LEAKED), _PROMPT, clean)
    theirs = retry_for_format_noise(_result(_TASK_INSTRUCTION), _PROMPT, clean)

    mine_kinds = set(mine.retry_kinds or [])
    theirs_kinds = set(theirs.retry_kinds or [])

    assert "player_meta_word" in mine_kinds
    assert "player_meta_word" not in theirs_kinds
    assert "meta_narration" in theirs_kinds
