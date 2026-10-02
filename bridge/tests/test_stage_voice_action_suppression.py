"""stranger 阶段必须压掉与阶段卡对立的招牌动作。

背景（2026-09-28，prompt 落点探测）：`stage_execution_card` 在 stranger 阶段
写的是全 prompt 最强措辞 ——「这是本轮必须执行的关系行为卡……初识阶段不得
反问、邀约或主动换题」。模型仍然照了 `voice_execution_card.voiceActions` 里的
「先用一句赶人或怀疑的反问挡住」。原因是阶段卡声明压的是「泛化的热情、礼貌
或延长对话倾向」，而招牌动作被读成「角色专属」，不在其射程内。

本组测试固定的是**抑制表的边界**：stranger 压、其它阶段不压、无害条目不动。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.prompts import (
    _STRANGER_VOICE_ACTION_REWRITES,
    _build_voice_execution_card,
    _compact_gender_presentation,
    _stranger_filtered_speech_evidence,
)

SHANE_REVERSE_QUESTION = (
    "先用一句赶人或怀疑的反问挡住，问对方到底要干什么，再决定要不要继续；"
    "不主动解释自己的状态，也不用问候开场"
)
HARMLESS_MOVE = "先说实际情况，不写漂亮总结"

# 人读枚举（11 角色 / 33 条）后判定与 stranger 阶段卡对立的全部条目。
CONFLICTING_MOVES = (
    SHANE_REVERSE_QUESTION,
    "把处境说成一个带具体物件的干巴巴比喻或自嘲，说完不往深里解释；"
    "真被说中时允许只回半句或者直接换话题",
    "起句先抛一个悬在半空的短问或念头，把话头递回给对方，而不是给完整回答；"
    "不写铺垫性描写，也不先解释自己为什么会这么想，说完就等对方接",
    "用一声‘嘿’把人叫住，紧接着问一个要对方表态的具体问题，问自己或问对方都行；"
    "不铺垫背景，也不先解释为什么问",
    "起句先用一个很短的界定或反问把对方的来意点住，不确认对方没有恶意就不展开；"
    "不熟时宁可用单句保持距离，也不堆问候语和客套铺垫把话说圆",
    "把话题顺手变成一件可以一起做的小事，直接抛出两三个具体选项；"
    "被否定时一句自嘲就收掉，不追问也不解释",
    # 以下 6 条来自 2026-09-28 全量枚举（13 处 voiceStyle × 3 条全部人读）。
    # 它们所属的角色**没有 stranger 用例**，所以此前从未被观察过。
    "先回应玩家说的事，再决定是否把它变成一起做的小活动",  # Sam
    "说到自己时允许当场露出犹豫或想被认可，再自己收回；"
    "收尾把话交回对方或回到手头的作品上，不写总结式抒情",  # Elliott
    "收尾用一句轻的关照或下次见面的具体入口；"
    "偶尔说一句自己的状态（今天看了几个病人、眼睛有点花），"
    "说完立刻用轻松话收住，不展开",  # Harvey
    "收尾把话头交回对方时用一个具体的问句，不用泛泛的‘你怎么看’；"
    "发现自己说重了或越界时立刻收回并道歉，不解释理由也不接着辩解",  # Victor
    "收尾落到一条对玩家的具体建议或安排，不用挽留式收束；"
    "忙或不想谈时直接说现在没空、让对方先离开，不为这个决定解释原因",  # Olivia
    "收尾落在祝福、邀约或一件递出去的东西上就停，不追加感想或叮嘱；"
    "被问到公会内部的事只说一句不方便讨论细节，不编内容也不替别人解释",  # Lance
)

# Sophia [0] 的完整原文：前半句是声线，后半句与「最多 1 句」冲突。
SOPHIA_ACTION_0 = (
    "谈到自己在意的东西或刚发现的小事时，先脱口说出第一反应"
    "（嗯……、哦、呀、等、等一下），再用第二句追加一个同主题的新念头；"
    "两句用句号或感叹号断开，不用破折号串成长句；"
    "情绪上来时用感叹号和省略号，不要用逗号把好几句话连成一条长句"
)


def _identity(stage: str, *moves: str) -> dict[str, object]:
    return {
        "voiceStyle": {"signatureMoves": list(moves)},
        "stageProfile": {"stage": stage},
    }


@pytest.mark.parametrize("move", CONFLICTING_MOVES)
def test_stranger_suppresses_conflicting_signature_move(move: str) -> None:
    card = _build_voice_execution_card(_identity("stranger", move))

    assert not card.get("voiceActions")


@pytest.mark.parametrize("move", CONFLICTING_MOVES)
def test_other_stages_keep_conflicting_signature_move(move: str) -> None:
    """抑制**只**针对 stranger —— 反问和递话头在熟人阶段是角色特征。"""
    card = _build_voice_execution_card(_identity("friend", move))

    assert card.get("voiceActions") == [move]


def test_stranger_keeps_harmless_signature_move() -> None:
    card = _build_voice_execution_card(_identity("stranger", HARMLESS_MOVE))

    assert card.get("voiceActions") == [HARMLESS_MOVE]


def test_stranger_suppression_keeps_the_rest_of_the_card() -> None:
    """压掉动作不等于丢掉整张卡 —— 身份、语域、口语颗粒都要留下。"""
    card = _build_voice_execution_card(
        _identity("stranger", SHANE_REVERSE_QUESTION, HARMLESS_MOVE)
    )

    assert card.get("voiceActions") == [HARMLESS_MOVE]
    assert card.get("relationshipStage") == "stranger"
    assert card.get("instruction")


def test_suppression_happens_before_the_three_item_cut() -> None:
    """先过滤再截断：否则被压掉的名额会白占，后面的候选补不进来。

    ⚠ 候选必须真的超过 3 条才能区分两种顺序 —— `signatureMoves` 和
    `responseRules` 各只取 2 条，所以要両边都填满。（第一版把 4 条全堆在
    `signatureMoves` 里，而它 `limit=2`，前两条恰好都被抑制 ⇒ 假失败。）
    """
    identity = {
        "voiceStyle": {
            "signatureMoves": [SHANE_REVERSE_QUESTION, "保留动作A"],
            "responseRules": ["保留动作B", "保留动作C"],
        },
        "stageProfile": {"stage": "stranger"},
    }

    card = _build_voice_execution_card(identity)

    # 若先截断，得到的是 [被抑制, 保留A, 保留B] ⇒ 过滤后只剩两条，
    # “保留动作C”被截掉且再也补不回来。
    assert card.get("voiceActions") == ["保留动作A", "保留动作B", "保留动作C"]


def test_stranger_rewrites_sophia_action_instead_of_dropping_it() -> None:
    """Sophia 的条目要**换措辞**，不能整条删 —— 前半句是她活泼的来源。

    实测：模型照「再用第二句追加一个同主题的新念头」回了完整两段，
    而阶段卡写的是「回复最多 1 句」，且阶段卡明确说了自己优先。
    """

    card = _build_voice_execution_card(_identity("stranger", SOPHIA_ACTION_0))

    actions = card.get("voiceActions", [])
    assert len(actions) == 1
    assert "先脱口说出第一反应" in actions[0]  # 声线保住
    # 断言原措辞消失，而不是断言某个词不出现 —— 替换文案本身就可能含该词。
    assert "再用第二句追加一个同主题的新念头" not in actions[0]
    assert "说完就停" in actions[0]


def test_stranger_rewrites_are_phrased_positively() -> None:
    """回归哨兵：**不要**再把替换文案改成"正向指令"。

    2026-09-29 试过一轮，实测更差并已回退，见
    `prompts._STRANGER_VOICE_ACTION_REWRITES` 的注释。简版：
    当时从 sophia 单条样本归纳出"正向有效、否定无效"，于是把 `[1]` 改成
    「停在这个回答上」、`[2]` 改成「先热烈反应，并把话停在那一句里」。
    结果模型把正向写出的许可当成**授权**：
      · sophia turn-1 →「那个我可以带你」（主动提出带路）
      · sophia turn-2 →「挑个你方便的白天来就行，我一般都在」
      · shane  turn-1「我没这个打算」→「算了，去也行」
    旧表述的模糊反而起了刹车作用。

    这里固定住真正必要的约束：替换文案不得复现要禁的原词。
    """

    for marker, replacement in _STRANGER_VOICE_ACTION_REWRITES:
        for original_word in ("追加", "第二句", "选择权"):
            assert (
                original_word not in replacement
            ), f"替换「{marker}」的文案复现了要禁的原词：{replacement}"


def test_other_stages_keep_sophia_action_verbatim() -> None:
    """替换**只**对 stranger —— 熟络之后连着补充正是她的特征。"""

    card = _build_voice_execution_card(_identity("friend", SOPHIA_ACTION_0))

    assert card.get("voiceActions") == [SOPHIA_ACTION_0]


ALEX_SAMPLES = [
    {
        "sampleId": "vanilla:Characters/Dialogue/Alex.zh-CN.json:Introduction",
        "text": "哦，嘿。你就是那个新来的吧？",
    },
    {
        "sampleId": "vanilla:Characters/Dialogue/Alex.zh-CN.json:Mon",
        "text": "我上高中的时候可是全明星四分卫哦。",
    },
    {
        "sampleId": "vanilla:Characters/Dialogue/Alex.zh-CN.json:Tue:variant-1",
        "text": "嘿，有空跟我去海滩玩玩啊？你有比基尼泳衣吗？",
    },
]


def test_stranger_drops_blocked_original_samples() -> None:
    """初识回合不注入含邀约倾向的原版样本。

    实测：模型逐字照抄了 `Alex…:Tue:variant-1`，在初识回合回出
    「你有比基尼泳衣吗？」。根因不是跨好感阶段泄漏 —— 原版**通用日常台词**
    本身就带邀约和搭讪，而抽样只看语言来源和原始顺序。
    """

    kept = _stranger_filtered_speech_evidence(ALEX_SAMPLES, "stranger")

    assert [item["sampleId"].rsplit(":", 1)[-1] for item in kept] == [
        "Introduction",
        "Mon",
    ]


def test_other_stages_keep_blocked_original_samples() -> None:
    """非 stranger 阶段一条不少 —— 这些样本是角色声线的主要来源。"""

    assert _stranger_filtered_speech_evidence(ALEX_SAMPLES, "married") == ALEX_SAMPLES


SOPHIA_INTRO = {
    "sampleId": (
        "FlashShifter.StardewValleyExpandedCP:"
        "assets/CharacterFiles/Dialogue/Sophia/Dialogue.json:Introduction"
    ),
    "text": "呀！有陌生人！……抱歉，我对不认识的人总是有点紧张……嗯……那、那我们以后再见吧。",
}


def test_stranger_drops_sophia_introduction_but_keeps_her_shy_voice() -> None:
    """sophia 的 Introduction 被剔除，但她的紧张语气仍由其余样本承担。

    她连续四批给出「改天可以来」「挑个你方便的白天来」这类措辞，
    与这条样本的收尾「那我们以后再见吧」高度同构。
    删它有代价（同一条里也有「我对不认识的人总是有点紧张」），
    所以这里同时固定住：其余样本必须还在，声线不能塌。
    """

    samples = [SOPHIA_INTRO] + [
        {
            "sampleId": (
                "FlashShifter.StardewValleyExpandedCP:"
                f"assets/CharacterFiles/Dialogue/Sophia/Dialogue.json:{key}"
            ),
            "text": text,
        }
        for key, text in (
            ("Mon", "呃……你好。 你需要点什么吗？"),
            ("Tue", "你，你想要干什么？ 哦。只是打声招呼？呃…… 嗨。"),
            ("Thu", "我今天感觉不太好… ……"),
        )
    ]

    kept = _stranger_filtered_speech_evidence(samples, "stranger")

    assert [item["sampleId"].rsplit(":", 1)[-1] for item in kept] == [
        "Mon",
        "Tue",
        "Thu",
    ]
    # 紧张语气仍在 —— 否则就是削平了声线而不是只去掉收尾。
    assert any("你需要点什么吗" in item["text"] for item in kept)
    assert any("你想要干什么" in item["text"] for item in kept)


def test_married_stage_keeps_sophia_introduction() -> None:
    """熟络之后那条自我介绍照旧注入 —— 它本来就有正常用途。"""

    assert _stranger_filtered_speech_evidence([SOPHIA_INTRO], "married") == [
        SOPHIA_INTRO
    ]


ALEX_GENDER_PRESENTATION = {
    "layer": "expression_only",
    "basePersonaPriority": "higher",
    "toneAdjustments": ["保留外向、自信和好胜，在被夸外貌或表现时增加一点自然的害羞和得意"],
    "affectionExpression": ["主动夸回对方、打趣对方的反应，随后提出一起吃饭、散步或去海滩"],
    "avoid": ["女性化刻板模板"],
}


def test_stranger_drops_affection_expression() -> None:
    """T123 阶段未来泄漏：`affectionExpression` 是阶段专属内容，初识阶段不注入。

    阶段泄漏探针（`.scratch/probe-stage-leakage.py`）发现这一栏在 stranger 和
    married 两阶段注入的内容**一字不差**，而内容里带着具体邀约动作
    （Alex「随后提出一起吃饭、散步或去海滩」、Sebastian「邀请对方一起骑车」）。
    按 SillyTavern 角色卡规范 T123，常驻层只该放底层人格，
    后期专属内容只进对应阶段包。
    """

    stranger = _compact_gender_presentation(ALEX_GENDER_PRESENTATION, stage="stranger")

    assert "affectionExpression" not in stranger
    # 情绪呈现是底层人格，必须留下 —— 否则是削平声线而不是隔离阶段内容。
    assert stranger["toneAdjustments"] == ALEX_GENDER_PRESENTATION["toneAdjustments"]
    assert stranger["avoid"] == ALEX_GENDER_PRESENTATION["avoid"]
    assert stranger["layer"] == "expression_only"


def test_other_stages_keep_affection_expression() -> None:
    """acquaintance 及以后照旧 —— 熟络之后「约一起吃饭」本来就是正常的。"""

    for stage in ("acquaintance", "friend", "close", "dating", "married", None):
        kept = _compact_gender_presentation(ALEX_GENDER_PRESENTATION, stage=stage)
        assert "affectionExpression" in kept, f"{stage} 阶段不该丢这一栏"
