"""方案 D：找话题时「第一反应」与「来源句」不再二选一（2026-09-21）。

用户反馈的形态是**妥协产物**：`_TOPIC_OPENING_GROUNDING_INSTRUCTION` 硬要求
「无论话题从哪来，都必须有一句来源句，用‘我刚把…’」，读起来就是「第一句必须是
来源句」；而索菲亚这类角色的 `signatureMoves[0]` 恰恰是「先脱口说出第一反应
（哇、等等、你看）」。两条要求直接互斥，实测找话题 12/12 全选「我刚把」，
角色招牌动作在开场整条消失。

落地方案是**合并**而不是二选一：

* 公共契约把**顺序**放开（来源句不必是第一条分句），但来源句仍是同一条消息内的
  硬要求 —— 「没头没尾」那个初衷不能丢；
* 第一条动作就是「以一声反应起句」的角色（索菲亚、Abigail、Elliott）额外拿到
  一句显式许可，说清「反应在前、来源紧跟」，避免模型为了先交代来源把它删掉。

本文件同时钉住 Guard 侧：合并形态的回复**不会**被判成「把缺失前情推给玩家」，
也不会触发任何重试。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.guard import missing_opening_grounding, retry_for_format_noise
from stardew_ai_bridge.models import ProviderResult
from stardew_ai_bridge.prompts import (
    PromptBuilder,
    _TOPIC_REACTION_OPENING_PERMISSION,
    has_reaction_opening_move,
)

# 线上 persona JSON 的原文（`data/personas/sve.json`）。
SOPHIA_MOVES = [
    "谈到绘画、酿造或刚发现的小事时，先脱口说出第一反应（哇、等等、你看），"
    "再用第二句追加一个同主题的新念头；两句用句号或感叹号断开，不用破折号串成长句",
    "被夸、被催或被问亲密决定时先短暂停顿或改口，回答后把选择权留给对方；普通事务不用每轮停顿",
]
# `data/personas/vanilla.json`。
ABIGAIL_MOVES = [
    "用一声短反应开口（哦、啊、呃、哇哦），紧接着把话头抛回给玩家，用一个具体的反问或小提议接上；",
    "被戳到痛处时先还嘴再自己笑场。",
]
# `data/personas/female-bachelors.json`。
ELLIOTT_MOVES = [
    "先用一句对眼前东西的即时反应开口（画、海风、纸笔声都算），把感受说完再点明它是什么；不先客套",
    "写不下去时把稿纸推开，说一句自嘲。",
]
HARVEY_MOVES = [
    "只挑对方此刻说的那一点接住（肩膀僵、累了、没睡好），用一句日常话确认，紧接着给一个当下就能做的小动作",
    "收尾用一句轻的关照或下次见面的具体入口。",
]
# 第二条才提「第一反应」的角色：只看第一条，不该命中。
LATE_REACTION_MOVES = [
    "起句先给出明确判断或短答，不用‘嗯’或‘唔’铺垫。",
    "说到喜欢的东西时会先脱口说出第一反应，再补细节。",
]

_MERGED_REPLY = "哇，等等——我刚把新画晾到窗边，颜料还没干。你要不要看一眼？"
_OPAQUE_REPLY = "那件事你听说了吗？"


def _context(moves: object, *, intent: str = "topic") -> dict[str, object]:
    identity: dict[str, object] = {
        "npcId": "Sophia",
        "displayName": "Sophia",
        "stageProfile": {"stage": "dating"},
    }
    if moves is not None:
        identity["voiceStyle"] = {"signatureMoves": moves}
    return {
        "npcIdentity": identity,
        "qualityContext": {},
        "interaction": {"intent": intent, "channel": "face_to_face"},
        "gameState": {"relationshipStage": "dating", "location": "FarmHouse"},
        "history": [],
    }


def _topic_messages(moves: object) -> list[dict[str, str]]:
    return PromptBuilder().build(_context(moves), "")


def _contract(messages: list[dict[str, str]]) -> str:
    return next(
        message["content"]
        for message in messages
        if message["name"] == "topic_response_contract"
    )


# --- 公共契约：顺序放开，来源句保留 ------------------------------------------


def test_topic_contract_allows_an_opening_beat_before_the_source_clause() -> None:
    contract = _contract(_topic_messages(HARVEY_MOVES))

    assert "顺序可以换，来源不能省" in contract
    assert "开场那一拍按角色自己的说话习惯来" in contract


# --- 2026-09-21 二次收紧：三处改动各钉一条 -----------------------------------


def test_opening_beat_is_limited_to_a_short_reaction_or_greeting() -> None:
    """改动一：那一拍不再是「观察或判断都算」这种无边界敞口。"""

    contract = _contract(_topic_messages(HARVEY_MOVES))

    assert "但这一拍只算一声反应或短招呼（十个字以内" in contract
    assert "不含新对象、不含指代" in contract
    assert "‘它／这个／那个’这类还没交代过的指代" in contract
    # 旧措辞正是本次实测问题的敞口，必须已从契约里消失。
    assert "一声反应、招呼、观察或判断都算" not in contract


def test_source_sentence_is_promoted_to_a_standalone_requirement() -> None:
    """改动二：从「只要…就…」的条件从句提为独立硬要求，并显式给出位置。"""

    contract = _contract(_topic_messages(HARVEY_MOVES))

    assert "同一条消息里必须有来源句，位置在开场那一拍之后" in contract
    assert "只要在同一条消息里紧接着把来源补上" not in contract


def test_the_new_clause_does_not_open_with_a_permissive_word() -> None:
    """改动三：不再用「不必」起手——那读起来像在放松要求。"""

    contract = _contract(_topic_messages(HARVEY_MOVES))

    assert "来源句不必是第一条分句" not in contract


# --- 离线检查：新措辞不再覆盖索菲亚那种形态 -----------------------------------

# 用户实测原文（2026-09-21「找话题」）。起句「还没完全干透」是一个**零形式指代**
# 的状态描述——字面上既没有「它」也没有「那个」。
_SOPHIA_LEAKED_REPLY = (
    "还没完全干透，我不想让颜色在灯下变了样。"
    "等它放到画架前，你先看第一眼，然后告诉我最喜欢哪块颜色，好吗？"
)
# 旧措辞放行这一拍的那半句。它是本次问题的敞口，必须已从契约里删掉。
_OLD_PERMISSIVE_CLAUSE = "一声反应、招呼、观察或判断都算"


def test_the_leaked_opening_shape_is_no_longer_licensed() -> None:
    """本次实测那句的形态，在新措辞下找不到任何许可。

    旧放行面是「一声反应、招呼、观察或判断都算」——「还没完全干透」是一个关于
    未交代对象的**观察**，正好落在里面，于是它被当成合法的开场那一拍，来源句
    就此省掉。收紧要成立，就得让这个形态不再被任何一句覆盖。
    """

    contract = _contract(_topic_messages(SOPHIA_MOVES))

    # 1) 旧敞口句已经不存在；
    assert _OLD_PERMISSIVE_CLAUSE not in contract
    # 2) 新放行面把「观察／判断」这一整类排除在那一拍之外；
    beat_clause = contract.split("但这一拍只算")[1].split("同一条消息里必须有")[0]
    assert "观察" not in beat_clause
    assert "判断" not in beat_clause
    # 3) 并且点名了零形式指代——只列「它／这个／那个」挡不住这句。
    assert "省掉主语的描述" in contract
    assert "‘还没干透’" in contract


def test_the_length_cap_alone_would_not_have_stopped_that_reply() -> None:
    """长度门槛只是必要条件：那句 7 字，光靠「十个字以内」挡不住。"""

    first_beat = _SOPHIA_LEAKED_REPLY.split("，")[0]

    assert first_beat == "还没完全干透"
    assert len(first_beat) <= 10
    contract = _contract(_topic_messages(SOPHIA_MOVES))
    assert "十个字以内" in contract
    # 真正起作用的是禁用面，不是长度。
    assert "不含新对象、不含指代" in contract


@pytest.mark.parametrize("moves", [SOPHIA_MOVES, ABIGAIL_MOVES, ELLIOTT_MOVES])
def test_reaction_permission_is_tightened_symmetrically(moves: list[str]) -> None:
    """对称保护：拿到许可句的正是索菲亚这类角色，许可不能比公共契约松。"""

    contract = _contract(_topic_messages(moves))

    assert "第一反应是一声感叹或招呼，不是对某样东西的描述" in contract
    assert "省掉主语的描述" in contract
    assert "来源句也不能省" in contract


def test_topic_contract_keeps_the_source_sentence_requirement() -> None:
    """「没头没尾」那个初衷不能回退。"""

    contract = _contract(_topic_messages(HARVEY_MOVES))

    assert "无论话题从哪来，都必须有一句来源句" in contract
    assert "‘我刚把…’" in contract
    assert "不要为了先交代来源而省掉这一拍" in contract


# --- 角色条件许可：只给「以一声反应起句」的角色 -------------------------------


@pytest.mark.parametrize(
    "moves",
    [SOPHIA_MOVES, ABIGAIL_MOVES, ELLIOTT_MOVES],
)
def test_reaction_opening_roles_get_the_explicit_permission(
    moves: list[str],
) -> None:
    contract = _contract(_topic_messages(moves))

    assert _TOPIC_REACTION_OPENING_PERMISSION in contract


@pytest.mark.parametrize("moves", [HARVEY_MOVES, LATE_REACTION_MOVES])
def test_other_roles_do_not_get_the_reaction_invitation(
    moves: list[str],
) -> None:
    """没有这个说话习惯的角色不该被邀请用「哇」开场。"""

    contract = _contract(_topic_messages(moves))

    assert _TOPIC_REACTION_OPENING_PERMISSION not in contract


def test_permission_is_absent_without_any_voice_style() -> None:
    contract = _contract(_topic_messages(None))

    assert _TOPIC_REACTION_OPENING_PERMISSION not in contract


def test_permission_is_not_added_to_ordinary_chat_turns() -> None:
    messages = PromptBuilder().build(
        _context(SOPHIA_MOVES, intent="chat"),
        "今天在忙什么？",
    )

    assert all(message["name"] != "topic_response_contract" for message in messages)


# --- 识别函数本身 ------------------------------------------------------------


@pytest.mark.parametrize(
    ("moves", "expected"),
    [
        (SOPHIA_MOVES, True),
        (ABIGAIL_MOVES, True),
        (ELLIOTT_MOVES, True),
        (HARVEY_MOVES, False),
        (LATE_REACTION_MOVES, False),
        ([], False),
        ("先脱口说第一反应", False),  # 类型不对不猜
        (["   "], False),
        (None, False),
    ],
)
def test_has_reaction_opening_move_reads_only_the_first_move(
    moves: object, expected: bool
) -> None:
    identity = {"voiceStyle": {"signatureMoves": moves}}
    assert has_reaction_opening_move(identity) is expected


@pytest.mark.parametrize("identity", [None, {}, {"voiceStyle": None}, {"voiceStyle": {}}])
def test_has_reaction_opening_move_is_total(identity: object) -> None:
    assert has_reaction_opening_move(identity) is False


# --- Guard 侧：合并形态不吃惩罚 ----------------------------------------------


def test_merged_reply_is_not_flagged_as_an_opaque_opening() -> None:
    messages = _topic_messages(SOPHIA_MOVES)

    assert missing_opening_grounding(messages, _MERGED_REPLY) is False
    # 对照组：真正没头没尾的指代仍然要拦（这条规则没被放松）
    assert missing_opening_grounding(messages, _OPAQUE_REPLY) is True


def test_merged_reply_survives_the_full_retry_pipeline() -> None:
    """反应在前 + 来源句紧跟的回复不该触发任何重试。"""

    def should_not_be_called(messages: list[dict[str, str]]) -> ProviderResult:
        raise AssertionError("合并形态是合法开场，不该重试")

    original = ProviderResult(
        reply=_MERGED_REPLY,
        provider="fake",
        fallback=False,
        latencyMs=1,
        warnings=[],
    )

    outcome = retry_for_format_noise(
        original,
        _topic_messages(SOPHIA_MOVES),
        should_not_be_called,
    )

    assert outcome.reply == _MERGED_REPLY
    assert outcome.warnings == []
