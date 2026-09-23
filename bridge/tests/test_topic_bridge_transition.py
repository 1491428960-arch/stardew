"""换面的「关联过渡」与「玩家短句」信号（2026-09-22）。

用户提的是一个**更深的设计问题**，不是"再加一个按钮"：

    「我们怎么自由切换话题……我个人是希望把这个主动权交到 NPC 手里，
      而不是一个话题聊到头了我点一下'找话题'，这个度怎么把握」

他抱怨的现状是**硬拐**：槽位说"这轮别谈酒了"，她就真的一拐到天气，中间没有过渡。
本次两半（已批准）：

* **A 关联过渡**：`topicSlot` 的 instruction 不再只下封口令，而是要求**先接住上一轮
  说过的具体东西，再从它拉一根线**出去。上一轮的原文是**代码从 history 里摘出来的**
  （`recent_replies[-1]` 的首句），不是让模型自己回忆 —— 模型的"上一轮"在 compact
  路径下只有 4 条可见，而槽位算在完整 history 上（见第 3 节）。
* **B 玩家短句信号**：读 history 里**玩家的最近一条回复**，很短且是敷衍类就**主动**换面，
  不需要玩家去点"找话题"。判据、防误判与理由见第 4、5 节。
* **⭐ 必须保住的一条**（用户明确关心）：她主动换出去之后，玩家继续聊原来那个，
  **她要能回来**。代码层是"玩家点名的面 → 槽位整体撤回"（第 6 节），
  措辞层是禁令括号里的那句豁免（第 7 节）。这条是**方向盘在玩家手里**的落点。

本文件刻意**不**复用 `test_topic_slot_rotation.py` 的 helper：那一份钉的是"槽位怎么算"，
这一份钉的是"槽位怎么说、什么时候说、什么时候闭嘴"。两组断言会随口径各自演化。
"""

from __future__ import annotations

import json

import pytest

from stardew_ai_bridge.stage_policy import (
    _LIFE_FACET_PATTERNS,
    rotation_topic_slot,
)

SOPHIA_MODS = ["vanilla", "SVE", "FlashShifter.StardewValleyExpandedCP"]
# 2026-09-23：索菲亚素材补到 5 面 6 条，本常量跟着同步（与
# `test_topic_slot_rotation.py::SOPHIA_TOPICS` 及 `data/personas/sve.json` 逐字一致）。
# 2026-09-24：第 2 条由「画布上还没画完的那一块」换成「给下一个角色扮演挑的布料」
# （SVE 里她的创作面是角色扮演／缝纫，不是绘画；面归属不变，仍在「工作或手艺」）。
# 2026-09-25：补到 **12 条 / 9 面全覆盖**，写法同时压短（`roleGuidance` 的 240 字
# 截断线卡着，不压短装不下 12 条）。与 `test_topic_slot_rotation.py::SOPHIA_TOPICS`
# 及 `data/personas/sve.json` 逐字一致。
SOPHIA_TOPICS = [
    "精灵石和矿石",
    "斯嘉丽和朋友们",
    "海边的咸风",
    "毯子和电视",
    "格斯做的菜",
    "独处时的孤独",
    "镇上的新鲜事",
    "蓝月亮的年份",
    "手工房的布料",
    "你今天要忙什么",
    "记得把头发染成粉色那天",
    "动漫展",
]

# **只覆盖两个面**的素材形状（2026-09-23 之前的索菲亚素材）：缺口角色的样子。
# "面刚用过就说'另一件事'"那条措辞分支只在它身上触发，所以回归必须用它来做。
NARROW_ROLE_TOPICS = [
    "酒窖里这一批新酿",
    "画布上还没画完的那一块",
    "镇上今天谁在广场上吵",
    "她刚搬来镇上时住的那间旧房子",
]

# 最近两轮都落在「工作或手艺」——正是用户实测的那个 case
BREW_REPLIES = [
    "刚把新酿的葡萄酒装进橡木桶，酒窖里全是葡萄的甜味。",
    "是啊，葡萄园的收成很好，我又酿了一批酒。",
]
TOWN_REPLY = "镇上广场那边今天有人吵架，围了一圈人。"
WEATHER_REPLY = "外面一直在下雨，我就在窗边坐了会儿。"


def _payload(npc: str, history: list[dict[str, str]], mods: list[str], **extra) -> dict:
    body = {
        "npcId": npc, "message": "今天过得怎么样？", "intent": "chat", "provider": "fake",
        "compactPrompt": True, "channel": "face_to_face",
        "sourceMods": mods, "recentFacts": [], "history": history,
        "gameState": {
            "npcId": npc, "displayName": npc, "gender": "Female", "location": "Town",
            "season": "spring", "date": "25", "weather": "clear", "time": 1200,
            "friendship": 1500, "friendshipHearts": 6, "relationship": "friend",
        },
    }
    body.update(extra)
    return body


def _turns(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    """`[(玩家, NPC), ...]` → 游戏端那种 user/assistant 交替的 history。"""

    items: list[dict[str, str]] = []
    for player, npc in pairs:
        items.append({"role": "user", "content": player})
        items.append({"role": "assistant", "content": npc})
    return items


def _card(messages: list[dict[str, str]], name: str) -> dict:
    for message in messages:
        if message.get("name") == name:
            return json.loads(message["content"])
    raise AssertionError(f"prompt 里没有 {name} 卡")


def _stage_card(body: dict) -> dict:
    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    context, _ = _build_context(body)
    return _card(
        PromptBuilder().build(context, body["message"], compact=True),
        "stage_execution_card",
    )


# --- 1. A 部分：换面必须带关联过渡 -------------------------------------------


def test_instruction_asks_to_bridge_from_the_last_specific_thing() -> None:
    """判据：instruction 里必须出现"从上一轮的具体东西拉一根线"这个动作。"""

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert "从它拉一根线" in slot["instruction"]
    assert "不要凭空跳过去" in slot["instruction"]


def test_instruction_quotes_the_previous_reply_verbatim() -> None:
    """过渡的起点是**代码摘出来的原文**，不是让模型自己回忆上一轮说了什么。

    引用的是**最近一条**回复里一个**完整**的短句（按句末标点取首句，超长再按逗号
    累积）—— 硬截会留下「是啊，葡萄园的收成很好，我又酿了」这种腰斩的引用，
    而恰恰是要模型"从它拉一根线"，它自己却是句断话。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert "上一轮你说过" in slot["instruction"]
    # 最近一条是 BREW_REPLIES[1]，首个分句完整保留、第二个分句放不下就停
    assert "是啊，葡萄园的收成很好" in slot["instruction"]
    assert "我又酿了一批酒" not in slot["instruction"]
    # 引号里的引用必须是完整分句，不许以逗号结尾（那是被截断的形状）
    quoted = slot["instruction"].split("「")[1].split("」")[0]
    assert not quoted.endswith("，")


def test_anchor_prefers_a_whole_short_sentence_over_a_truncated_one() -> None:
    """首句本身够短时整句引用 —— 不触发分句累积那条路径。"""

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], "刚把新酿装进橡木桶，酒窖里全是葡萄的甜味。"],
    )
    quoted = slot["instruction"].split("上一轮你说过：「")[1].split("」")[0]

    assert quoted == "刚把新酿装进橡木桶"


def test_instruction_no_longer_only_forbids() -> None:
    """旧版是纯封口令（"本轮不要再出现这一面的对象、动作或说法"）——正是"硬拐"的来源。

    这一条是**口径变更**的证据：旧句必须消失，新句必须在。改动本身写在
    `stage_policy.rotation_topic_slot` 的注释里。
    """

    instruction = rotation_topic_slot(
        SOPHIA_TOPICS, recent_replies=BREW_REPLIES
    )["instruction"]

    assert "本轮不要再出现这一面的对象、动作或说法" not in instruction
    assert "先接住" in instruction


@pytest.mark.parametrize(
    "kwargs",
    [
        {"recent_replies": BREW_REPLIES},
        {"recent_replies": BREW_REPLIES, "player_replies": ["嗯"]},
        {"recent_replies": BREW_REPLIES, "player_replies": ["嗯", "哦"]},
        {"recent_replies": [BREW_REPLIES[0], TOWN_REPLY, BREW_REPLIES[1]]},
        {"recent_replies": BREW_REPLIES, "player_replies": ["好的"]},
        {"recent_replies": [] , "player_replies": ["嗯"]},
        {"recent_replies": [BREW_REPLIES[0]], "player_replies": ["哦"]},
    ],
)
def test_every_instruction_fits_the_compact_whitelist_limit(kwargs: dict) -> None:
    """`_compact_stage_policy` 把 instruction 硬截断到 300 字符 —— 超了就是断句。

    参数字典覆盖**每一条措辞分支**（有/无建议面、有/无引用起点、单一/合并理由）。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, **kwargs)

    assert slot, kwargs
    assert len(slot["instruction"]) <= 300, (len(slot["instruction"]), kwargs)


def test_instruction_survives_the_compact_path_untruncated() -> None:
    """端到端：线上那张卡里的 instruction 与槽位产出的**逐字相同**（没被截）。"""

    body = _payload("Sophia", _turns([("聊点别的", BREW_REPLIES[0]),
                                      ("还有呢", BREW_REPLIES[1])]), SOPHIA_MODS)
    slot = _stage_card(body)["topicSlot"]

    assert len(slot["instruction"]) <= 300
    assert slot["instruction"].endswith("只说一件，不要罗列。") or slot[
        "instruction"
    ].endswith("不要罗列。")


def test_rendered_instruction_example() -> None:
    """渲染实例（文档价值：这是模型真正读到的那段话）。

    2026-09-22：禁令后面那段**括号从句**（"（玩家本轮自己点名的对象仍要接住…）"）
    移出去了 —— 它现在是 `slot["playerAnchor"]`，与 `instruction` **并列**的一级字段，
    措辞带"硬约束"。所以这里并排渲染两份，读的时候是一个整体：
    instruction 说"换面怎么换"，playerAnchor 说"什么不许被换掉"。

    2026-09-23：禁令句换成了**范例**（"这一面本轮先搁着——像这样换：「手上这件先这样
    ……对了，说起来」"）。这份实例是逐字对照的锚点，改文案时**必须**一起来改。

    2026-09-24 **去模板化**（见下一条测试）：范例由"固定一句"改成"四个候选按 anchor
    确定性轮换"，末句的「再用「对了」「说起来」拐到别的面」也跟着改成「再用**一个
    转折词**拐到别的面」——原句在同一句里把那个模板又强化了一遍。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert slot["trigger"] == "facetRepeat"
    assert slot["instruction"] == (
        "最近2轮里有2轮在谈「工作或手艺」这一面；"
        "上一轮你说过：「是啊，葡萄园的收成很好」。"
        "本轮先接住那里面的具体东西，再从它拉一根线过去、换到别的面，不要凭空跳过去。"
        "这一面本轮先搁着——像这样换：「……说起来，」，"
        "先把上一句收住，再用一个转折词拐到别的面，不要以同一面另起一件事。"
        "改从「家人朋友」这一面挑一件具体的、能落到对白里的小事来说"
        "（例如「斯嘉丽和朋友们」这个方向），只说一件，不要罗列。"
    )
    assert slot["playerAnchor"] == (
        "硬约束：玩家本轮点名的对象必须先接住、先应下来；"
        "他要接着聊那一面就顺着聊，换面不许绕开它、也不许一句带过。"
    )


def test_transition_example_rotates_instead_of_repeating_one_template() -> None:
    """过渡范例必须真的轮得动（2026-09-24 回归）。

    **背景（60 次云端实测）**：旧版只给一个范例「手上这件先这样……对了，说起来」，
    改后 `7b9aa33` 的 A/B 两组共 10 轮换面里，「对了，说起来」这一对**连用**出现在
    5 轮，形状二第 3、4、5 轮**连续三轮同款开场**，第 4、5 轮连内容都回环。
    —— 范例被当成了唯一模板照抄，把"有时硬拐"换成了"固定一个说法"。

    修法是**代码换、不由模型自觉**：每轮只注入一个范例，且优先挑最近两轮没用过的。
    这里钉四件事：避让生效、全用过时兜底不崩、兜底确定性、旧的那句连用不会回来。
    """

    from stardew_ai_bridge.stage_policy import (
        _TRANSITION_EXAMPLES,
        _transition_example,
    )

    examples = {text for _, text in _TRANSITION_EXAMPLES}

    # ① 最近一轮用过「对了」→ 本轮不能再给带「对了」的那个
    just_used = ["嗯，那杯我先留着。对了，说起来——刚搬来那阵子住的那间旧房子。"]
    picked = _transition_example("是啊，葡萄园的收成很好", just_used)
    assert picked in examples
    assert "对了" not in picked
    assert "说起来" not in picked

    # ② 四个都用过 → 兜底仍然返回候选之一，且**确定性**（不依赖 PYTHONHASHSEED）
    all_used = ["对了 说起来 哦，还有—— 话说回来，"]
    fallback = _transition_example("是啊，葡萄园的收成很好", all_used)
    assert fallback in examples
    assert fallback == _transition_example("是啊，葡萄园的收成很好", all_used)

    # ③ 零历史（`replies` 省略）仍返回候选之一，不炸
    assert _transition_example("") in examples

    # ④ 端到端：换面那一轮的 instruction 里只出现**一个**范例，且不是旧的连用
    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)
    assert "对了，说起来" not in slot["instruction"]
    assert sum(text in slot["instruction"] for text in examples) == 1


def test_a_topic_she_just_said_is_not_suggested_again() -> None:
    """方案 4（2026-09-24）：判面之外还要看「这条素材本身最近两轮说过没有」。

    **背景是云端实测的 A2 形状**（改后 `7b9aa33`，改前/改后各 5 轮）。第 4、5 轮她
    连说了两遍爆米花，而那句**判不出「吃喝」面** —— 素材条目「加了桦树糖浆的爆米花
    **食谱**」是靠"食谱"两个字判出面的，她说的「加了桦树糖浆的爆米花」判出来是空。
    于是 `_pick` 认为"吃喝这一面没用过"，第 5 轮把**同一条素材**又推荐了一遍。

    这里用的 4 条回复是**实测原文**（`.tmp/dq-verify/out/after-all.txt` 的 A2 前 4 轮）。
    """

    replies = [
        "还不错，刚从酒窖里出来，手上还都是橡木桶的味道。秋天这批新酿闻起来比我想的好，等一下——你要不要过来尝一小口？",
        "酒窖里那批新酿我还没贴标签，正想着怎么把秋天这股果香留在名字里。你提起来的这一杯，我倒想先问问你尝着像什么，再决定要不要分装给镇上的人。",
        "嗯，那杯我就先留着——对了，说起来刚搬来那阵子住的那间旧房子，窗户漏风，冬天我总窝在毯子里看电视。你哪天要是路过，我给你也留一小瓶。",
        "嗯，那杯我先留着。对了，说起来——加了桦树糖浆的爆米花，我前阵子试过一次，甜得有点意外。今天镇上倒是没什么大事，就广场上两个人为了摊位吵了几句，我看了一会儿就走了。",
    ]

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=replies)

    assert slot, "这 4 条应当触发 facetRepeat"
    # 旧写法在这里给出的正是「加了桦树糖浆的爆米花食谱」（离线复现过）。
    assert slot["suggestedTopic"] != "加了桦树糖浆的爆米花食谱"
    assert slot["suggestedTopic"]


def test_spoken_topic_detection_uses_bigrams_not_the_whole_entry() -> None:
    """判据本身：整条子串匹配在真实素材上**几乎不命中**，所以用的是 2-gram 覆盖率。"""

    from stardew_ai_bridge.stage_policy import _topic_already_spoken

    said = ["嗯，那杯我先留着。对了，说起来——加了桦树糖浆的爆米花，我前阵子试过一次。"]
    # 模型永远不会说出「食谱」那两个字 —— 整条子串匹配会漏掉一条明显用过的素材。
    assert "加了桦树糖浆的爆米花食谱" not in said[0]
    assert _topic_already_spoken("加了桦树糖浆的爆米花食谱", said) is True
    # 完全没提过的素材不能误杀。
    assert _topic_already_spoken("酒窖里这一批新酿", said) is False


def test_pick_falls_back_instead_of_returning_empty() -> None:
    """三级降级：连"没说过 + 最近没用过的面"都挑不出时，退回不排除那一轮，**不返回空**。

    素材只有两条、且两条都已经被她说过的极端形状。宁可重复一条，也不要像旧写法那样
    建议一个这个角色根本没有素材的面。
    """

    topics = [
        "酒窖里这一批新酿",
        "镇上今天谁在广场上吵",
        "记得刚搬来那阵子住的那间旧房子",
    ]
    replies = [
        "酒窖里这一批新酿刚封好。对了，镇上今天谁在广场上吵得厉害，我路过看了会儿。",
        "酒窖里这一批新酿我今早又尝了一口。记得刚搬来那阵子住的那间旧房子窗户漏风。",
    ]

    slot = rotation_topic_slot(topics, recent_replies=replies)

    assert slot, "应当仍有建议，不能返回空槽位"
    assert slot["suggestedTopic"] in topics


def test_consecutive_facet_switches_do_not_reuse_the_same_transition() -> None:
    """她连着换面时，代码给出的范例不能连着两轮同款。

    模拟的是**期望行为**：她照范例拐出去，于是回复里带上了刚给的那个过渡词。
    实测里连三轮同款正是这条形状出的问题，所以这里连跑 6 轮看相邻是否撞。
    """

    from stardew_ai_bridge.stage_policy import (
        _TRANSITION_EXAMPLES,
        _transition_example,
    )

    replies = [
        "刚把新酿的葡萄酒装进橡木桶，酒窖里全是葡萄的甜味。",
        "是啊，葡萄园的收成很好，我又酿了一批酒。",
    ]
    picked: list[str] = []
    for _ in range(6):
        example = _transition_example(replies[-1], replies)
        picked.append(example)
        marker = next(
            item for item in _TRANSITION_EXAMPLES if item[1] == example
        )[0]
        replies.append(f"嗯，那杯我先留着——{marker}，刚搬来那阵子住的那间旧房子。")

    assert all(a != b for a, b in zip(picked, picked[1:])), picked
    assert len(set(picked)) >= 3, picked


# --- 2. 回归：槽位本身的算法一个字没动 ---------------------------------------


def test_slot_still_bans_the_repeated_facet() -> None:
    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert slot["bannedFacet"] == "工作或手艺"
    # 2026-09-25：素材补到 12 条后，这一轮点名池中第一条未被禁的「斯嘉丽和朋友们」
    # （家人朋友面）—— 池首「精灵石和矿石」正是工作面、被禁令挡下。
    # 不变量是"禁了工作面、去了另一个面"。
    assert slot["suggestedFacet"] == "家人朋友"
    assert slot["suggestedTopic"] == "斯嘉丽和朋友们"


def test_slot_stays_silent_without_any_signal() -> None:
    """没有重复面、也没有玩家短句 —— 一个字都不进 prompt（零成本不变）。"""

    assert rotation_topic_slot(SOPHIA_TOPICS, recent_replies=[]) == {}
    assert rotation_topic_slot(
        SOPHIA_TOPICS, recent_replies=[BREW_REPLIES[0]]
    ) == {}
    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
    ) == {}


# --- 3. B 部分：玩家短句 → 她主动换面 ----------------------------------------


def test_player_short_reply_fires_even_without_a_repeated_facet() -> None:
    """用户要的正是这条：**不用**先聊到同一面重复，玩家敷衍一句她就自己换。

    三面各一轮（`facetRepeat` 不成立），玩家最后只回了「嗯」。
    """

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
        player_replies=["嗯"],
    )

    assert slot
    assert slot["trigger"] == "playerShortReply"
    assert "playerShortReply" in slot["trigger"]


def test_short_reply_trigger_does_not_ban_a_facet() -> None:
    """B 触发时没有"被禁的面"——它要的是**换一个落点**，不是封口。

    封口由 A 理由（同面重复）承担；B 理由凭空禁一面会把玩家正在聊的东西也压掉。
    """

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
        player_replies=["嗯"],
    )

    assert "bannedFacet" not in slot
    assert slot["suggestedTopic"]
    assert "不要再绕着刚才那一面打转" in slot["instruction"]


def test_both_reasons_merge_into_one_slot() -> None:
    """两条理由可以同时成立（连着谈酒 + 玩家回「哦」），合并成**一个**槽位。

    两个槽位并排就是本项目记过多次的"两个层级、模型挑最松的读法"。
    """

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=BREW_REPLIES,
        player_replies=["哦"],
    )

    assert slot["trigger"] == "facetRepeat+playerShortReply"
    assert slot["bannedFacet"] == "工作或手艺"
    assert "没接住你的话头" in slot["instruction"]


@pytest.mark.parametrize("reply", ["嗯", "哦", "是吗", "好的", "这样啊", "原来如此",
                                   "嗯嗯", "哦哦", "懂了", "确实", "是嘛", "行"])
def test_filler_replies_are_recognised(reply: str) -> None:
    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
        player_replies=[reply],
    )

    assert slot.get("trigger") == "playerShortReply", reply
    assert f"「{reply}」" in slot["instruction"]


# --- 4. 防误判：这三类**不许**被当成敷衍 -------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "嗯，你说得对",     # 短，且以敷衍词开头，但带**实义判断** —— 不是敷衍
        "好，那就这样",     # 同上：有决定
        "对，我也这么想",   # 同上：有认同内容
        "嗯，酒不错",       # 带具体对象
    ],
)
def test_short_but_substantive_replies_do_not_fire(reply: str) -> None:
    """判据不是"短 + 含敷衍词"，而是**整句由空转词拼成**（没有任何实词）。

    「嗯，你说得对」净化后是"嗯你说得对"——`你说得对` 切不出表中的任何一项，
    于是不判敷衍。这是本次刻意选的**保守方向**：漏判的代价只是"这一轮不换面"
    （回到现状），误判的代价是她对着玩家的**明确认同**硬换台。
    """

    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
        player_replies=[reply],
    ) == {}


@pytest.mark.parametrize(
    "reply",
    [
        "我不想聊这个",
        "不想说这个",
        "别问这个了",
        "算了，不聊了",
        "不聊这个了",
        "别说这个",
        "不想谈这个",
    ],
)
def test_explicit_refusal_is_not_read_as_a_filler(reply: str) -> None:
    """**明确拒绝 ≠ 敷衍**：这是本次最重要的防误判。

    拒绝要走角色自己的边界处理（`boundaryMode`：「被追问私人话题时给出边界并结束」），
    而"她主动换面"是**绕开**：玩家在划线，NPC 却像没听见一样换台，读起来既不尊重
    也不像本人。所以拒绝词表**优先于**短句判定，命中即整体不产出槽位。

    ⚠ 与下一条的区别：这里都是"**打住**"（玩家不想继续），不是"**要求换**"。
    """

    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=BREW_REPLIES,
        player_replies=[reply],
    ) == {}


@pytest.mark.parametrize(
    "reply", ["换个话题", "换一个话题", "说点别的", "聊点别的"]
)
def test_player_asking_for_a_new_topic_fires_without_the_filler_label(reply: str) -> None:
    """「换个话题」是**指令**不是敷衍：玩家已经把要求说出口了，她照着换就行。

    但理由句必须写成"玩家明确要你换个话题"——不能借"敷衍"这个标签：玩家很认真
    地在提要求，被代码判成"没接住"是错的因果。
    """

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
        player_replies=[reply],
    )

    assert slot["trigger"] == "playerAsksNewTopic"
    assert "明确要你换个话题" in slot["instruction"]
    assert "没接住你的话头" not in slot["instruction"]
    assert slot["suggestedTopic"]


def test_long_filler_is_not_a_short_reply() -> None:
    """长度闸不放开：用户的口径是"很短（≤6 字）**且**敷衍类"，两条都要满足。

    「哈哈哈是嘛原来是这样啊」确实是敷衍，但 12 个字 —— 长度本身就说明玩家还在
    打字、还在给内容，不该由代码替他判成"没话说了"。
    """

    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
        player_replies=["哈哈哈是嘛原来是这样啊"],
    ) == {}


def test_only_the_most_recent_player_reply_counts() -> None:
    """只认**最近一条**：玩家上一轮敷衍、这一轮认真说了话，不该再补一次换面。"""

    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
        player_replies=["嗯", "后来我去镇上看了看，广场上确实挺热闹的"],
    ) == {}


def test_missing_player_replies_keeps_the_old_behaviour() -> None:
    """老调用点（只传 `recent_replies`）行为不变 —— B 是**新增**触发条件。"""

    assert rotation_topic_slot(
        SOPHIA_TOPICS, recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY]
    ) == {}
    assert rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)


# --- 5. compact 的 4 条 history 够不够 ---------------------------------------


def test_player_short_reply_is_visible_in_the_compact_window() -> None:
    """**compact 4 条够用**，两个理由：

    ① 槽位算在 `ContextBuilder` 的 history（上限 12 条，游戏端实发 6 条
       —— `BridgeClient.MaxHistoryItems`）上，与 `PromptBuilder.build` 里
       那个 `-(4 if compact else ...)` 的**显示窗口无关**；
    ② 就算按 4 条算，玩家最近一条回复也在里面 —— 它紧挨着最后一条 NPC 回复，
       是最不容易滑出窗口的那一条。

    ⚠ 2026-09-22 修形状：本条原先构造的是「history 里含本轮的『嗯』+ `message`
    是一个无关问句」。**真机上不存在这个形状** —— 游戏端本轮走 `Message` 字段、
    `History` 里没有本轮（`BridgeClient.SendAsync` 的 `History = historyByNpc[...]`，
    本轮的 user 项要等 `RememberResult` 收到回复之后才写进去）。那个构造句恰好
    绕过了接线 bug：即使 `player_replies` 只读 history，它也能捡到那个「嗯」。
    现在改成真机形状：玩家那句「嗯」**只在 `message` 里**，history 只有已完成的两轮。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    history = _turns([
        ("今天忙什么", BREW_REPLIES[0]),
        ("还有呢", TOWN_REPLY),
    ])
    body = _payload("Sophia", history, SOPHIA_MODS, message="嗯")
    context, _ = _build_context(body)
    messages = PromptBuilder().build(context, body["message"], compact=True)

    # ① 槽位读到的是**本轮**那句「嗯」—— 它只存在于 payload 的 `message` 里
    slot = _card(messages, "stage_execution_card")["topicSlot"]
    assert slot["trigger"] == "playerShortReply"
    assert "「嗯」" in slot["instruction"]

    # ② 模型可见的历史确实被压到 4 条，而本轮玩家那句由 `player_input` 卡单独承载
    visible = [item for item in messages if item.get("name") == "conversation_history"]
    assert len(visible) == 4
    assert visible[-1]["role"] == "assistant"
    player_cards = [item for item in messages if item.get("name") == "player_input"]
    assert player_cards and player_cards[-1]["content"] == "嗯"


def test_signal_degrades_safely_when_the_window_has_no_player_line() -> None:
    """边界（**记录事实**）：连点两次「找话题」后 history 里全是 assistant。

    游戏端 `BridgeClient` 刻意不把 topic 请求的内部提示写进 history，所以
    history 可以连续出现两条 assistant。这里构造一个更极端的形状 —— 玩家那句
    已经**滑出 compact 的 4 条显示窗口**（它在第 1 位，窗口只带最后 4 条）：

    * 模型看不见玩家那句话（4 条全是 assistant）；
    * 但槽位读的是**完整** history，照样判得出 `playerShortReply`。

    这正是"compact 的 4 条够不够"这个问题的答案：**槽位不依赖那个窗口**。

    2026-09-22 补：本轮也走 topic（`message = ""`）—— 与真机一致。topic 是 NPC
    主动开口，没有"本轮玩家的话"，所以槽位退回读 history 里最后一条玩家行。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    history = [
        {"role": "user", "content": "嗯"},
        {"role": "assistant", "content": BREW_REPLIES[0]},
        {"role": "assistant", "content": WEATHER_REPLY},
        {"role": "assistant", "content": TOWN_REPLY},
        {"role": "assistant", "content": "刚烤好一炉面包，满屋都是黄油味。"},
    ]
    body = _payload("Sophia", history, SOPHIA_MODS, message="", intent="topic")
    context, _ = _build_context(body)
    messages = PromptBuilder().build(context, body["message"], compact=True)

    visible = [item for item in messages if item.get("name") == "conversation_history"]
    assert len(visible) == 4
    assert not any(item["role"] == "user" for item in visible), "前提变了：窗口里出现玩家行"
    slot = _card(messages, "stage_execution_card")["topicSlot"]
    assert slot["trigger"] == "playerShortReply"
    assert "「嗯」" in slot["instruction"]


# --- 6. ⭐ 能拉回来：玩家点名被禁面 → 槽位整体撤回 ---------------------------


def test_player_naming_the_banned_facet_cancels_the_slot() -> None:
    """**方向盘在玩家手里**的代码落点。

    她刚主动换出去（连着两轮谈酒 → 槽位要她换到镇上），玩家却把话拉回原来那个：
    「那批新酿到底怎么样了？」。此时**整轮撤回槽位**，而不是"接住但不许延伸"。

    为什么整体撤回而不是改措辞：撤回时 `narrow_topic_pool` 也不再摘那一面，
    于是 `roleGuidance` 的落点池里**酒的素材还在** —— 她回来时有东西可落。
    只改措辞的话，"别再谈这一面"仍然从池子里把她的落点抽走了。
    """

    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=BREW_REPLIES,
        player_replies=["那批新酿到底怎么样了？"],
    ) == {}


@pytest.mark.parametrize(
    "reply",
    [
        "酒窖里那批新酿到底怎么样了？",
        "你今天又去葡萄园了吗？",
        "画布上那块画完了没？",
    ],
)
def test_any_reply_landing_on_the_banned_facet_cancels_the_slot(reply: str) -> None:
    """判据是"玩家这条话落在被禁的那个生活面上"（复用 `_LIFE_FACET_PATTERNS`），
    不是"玩家提到某个具体词"——第二份词表会各自演化。"""

    slot = rotation_topic_slot(
        SOPHIA_TOPICS, recent_replies=BREW_REPLIES, player_replies=[reply]
    )

    assert slot == {}, reply


def test_player_on_another_facet_does_not_cancel_the_slot() -> None:
    """代价闸：玩家聊**别的**面不能顺手把换面也取消掉。

    否则"玩家说了任何实质内容"都变成撤回，机制退化成"只对敷衍的玩家换面"。
    """

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=BREW_REPLIES,
        player_replies=["今天镇上是不是有集市？"],
    )

    assert slot["bannedFacet"] == "工作或手艺"


def test_yielding_to_the_player_keeps_the_whole_topic_pool() -> None:
    """端到端：撤回的那一轮，`roleGuidance` 的落点池**四条都在**（包括酒）。

    这是"她能回来"的直接证据：槽位没产出 ⇒ 不摘面 ⇒ 池子里酒的素材还在。

    ⚠ 2026-09-22 修形状：本条原先把"玩家拉回"的那句放在 **history 的最后一个 user
    项**里，而 `message` 留着一个无关问句。真机上本轮只走 `message` —— 那个形状等价于
    "玩家这一轮问的是『今天过得怎么样？』、玩家拉回发生在一轮之前"，撤回自然不该生效。
    改成真机形状后，同一条断言才真的在测撤回。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    history = _turns([
        ("聊点别的", BREW_REPLIES[0]),
        ("还有呢", BREW_REPLIES[1]),
    ])
    body = _payload("Sophia", history, SOPHIA_MODS, message="那批新酿到底怎么样了？")
    card = _stage_card(body)

    assert "topicSlot" not in card
    guidance = card["conversationLead"]["roleGuidance"]
    for topic in SOPHIA_TOPICS:
        assert topic in guidance, topic

    # 对照：同一份 history，本轮玩家聊**别的**面 ⇒ 槽位照常在场、禁令照常生效。
    # 这一半排除"槽位没出来只是因为历史形状不对"这个替代解释。
    other = _build_context(
        _payload("Sophia", history, SOPHIA_MODS, message="今天镇上是不是有集市？")
    )
    other_card = _card(
        PromptBuilder().build(other[0], "今天镇上是不是有集市？", compact=True),
        "stage_execution_card",
    )
    assert other_card["topicSlot"]["bannedFacet"] == "工作或手艺"


def test_yield_is_not_granted_by_a_bare_character_the_facet_table_does_not_know() -> None:
    """**边界记录（不是 bug）**：玩家只喊一个"酒"字时撤回不成立。

    `_LIFE_FACET_PATTERNS` 的"工作或手艺"面收的是「酿造／新酿／酒窖／橡木桶」这类
    **做法与场景**词，不含孤立的"酒"（"酒馆"归"吃喝"面，加一个"酒"字会改掉既有映射）。
    所以这种情况落到**硬约束**上：`topicSlot.playerAnchor` 明写"玩家本轮点名的对象
    必须先接住…换面不许绕开它、也不许一句带过"（见第 7 节）。两层一起才是完整的
    "能拉回来"。

    2026-09-22：豁免从 instruction 的括号从句升成一级字段 `playerAnchor`，
    断言跟着换到那里；"酒"字仍然不在词表里这一条不变（下面的 `_facet_hits` 断言）。
    """

    from stardew_ai_bridge.stage_policy import _facet_hits

    assert _facet_hits("酒怎么样") == set()
    slot = rotation_topic_slot(
        SOPHIA_TOPICS, recent_replies=BREW_REPLIES, player_replies=["酒怎么样"]
    )
    assert slot
    assert "必须先接住" in slot["playerAnchor"]


# --- 7. 措辞层豁免：接住 + 跟随，而不是"接住但不许延伸" ----------------------


def test_instruction_lets_the_player_steer_the_old_topic() -> None:
    """"方向盘在玩家手里"从**从句**升成**一级硬约束**（2026-09-22）。

    旧版豁免有两个版本：先是「…但接住之后不要由你往这一面延伸」（在"玩家还想聊原来
    那个"的场景里恰恰拦路：她接住一句就不能再往下说），后改成括号里的「他要是继续
    追问这一面，就顺着他的方向聊」。后者语义对了，但**位置**还是从句 —— 夹在当时的
    禁令句（"别再以这一面做新的落点…都不算换"，2026-09-23 已换成范例式表述）
    之间，读起来是禁令的附注，而不是一条并列的要求。

    现在它是 `topicSlot.playerAnchor`：与 `instruction` 平级、措辞带"硬约束"、
    且**无条件**产出（B/C 理由触发的槽位也带着它）。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert "硬约束" in slot["playerAnchor"]
    assert "顺着聊" in slot["playerAnchor"]
    assert "不许绕开它" in slot["playerAnchor"]
    assert "不要由你往这一面延伸" not in slot["instruction"]
    assert "不要由你往这一面延伸" not in slot["playerAnchor"]


# --- 8. 三幕场景：她自己换出去，玩家拉回来，她接得住 -------------------------


def test_three_act_scenario_she_rotates_he_pulls_back() -> None:
    """用户关心的那条完整链路，一次跑完：

    ① 连着两轮谈酒 → 槽位触发，要求**带过渡**换到镇上；
    ② 玩家只回「嗯」→ 她**主动**再换一次（不用玩家点"找话题"）；
    ③ 玩家把话拉回酒 → 槽位**整体撤回**，落点池完整，她接得住。
    """

    # ① 关联过渡换面
    first = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)
    assert first["bannedFacet"] == "工作或手艺"
    assert "从它拉一根线" in first["instruction"]

    # ② 玩家短句 → 她主动换面（此时三面各一轮，没有重复面）
    second = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, WEATHER_REPLY],
        player_replies=["嗯"],
    )
    assert second["trigger"] == "playerShortReply"

    # ③ 玩家拉回来 → 撤回。
    # 真机形状：拉回的那句走**本轮 `message`**，history 里只有已完成的两轮
    # （2026-09-22 修；原先把拉回那句放在 history 末尾、message 留一个无关问句，
    #  那个形状在真机上不存在，等于没测到撤回）。
    pull_back = "那批新酿到底怎么样了？"
    third_history = _turns([
        ("聊点别的", BREW_REPLIES[0]),
        ("还有呢", BREW_REPLIES[1]),
    ])
    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], BREW_REPLIES[1]],
        player_replies=[pull_back],
    ) == {}
    card = _stage_card(
        _payload("Sophia", third_history, SOPHIA_MODS, message=pull_back)
    )
    assert "topicSlot" not in card
    assert "镇上的新鲜事" in card["conversationLead"]["roleGuidance"]


def test_suggestion_says_another_thing_when_the_facet_was_just_used() -> None:
    """**素材缺口下的措辞分支**（真实渲染时发现的）。

    只覆盖两个面的角色：三轮谈过两个面之后，`_pick` 的第一轮（不许用过的面）必然
    选空、退化到"允许回到用过的面"。此时若照旧说"改从这一面挑一件小事"，模型很可能
    把**刚才那件事**再说一遍 —— 字面换了面、体感没换。所以面刚用过时改说
    "挑**另一件**事，不要重复刚才那件"。

    2026-09-23：素材换成 `NARROW_ROLE_TOPICS`（只覆盖两面的形状）—— 索菲亚本人补到
    5 面之后已经不走这条分支了（她第三轮就有"过去的回忆"可去），但缺口角色还在走。
    """

    slot = rotation_topic_slot(
        NARROW_ROLE_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLY, BREW_REPLIES[1]],
        player_replies=["嗯"],
    )

    assert slot["suggestedFacet"] == "镇上或邻里"
    assert "挑**另一件**具体" in slot["instruction"]
    assert "不要重复刚才那件" in slot["instruction"]


def test_suggestion_keeps_the_plain_wording_for_a_fresh_facet() -> None:
    """代价闸：面是**新的**时候不许跟着变成"另一件事" —— 那会让指令含糊。"""

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=BREW_REPLIES,
        player_replies=["哦"],
    )

    assert slot["suggestedFacet"] == "家人朋友"
    assert "另一件" not in slot["instruction"]


def test_no_bridge_sentence_when_there_is_no_previous_reply() -> None:
    """边界：history 里压根没有她的上一轮（玩家开口第一句就是「嗯」）。

    这时**不写**过渡句 —— 没有可拉的那根线，"先接住上一轮的…"是一句读不通的
    指令。B 的触发与建议面照旧产出。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=[], player_replies=["嗯"])

    assert slot["trigger"] == "playerShortReply"
    assert "上一轮" not in slot["instruction"]
    assert "从它拉一根线" not in slot["instruction"]
    assert slot["suggestedTopic"]


# --- 9. 白名单：新字段不许静默消失 -------------------------------------------


def test_compact_card_keeps_the_trigger_field() -> None:
    """`_compact_stage_policy` 是白名单重建 —— 没列出的键**静默消失**。

    诊断线第一版就踩过这个（`topicSlot` 整块到不了模型）。`trigger` 是线上唯一
    能看出"这次是哪个理由触发的"的字段，必须显式过名单。
    """

    from stardew_ai_bridge.prompts import _compact_stage_policy

    policy = {
        "stage": "friend",
        "topicSlot": {
            "bannedFacet": "工作或手艺",
            "trigger": "facetRepeat",
            "instruction": "最近2轮里有2轮在谈「工作或手艺」这一面。",
            "suggestedFacet": "镇上或邻里",
            "suggestedTopic": "镇上今天谁在广场上吵",
        },
    }

    compact = _compact_stage_policy(policy, include_response_order=False)

    assert compact["topicSlot"]["trigger"] == "facetRepeat"
    assert compact["topicSlot"]["bannedFacet"] == "工作或手艺"


def test_live_card_reports_the_trigger() -> None:
    body = _payload("Sophia", _turns([("聊点别的", BREW_REPLIES[0]),
                                      ("还有呢", BREW_REPLIES[1])]), SOPHIA_MODS)

    assert _stage_card(body)["topicSlot"]["trigger"] == "facetRepeat"
