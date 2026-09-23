"""话题深度槽位：她自己重复时给什么、玩家催她继续说时给什么。

## 这个文件防什么

2026-09-24 实测（走 `app._build_context`，即游戏那条路）：

* **`intent=topic`（她自说自话）30 轮，6/29 轮与上一轮相似度 ≥0.5**，
  其中第 6 轮与第 5 轮是 **1.00（一字不差）**；「毯子+橡树掉叶+第一场雪」
  这一件事被端出来 6 次。
* **`intent=chat` 8 轮**没有逐字重复，但**每轮端出 2~3 件新事**，
  一个话题碰一下就跳，第 6 轮起出现元对话与讨好式罗列。

根因：`_topic_already_spoken` 筛的是「该建议哪条素材」，**管不到模型的复述**；
而纵向（同一话题往下走）**完全没有机制**。

加一张卡后实测：`topic` 路径相邻重复 **6/29 → 0/29**，`chat` 路径第 6 轮出现
「刚才我说的是毯子的事，但其实……我真正想说的是，能和你一起待着就很好」。

## 判据为什么不复用 `_is_short_filler_reply`

那个判据要求「**整句由空转词拼成**」，而「然后呢」「还有呢」带实义虚词、判不出来
—— 实测三组里 `playerShortReply` 一次都没触发。所以这里要一个更宽的
「玩家在催她继续」判据，但**只用于本槽位**，不动那个函数的语义。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.stage_policy import topic_depth_slot

#: 实测里那件被端出来 6 次的事，原文照抄。
_SNOW = (
    "我刚才把毯子往沙发这头又拽了拽，想找个更暖和的角度窝着。"
    "结果一抬头，发现窗外那棵橡树的叶子都快掉光了。……今年第一场雪，我们能一起看吗？"
)

#: 一件与 `_SNOW` 无关的事，用来在两条相同回复之间"隔开"。
_OTHER = "呀——我差点把针线盒打翻了！刚在缝一块新料子，颜色是上次你说的那种灰蓝。"


# --- 触发 A：她自己重复了自己 -----------------------------------------------


def test_repeating_herself_triggers_the_repeat_card() -> None:
    """一字不差地重说一遍 —— 实测里最刺眼的那种（相似度 1.00）。"""

    replies = [
        _SNOW,
        "呀——我差点把针线盒打翻了！刚在缝一块新料子。",
        _SNOW,
    ]

    slot = topic_depth_slot(replies, player_replies=[])

    assert slot["depthTrigger"] == "selfRepeat"
    assert "别再原样说一遍" in slot["instruction"]


def test_novel_replies_do_not_trigger_the_repeat_card() -> None:
    replies = [
        "我刚把一块紫水晶拿到窗边，对着光看里面那层纹路。",
        "嘿……我刚才把毯子往沙发这头又拽了拽。",
        "呀——我差点把针线盒打翻了！刚在缝一块新料子。",
    ]

    assert topic_depth_slot(replies, player_replies=[]) == {}


def test_one_reply_cannot_be_a_repeat() -> None:
    """只有一条回复、也没有跨窗口原文时，谈不上「重复自己」。"""

    assert topic_depth_slot([_SNOW], player_replies=[]) == {}


def test_a_repeat_further_back_than_the_window_is_still_caught() -> None:
    """**跨窗口**那一份必须参与判重。

    真机 history 被封顶在 6 条（约 3 轮），隔了三四轮的重复在窗口里根本看不见
    —— 实测 `prod2-topic` 第 15 轮重复了第 12 轮，而那时第 12 轮早已滑出窗口，
    槽位全程没触发。所以"更早的"要把 `spoken_replies` 也算进来。
    """

    window = [
        "我今天把葡萄园那边该收的收完了。",
        "毯子角被我卷得皱巴巴的，也不知道在等什么。",
        _SNOW,
    ]

    # 只看窗口时抓不到（前面几条与它无关）。
    assert topic_depth_slot(window, player_replies=[]) == {}

    # 把更早说过的那一条放进跨窗口原文里 —— 命中。
    slot = topic_depth_slot(window, player_replies=[], spoken_replies=[_SNOW])

    assert slot["depthTrigger"] == "selfRepeat"


def test_a_pair_of_short_replies_sharing_a_common_opener_is_not_a_repeat() -> None:
    """她惯用「我刚才把…」开头，不能因为句式像就判重复（假阳防线）。"""

    replies = [
        "我刚才把甜茶倒出来，还在冒着热气。你要是有空，我想端到手工房陪你聊一会儿。",
        "我刚才把亚麻布铺平了，手感有点糙，但染色后会变软的。你记得我把头发染成粉色那天吗？",
    ]

    assert topic_depth_slot(replies, player_replies=[]) == {}


# --- 触发 B：玩家在陪她聊同一件事 -------------------------------------------


@pytest.mark.parametrize("line", ["然后呢", "还有呢", "接着说", "继续说", "嗯", "哦", "真的？"])
def test_continuation_signals_trigger_the_depth_card(line: str) -> None:
    slot = topic_depth_slot(["我刚把甜茶倒出来，还冒着热气。"], player_replies=[line])

    assert slot["depthTrigger"] == "playerContinuation"
    assert "只谈一件事" in slot["instruction"]


@pytest.mark.parametrize("line", ["我们去镇上吧", "你今天要忙什么？", "斯嘉丽最近怎么样"])
def test_a_real_question_does_not_trigger_the_depth_card(line: str) -> None:
    """玩家自己带了新话题时，不许把她按在刚才那件事上 —— 方向盘在玩家手里。"""

    assert topic_depth_slot(["我刚把甜茶倒出来。"], player_replies=[line]) == {}


# --- 优先序与边界 -----------------------------------------------------------


def test_the_player_wins_when_both_would_fire() -> None:
    """两个触发同时成立时，**玩家的意图优先** —— 这一条是实测推翻设计的地方。

    2026-09-24 的顺序一度是 A（selfRepeat）在前。于是玩家每轮只说
    「嗯」「然后呢」的整段对话里，她收到的**一直是 A 的文案**
    ——「要么换一件确实没提过的，要么就着它往下走一层」。
    **她选了更容易的那条**：每轮端出一件新事
    （香橙鸡→动漫展→炖菜→酒窖→月光石→林中晶体），
    正是用户抱怨的「同一个话题聊不出不同的感觉」。

    玩家在催她继续说时，他要的是「接着讲」，不是「换一件」。
    """

    # 既在重复自己（两条一样的），玩家又在催 —— 必须走 B。
    slot = topic_depth_slot([_SNOW, _SNOW], player_replies=["然后呢"])

    assert slot["depthTrigger"] == "playerContinuation"
    assert "只谈一件事" in slot["instruction"]


def test_a_shared_sentence_shape_is_not_a_repeat() -> None:
    """**假阳防护**：她惯用「我刚才把…」开场，**句式像不等于内容重复**。

    实测 `prod3-chat` 里她每轮内容其实都不同（香橙鸡 / 动漫展 / 炖菜 / 酒窖 /
    月光石 / 林中晶体），却在 0.5 的门槛下被判成"每轮都在重复自己"。
    所以阈值单独定为 `_DEPTH_REPEAT_RATIO`，不复用素材那边的 0.5。
    """

    first = "我刚才把葡萄园那边的葡萄分拣完了，指甲缝里还染着紫色，今天可真够忙的。"
    second = "我刚才把手工房的布料都归了一遍，有一块灰蓝色的还留着没动，想织条围巾。"

    assert topic_depth_slot([first, second], player_replies=[]) == {}


def test_the_repeat_card_names_the_line_she_repeated() -> None:
    """**指认到具体哪一条** —— 这是实测逼出来的（2026-09-24）。

    两批共 54 轮里 `selfRepeat` 几乎每轮都触发、独立卡也每轮都发到了，
    可逐字重复依然密集。原因不是指令被无视，而是**它没有"没提过的"可挑**：
    `topic` 路径下模型看不到玩家输入、可见历史只有 6 条且全是她自己。
    抽象地说"别重复"，等于让它在回声里自己找出口 —— 指认到具体哪条它才动得了。
    """

    slot = topic_depth_slot([_SNOW, _OTHER, _SNOW], player_replies=[])

    assert slot["depthTrigger"] == "selfRepeat"
    # 引用了被重复那条的开头（保留标点，是给人看的）。
    assert "毯子往沙发这头" in slot["instruction"]
    assert "换一件具体的小事" in slot["instruction"]


def test_the_repeat_card_does_not_license_making_things_up() -> None:
    """**不许给编造的许可** —— 2026-09-24 `prod6-topic` 第 24 轮实测。

    那一轮她突然写成古风悬疑小说：「轩窗边，那株旧葡藤又落了一层薄灰……
    门锁换了。三把钥匙都在我手里，一把给了收葡萄的短工，一把埋在北坡那棵歪脖柳下」。
    根因是指令里那句「换到另一个人、**换到另一段时间**」——
    它把"换话题"读成了"换一个时空"，于是自由发挥。

    所以出路必须锚在**她真的经历过的具体小事**上，不能给时空留口子。
    """

    slot = topic_depth_slot([_SNOW, _SNOW], player_replies=[])
    instruction = slot["instruction"]

    assert "换到另一段时间" not in instruction
    assert "换到另一个人" not in instruction
    assert "最近真遇到过的" in instruction


def test_the_card_quotes_nothing_when_there_is_nothing_to_quote() -> None:
    """没有可引用的原文时不能留一个空引号 —— 那比不引用更糟。"""

    from stardew_ai_bridge.stage_policy import _self_repeat_instruction

    instruction = _self_repeat_instruction("")

    assert "「」" not in instruction
    assert "——就是" not in instruction


def test_player_refusal_suppresses_the_slot() -> None:
    """玩家在划边界时不压她 —— 那是 `boundaryMode` 的地盘。"""

    assert topic_depth_slot([_SNOW, _SNOW], player_replies=["我不想聊这个了"]) == {}


def test_no_replies_produces_nothing() -> None:
    assert topic_depth_slot([], player_replies=[]) == {}
    assert topic_depth_slot([], player_replies=["然后呢"]) == {}


def test_empty_and_blank_inputs_are_ignored() -> None:
    assert topic_depth_slot(["", "   "], player_replies=["  "]) == {}
    assert topic_depth_slot(None, player_replies=None) == {}
