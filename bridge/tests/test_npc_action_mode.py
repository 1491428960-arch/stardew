"""B 阶段开关的双向回归测试：允许 NPC 用 `（）` 写**自己的**动作。

背景
----
玩家可以在输入里写 `（坐到床边，拍拍被子）过来，再陪我一会`。原来的 prompt 里
**没有任何一条规则**说明这种括号动作是什么，模型于是把它当成一句"已声明的事实"
应一声就走过；同时 prompt 里散着 11 处「禁止动作旁白」，把 NPC **自己**的动作
也一起禁掉了。真实回复因此退化成复述玩家动作 + 丢掉请求：

    「你床边的位置是好，不过我先说好，躺着可不算锻炼。刚还想做几组俯卧撑——
      但你都拍被子了，那今天的训练指标……改做陪聊也算数吧。说吧，什么事？」

本开关（环境变量 `STARDEW_AI_NPC_ACTION`）打开后：
  · prompt 侧把「禁止动作旁白」换成**正面**规范（教它动作写成什么样，而不是禁止动作）；
    禁止式会 priming，A1 实测把 `stage_direction` 触发率从 25.0% 推到 37.0%。
  · 把「不要复述玩家**原话**」扩展到「话和做法都不还回去」。
  · guard 侧只放行**句中**括号；整条被括号包住的仍判死（保护带括号的兜底语）。

红线
----
关闭时两侧行为必须与 B 之前**逐字节一致**。任何一条断言失败都说明开关漏了。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge import guard, prompts

# B 之前的原文，逐字。关闭时必须在场。
OLD_ACTION_CLAUSE = "禁止动作旁白，包括括号、星号或其他舞台说明和环境描写。"
OLD_RESTATE_CLAUSE = "不要先复述、改写或总结玩家原话"
OLD_BUDGET_CLAUSE = "不要用旁白"

# 打开后才允许出现的正面规范。
NEW_ACTION_RULE = "客观片段"
NEW_FACT_RULE = "当成已经发生的事接住"

# 带括号的兜底语：app.py 明确注明「括号是有意的，不要去改」。
# 它是全语料唯一的 whole_wrapped 形态，两种模式下都必须判死。
SAFE_FALLBACK = "（暂时没有合适的回复，请稍后再试。）"

STAGES = ("stranger", "acquaintance", "friend", "close", "dating", "married")


@pytest.fixture()
def mode_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts, "NPC_ACTION_MODE", False)
    monkeypatch.setattr(guard, "NPC_ACTION_MODE", False)


@pytest.fixture()
def mode_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts, "NPC_ACTION_MODE", True)
    monkeypatch.setattr(guard, "NPC_ACTION_MODE", True)


def _all_instructions() -> list[str]:
    """枚举 `_stage_execution_instruction` 的全部四条分支 × 六个阶段。"""
    return [
        prompts._stage_execution_instruction(
            {"stage": stage}, natural_light_turn=nl, topic_request=tq
        )
        for stage in STAGES
        for nl in (False, True)
        for tq in (False, True)
    ]


# --------------------------------------------------------------------------
# prompt 侧
# --------------------------------------------------------------------------


def test_off_keeps_original_wording(mode_off: None) -> None:
    """关闭时必须是 B 之前的原文，一条新规范都不许出现。"""
    text = "\n".join(_all_instructions())
    assert OLD_ACTION_CLAUSE in text
    assert OLD_RESTATE_CLAUSE in text
    assert OLD_BUDGET_CLAUSE in text
    assert NEW_ACTION_RULE not in text
    assert NEW_FACT_RULE not in text


def test_off_covers_every_branch(mode_off: None) -> None:
    """四分支 × 六阶段共 24 条，每条都得还带着原句。"""
    for text in _all_instructions():
        assert OLD_ACTION_CLAUSE in text


def test_on_clears_every_forbidden_clause(mode_on: None) -> None:
    """打开时「禁止动作旁白」必须清零 —— 残留一处就是单一权威冲突。"""
    for text in _all_instructions():
        assert "禁止动作旁白" not in text


def test_on_installs_positive_rules(mode_on: None) -> None:
    text = "\n".join(_all_instructions())
    assert NEW_ACTION_RULE in text
    assert NEW_FACT_RULE in text


def test_on_retires_old_clauses(mode_on: None) -> None:
    """旧的复述禁令与预算句都应换成正面表述。"""
    text = "\n".join(_all_instructions())
    assert OLD_RESTATE_CLAUSE not in text
    assert OLD_BUDGET_CLAUSE not in text


def test_on_action_rule_is_positive_not_negated(mode_on: None) -> None:
    """规范本身必须说清"写成什么样"，而不是只说"不许写"。

    这是 A1 的教训：在常驻卡里点名一个禁止的 register 会**提高**它的出现率。
    """
    text = prompts._stage_execution_instruction({"stage": "close"})
    assert "客观片段" in text
    assert "不带「我」" in text


# --------------------------------------------------------------------------
# guard 侧
# --------------------------------------------------------------------------


def test_guard_off_rejects_any_bracket(mode_off: None) -> None:
    """关闭时任何括号都判死 —— 与 B 之前一致。"""
    assert guard.ResponseGuard.format_issue("（挪开一点）行，陪你一会儿") == "stage_direction"
    assert guard.ResponseGuard.format_issue(SAFE_FALLBACK) == "stage_direction"


def test_guard_on_rejects_whole_wrapped(mode_on: None) -> None:
    """打开时整条被括号包住的仍必须判死，最重要的就是兜底语。"""
    assert guard.ResponseGuard.format_issue(SAFE_FALLBACK) == "stage_direction"
    assert (
        guard.ResponseGuard.format_issue("（我走过去，抱住她，把下巴搁在她肩上）")
        == "stage_direction"
    )


def test_guard_on_allows_inline_bracket(mode_on: None) -> None:
    """打开时句中出现括号要放行 —— 那是 NPC 在写自己的动作。"""
    assert guard.ResponseGuard.format_issue("（挪开一点，把被子往你那边推了推）行，陪你一会儿") is None
    assert guard.ResponseGuard.format_issue("行，我这就过来陪你。") is None


def test_guard_on_accepts_inline_bracket_reply(mode_on: None) -> None:
    result = guard.ResponseGuard().check("（挪开一点）行，陪你一会儿")
    assert result.accepted is True


def test_guard_off_still_accepts_plain_dialogue(mode_off: None) -> None:
    """开关关掉不该影响普通台词。"""
    assert guard.ResponseGuard().check("行，我这就过来陪你。").accepted is True


@pytest.mark.parametrize("mode", [False, True])
def test_guard_fallback_never_stripped(monkeypatch: pytest.MonkeyPatch, mode: bool) -> None:
    """兜底语在两种模式下都必须保持原样，不能被剥掉。

    app.py 的注释写得很死：「括号是有意的，不要去改」。
    """
    monkeypatch.setattr(guard, "NPC_ACTION_MODE", mode)
    result = guard.ResponseGuard().check(SAFE_FALLBACK)
    assert result.accepted is False
    assert result.text != SAFE_FALLBACK  # 判死时 text 为空，不会把兜底语原样放行


# ---------------------------------------------------------------------------
# 长度判定：括号动作不计入对白长度（2026-10-07，B2）
#
# 依据是 37 条**首答**（重试前文本）的实测，探针挂在
# `reply_exceeds_dialogue_length` 上：
#     净对白（去括号）  中位 29 / 均值 31.1 / 超 68 仅 2.7%
#     括号开销          中位 42 / 均值 40.2 / p90 56 / max 79
#     总长              中位 72 / 超 68 达 57%
# 对照组关闭态的对白中位是 39 字、历史基线超 68 字 5.79% ⇒ B **没有**让对白变啰嗦，
# 净对白反而更短，多出来的 40 字全是动作开销。而按总长判会让 over_length
# 从 23% 涨到 88%，那 57% 里没有一条真的啰嗦。
# ---------------------------------------------------------------------------


def _blk(n: int) -> str:
    """造一个 n 字的括号块；n 必须 <= 80 才匹配 `_stage_direction`。"""

    return "（" + "字" * n + "）"


def test_length_off_is_unchanged(mode_off: None) -> None:
    """关闭时只看总长，与 B 之前完全一致。"""

    assert guard.reply_exceeds_dialogue_length("字" * 70) is True
    assert guard.reply_exceeds_dialogue_length("字" * 60) is False
    assert guard.reply_exceeds_dialogue_length(_blk(12) + "字" * 70) is True


def test_length_on_ignores_own_action(mode_on: None) -> None:
    """打开时括号动作不计入长度，对白部分仍按原来的数判。"""

    assert guard.reply_exceeds_dialogue_length(_blk(12) + "字" * 70) is True
    assert guard.reply_exceeds_dialogue_length(_blk(12) + "字" * 60) is False
    # 实测里的典型形态：总长远超 68，净对白却很短。
    assert (
        guard.reply_exceeds_dialogue_length(
            "（愣了一下，随即放松下来，手搭上你后背）" + "字" * 30
        )
        is False
    )


def test_length_on_blocks_bracket_stuffing(mode_on: None) -> None:
    """防灌水：动作开销本身有预算，超了仍要重试。"""

    assert guard.reply_exceeds_dialogue_length(_blk(50) + "字" * 10 + _blk(50)) is True
    assert guard.reply_exceeds_dialogue_length(_blk(40) + "字" * 10 + _blk(40)) is False


def test_length_on_oversized_block_falls_back_to_total(mode_on: None) -> None:
    """单块超过 80 字时 `_stage_direction` 不匹配 ⇒ 剥不掉 ⇒ 落回总长判定。

    这是量词上限带来的免费防线，不是有意设计，但行为必须固定下来。
    """

    assert guard.reply_exceeds_dialogue_length(_blk(100) + "字" * 10) is True


def test_strip_stage_directions_touches_brackets_only() -> None:
    """剥离只动括号，其余一字不碰。"""

    assert guard._strip_stage_directions("（愣了一下）不走。") == "不走。"
    assert guard._strip_stage_directions("不走。") == "不走。"


@pytest.mark.parametrize("mode", [False, True])
def test_fallback_length_never_retried(
    monkeypatch: pytest.MonkeyPatch, mode: bool
) -> None:
    """兜底语在**长度**这条路上必须放行 —— 判死它的是 `format_issue` 那条路。

    两条路语义不同，不要合流：这里只问「对白多长」，
    那里问「该不该打回重写」。
    """

    monkeypatch.setattr(guard, "NPC_ACTION_MODE", mode)
    assert guard.reply_exceeds_dialogue_length(SAFE_FALLBACK) is False
