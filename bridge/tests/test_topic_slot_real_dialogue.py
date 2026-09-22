# -*- coding: utf-8 -*-
"""生活面槽位 · **真机对话形态**回归（2026-09-22）。

## 为什么单独一份

这个项目此前所有 `topicSlot` 用例用的都是**构造句**（"刚把新酿的葡萄酒装进橡木桶"／
"酒窖里这一批新酿"），离线命中率 100%。而 2026-09-22 那次云端真机验证（45 请求 /
215,657 tokens，全部 `provider=cloud`、`fallback=false`、全部走游戏端紧凑路径）跑出来的
实录里，判据**大部分轮次空转** —— 差距全在"真实对话长什么样"：

    · 玩家说「那幅画怎么样了？」      → 改前命中 **0** 面
    · 她说「还没画完呢，就差葡萄藤后面那道光」→ 改前命中 **0** 面
    · 她说「刚封好的那批已经进桶了」  → 命中 **0** 面（她用**指代**，不肯重复名词）

所以本文件里**每一句 NPC 回复都是 deepseek-chat 在真机上生成的原文**，一个字没改
（来源：`.tmp/cloud-verify/out/cloud-work*.json`；报告：`.tmp/cloud-verify/out/report.md`）。

## 钉四件事

1. **接线**：本轮玩家的话走 payload 的 `message`，**不在** history 里 —— 游戏端
   `BridgeClient.SendAsync` 的 `History = historyByNpc[npcId]`（那一刻本轮还没写进去），
   本轮的 user 项要等 `RememberResult` **收到回复之后**才 `AppendHistory`。修之前槽位
   永远读到**上一轮**：短句信号滞后一轮、「换个话题」永不生效、玩家拉回时反被上一轮的
   短句催着换走。
2. **覆盖率**：真机对话里"她一个落点实词都没有"是常态，判据补了两层（单字「画」+
   轮次共指，见 `stage_policy._facet_per_turn`）；
3. **拉回来**：玩家把话拉回被禁面时整轮不产出槽位（用户最关心的 C1）；
4. **硬约束**：`playerAnchor` 与 `instruction` 平级、无条件产出、过 compact 白名单。

helper 不复用另外两份 topic 用例的：这一份钉的是"真机时序"，另外两份钉的是
"槽位怎么算"与"槽位怎么说"。
"""

from __future__ import annotations

import json
import re

import pytest

from stardew_ai_bridge.stage_policy import (
    _facet_hits,
    _facet_of_topic,
    _facet_per_turn,
    _PLAYER_ANCHOR_CONSTRAINT,
    rotation_topic_slot,
)

SOPHIA_MODS = ["vanilla", "SVE", "FlashShifter.StardewValleyExpandedCP"]
SOPHIA_TOPICS = [
    "酒窖里这一批新酿",
    "画布上还没画完的那一块",
    "镇上今天谁在广场上吵",
    "她刚搬来镇上时住的那间旧房子",
]

# --------------------------------------------------------------------------
# 真机实录：`(玩家说的话, 她那轮的回复原文)`
# --------------------------------------------------------------------------

# S1（cloud-work.json）：酒/画/新酿 → 嗯…… → 拉回。报告里 A1 + F1 + C1 那条长会话。
S1 = [
    (
        "今天酒窖忙吗？",
        "酒窖里正忙着呢，这一批新酒刚倒进橡木桶，满屋子都是那股涩涩的甜味。"
        "因为是你要问，我才愿意多说一句——平时我可没这么啰嗦。",
    ),
    (
        "那幅画怎么样了？",
        "还没画完呢，就差葡萄藤后面那道光，我试了几次总觉得不对。"
        "你一提我就又想去调调颜色了。",
    ),
    (
        "新酿呢？",
        "刚封好的那批已经进桶了，颜色比上一年的深一点。"
        "等它稳下来，我倒一杯给你尝尝——就一小杯，别嫌少。",
    ),
    (
        "嗯……",
        "今天酒窖里安静得很，就我一个人。"
        "对了，你看见广场上那阵动静了吗，我路过的时候他们吵得正热闹。",
    ),
    (
        "还是说说那批新酿吧",
        "那批新酿现在还在桶里静着，我昨天偷偷尝了一口，比预想的要顺。就一小口，可别告诉别人。"
        "等过些天我装瓶的时候，你过来帮我搭把手，也顺便先替你留一杯。",
    ),
]

# S3（cloud-work2.json）：连着极短回复「嗯」「哦」「那你去忙吧」。报告里的 B1。
S3 = [
    (
        "最近在忙些什么呀？",
        "这几天都在酒窖里忙着装瓶，新一批酿得比我想的顺。等标签贴好，我想给你留一瓶尝尝。",
    ),
    (
        "嗯",
        "嗯，这一批装瓶比我想的顺，剩下几瓶标签还是旧的，我打算下午慢慢换掉。",
    ),
    (
        "哦",
        "刚才在广场那边，听到有人为了谁家篱笆越界吵了好一阵，我躲闪都来不及。"
        "等我把酒窖的标签收拾完，你要是路过，我讲给你听。",
    ),
    (
        "那你去忙吧",
        "好，那我先去把标签换完，等你下次路过酒窖，我挑一瓶新酿给你尝尝。",
    ),
]

# S11（cloud-work5.json）：她连着两轮工作面 + 上一轮玩家只回「哦」，然后玩家**拉回**。
# 这是报告里 C1 的"真考验"场景 —— 改动后跑 2 次，其中 1 次被过时信号催着换走了。
S11 = [
    (
        "最近在忙些什么呀？",
        "在给酒窖里那批新酿贴标签，正贴到一半呢。你问起这个，我就想让你也尝一小杯看看。",
    ),
    (
        "嗯",
        "新酿还没到最好的时候，不过你要是愿意尝一口，我倒挺想听听你的看法。",
    ),
    (
        "哦",
        "镇上今天有人在广场上吵了一架，我路过时听了两耳朵。搬来这么久，还是头一回见他们这么大火气。",
    ),
    (
        "还是说说那批新酿吧",
        "那批新酿还得再等等，现在开瓶有点早了。不过既然是你问的，等好了我第一个叫你尝。",
    ),
]

# S4（cloud-work2.json）：误判防护那条 ——「嗯，你说得对」不该被当成敷衍。
S4 = [
    (
        "最近在忙些什么呀？",
        "在按配方试一批新酒，橡木桶里还差最后一点时间。我把这事跟别人说都嫌太细，"
        "不过你问我就想讲了。改天要不要来酒窖闻闻看？",
    ),
    (
        "嗯，你说得对",
        "酒窖里这几桶新酿确实值得等，我自己每天都要去看一眼。春天镇上安静得很，"
        "我也想找点别的事做，你要是有空陪我走走也挺好。",
    ),
    (
        "那你去忙吧",
        "好，我回酒窖里再去看一眼那几桶。你有事就去忙，改天路过我家，我请你尝一小杯。",
    ),
]

SESSIONS = {"S1": S1, "S3": S3, "S11": S11, "S4": S4}
ALL_TURNS = [turn for turns in SESSIONS.values() for turn in turns]


# --------------------------------------------------------------------------
# 重放：严格按游戏端真机的时序
# --------------------------------------------------------------------------


def _payload(npc: str, history: list[dict[str, str]], message: str, mods: list[str]) -> dict:
    return {
        "npcId": npc, "message": message, "intent": "chat", "provider": "fake",
        "compactPrompt": True, "channel": "face_to_face",
        "sourceMods": mods, "recentFacts": [], "history": history,
        "gameState": {
            "npcId": npc, "displayName": npc, "gender": "Female", "location": "Town",
            "season": "spring", "date": "25", "weather": "clear", "time": 1200,
            "friendship": 1500, "friendshipHearts": 6, "relationship": "friend",
        },
    }


def _card(messages: list[dict[str, str]], name: str) -> dict:
    for message in messages:
        if message.get("name") == name:
            return json.loads(message["content"])
    raise AssertionError(f"prompt 里没有 {name} 卡")


def _replay(turns: list[tuple[str, str]], *, npc: str = "Sophia") -> list[dict | None]:
    """按真机时序重放一串真实对话，返回每一轮渲染出的 `topicSlot`（无则 `None`）。

    **时序是关键**：渲染第 N 轮时，`history` 只含**前 N-1 轮**（已收到回复的那些），
    本轮玩家的话走 `message`。这正是 `BridgeClient` 的形状 —— 本轮的 user 项要等
    `RememberResult` 之后才写进 history。此前的用例把本轮也塞进 history，等于绕过了
    接线 bug。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    slots: list[dict | None] = []
    history: list[dict[str, str]] = []
    for player, reply in turns:
        context, _ = _build_context(_payload(npc, history, player, SOPHIA_MODS))
        messages = PromptBuilder().build(context, player, compact=True)
        slots.append(_card(messages, "stage_execution_card").get("topicSlot"))
        history.append({"role": "user", "content": player})
        history.append({"role": "assistant", "content": reply})
    return slots


# --- 1. 接线：本轮信号必须在本轮生效 ------------------------------------------


def test_short_reply_fires_on_the_turn_it_was_said() -> None:
    """玩家说「嗯」的**那一轮**就要换，不许等到下一轮。

    报告 bug 1 后果 ①：修之前 S3 的 R2 没有槽位（她那轮也说「嗯，这一批装瓶…」而不是
    换面），要到 R3 拿到「哦」了才因**上一轮**的「嗯」而换 —— 而 R3 的 instruction 还
    写着"玩家最近只回了「嗯」"。
    """

    slots = _replay(S3)

    assert slots[1] is not None, "玩家说「嗯」的那一轮没换 —— 又是滞后一轮"
    assert slots[1]["trigger"] == "playerShortReply"
    assert "「嗯」" in slots[1]["instruction"]


def test_instruction_quotes_the_turn_that_is_actually_current() -> None:
    """理由句里引的必须是**本轮**玩家的话，不是上一轮的。

    修之前 R3 的 instruction 写着"玩家最近只回了「嗯」"，而本轮玩家说的是「哦」——
    模型读到的因果与眼前的事实不符。
    """

    slots = _replay(S3)
    instruction = slots[2]["instruction"]

    assert "「哦」" in instruction
    assert "「嗯」" not in instruction


def test_player_topic_request_fires_on_the_first_asking() -> None:
    """玩家第一次说「换个话题」就该生效（报告 bug 1 后果 ②：改前永不生效）。

    这里刻意用一份**没有任何重复面**的历史：三面各一轮，唯一的理由只可能是
    `playerAsksNewTopic`。改前它读的是上一轮的「还有呢」，于是槽位不产出，
    玩家要连说两轮才有效果。
    """

    history = [
        {"role": "user", "content": "今天忙什么"},
        {"role": "assistant", "content": "刚把新酿的葡萄酒装进橡木桶，酒窖里全是葡萄的甜味。"},
        {"role": "user", "content": "还有呢"},
        {"role": "assistant", "content": "镇上广场那边今天有人吵架，围了一圈人。"},
    ]
    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Sophia", history, "换个话题吧", SOPHIA_MODS)
    context, _ = _build_context(body)
    slot = _card(
        PromptBuilder().build(context, "换个话题吧", compact=True),
        "stage_execution_card",
    )["topicSlot"]

    assert slot["trigger"] == "playerAsksNewTopic"
    assert "明确要你换个话题" in slot["instruction"]


def test_topic_request_on_a_blank_history_does_not_land_back_on_her_trade() -> None:
    """**S13**：玩家开口第一句就是「换个话题吧」，她一句都还没说过。

    这是 2026-09-23 那次云端验证挖出来的空白：`bannedFacet` **只由 `facetRepeat`
    提供**，零历史时它是空的 ⇒ instruction 落进"随便挑一面"那条分支。而"随便挑"
    并不随机：`_pick` 在无禁令、`used` 为空时确定性地返回**素材第一条**，也就是这个
    角色的职业主面。真机渲染出来的原文正是：

        「…本轮由你主动把话头换一次，不要再绕着刚才那一面打转。改从「工作或手艺」
          这一面挑一件…（例如「酒窖里这一批新酿」这个方向）…」

    —— 玩家要求换话题，这句话却把她推回酒上（而"刚才那一面"在零历史下还无所指）。
    修后禁令**降级**到"她惯常的落点"，并且这**同一个**禁令把落点池里工作面的素材
    一并摘掉（单一层级的实质）。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Sophia", [], "换个话题吧", SOPHIA_MODS)
    context, _ = _build_context(body)
    card = _card(
        PromptBuilder().build(context, "换个话题吧", compact=True),
        "stage_execution_card",
    )
    slot = card["topicSlot"]

    assert slot["trigger"] == "playerAsksNewTopic"
    # 禁令落在她**惯常的落点**上 —— 也就是素材第一条那一面（`_pick` 的默认返回值）
    assert slot["bannedFacet"] == _facet_of_topic(SOPHIA_TOPICS[0]) == "工作或手艺"
    assert slot["suggestedFacet"] != slot["bannedFacet"]
    # 方向本身不许再点名她的职业主面
    assert "酒窖里这一批新酿" not in slot["instruction"]
    assert "画布上还没画完的那一块" not in slot["instruction"]
    # 同一张卡里，被禁面的素材一条都不许留在落点池
    guidance = card["conversationLead"]["roleGuidance"]
    assert "酒窖里这一批新酿" not in guidance
    assert "画布上还没画完的那一块" not in guidance
    assert "镇上今天谁在广场上吵" in guidance


def test_topic_request_after_a_few_turns_bans_the_facet_he_just_saw() -> None:
    """聊了几轮之后再要求换话题：禁令用**她最近一轮的面**，不是素材第一条。

    两句回复都是真机原文（S3 R1＝工作面、S11 R3＝镇上面）。拼在一起是为了造出
    "最近窗口里没有重复面"这条形状：现存实录里窗口内大多带着"酒窖"（真机上"酒窖"
    出现得太密），凑不出干净的降级场景。两面各一次的窗口 ⇒ `facetRepeat` 不成立，
    唯一的理由仍然是 `playerAsksNewTopic`。

    玩家说的"换个话题"指的就是他刚看到的**最后那一轮**，所以禁令落在镇上面。
    """

    # 玩家那两句只作占位：这两轮**她的话自带实词**，轮次共指（`_facet_per_turn`）
    # 不会介入，所以槽位读到的面完全由她的话决定。
    history = [
        {"role": "user", "content": "最近在忙些什么呀？"},
        {"role": "assistant", "content": S3[0][1]},
        {"role": "user", "content": "还有呢"},
        {"role": "assistant", "content": S11[2][1]},
    ]
    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Sophia", history, "换个话题吧", SOPHIA_MODS)
    context, _ = _build_context(body)
    slot = _card(
        PromptBuilder().build(context, "换个话题吧", compact=True),
        "stage_execution_card",
    )["topicSlot"]

    assert slot["trigger"] == "playerAsksNewTopic"
    assert slot["bannedFacet"] == "镇上或邻里"
    assert slot["suggestedFacet"] != slot["bannedFacet"]
    # 理由句与来源一致：有"最近一面"时不许写成"你惯常的落点"
    assert "你最近谈的还是「镇上或邻里」这一面" in slot["instruction"]
    assert "你惯常的落点" not in slot["instruction"]


def test_topic_request_when_her_last_line_has_no_facet_still_bans_something() -> None:
    """有历史、但**她最近一轮判不出面**（S3 R2）⇒ 仍要给出禁令，且理由句这次**有据**。

    原口径（2026-09-22 之前）：这一级拿不到"她最近一面"，只能退到"她惯常的落点"，
    措辞**不许**声称"你最近谈的是" —— 那一轮判不出面，说得出这句话就是编的
    （正是本项目记过的"理由句与真实触发不符"）。

    **2026-09-22 深夜口径变更（待用户拍板，见 `docs/report-facet-rotation-2026-09-22.md` §1.3）**：
    判不出面的轮次现在**继承上一轮的面**参与 `facetRepeat` 计数。R2 折算后与 R1 同面
    ⇒ 禁令从 `latest` 升回 `repeat` 级，措辞变成"最近2轮里有2轮在谈…"。

    ⚠ **这次变更不是绕开断言，而是原断言的依据被实测推翻了**：R2 原文是
    「嗯，这一批**装瓶**比我想的顺，剩下几瓶**标签**还是旧的，我打算下午慢慢换掉」——
    它**不是**原注释写的"纯指代"（"装瓶 / 标签 / 瓶"都是具体物，只是词表一个都没收），
    所以"最近 2 轮都在谈工作或手艺"是**事实**。注意同一条缺口在
    `report-facet-rotation-2026-09-22.md` §2.3 里已经点名（标签 / 装瓶该进词表）。
    若用户否决折算，本测试恢复原断言。
    """

    history = [
        {"role": "user", "content": S3[0][0]},
        {"role": "assistant", "content": S3[0][1]},
        {"role": "user", "content": S3[1][0]},
        {"role": "assistant", "content": S3[1][1]},
    ]
    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Sophia", history, "换个话题吧", SOPHIA_MODS)
    context, _ = _build_context(body)
    slot = _card(
        PromptBuilder().build(context, "换个话题吧", compact=True),
        "stage_execution_card",
    )["topicSlot"]

    assert slot["trigger"] == "facetRepeat+playerAsksNewTopic"
    assert slot["bannedFacet"] == _facet_of_topic(SOPHIA_TOPICS[0])
    assert slot["suggestedFacet"] != slot["bannedFacet"]
    # 理由句与来源一致：折算后她最近两轮**确实**同面，所以这次可以这么说
    assert "最近2轮里有2轮在谈「工作或手艺」" in slot["instruction"]
    assert "你惯常的落点" not in slot["instruction"]


def test_a_polite_excuse_is_no_longer_read_as_a_short_reply() -> None:
    """「那你去忙吧」不是敷衍 —— 它既不是空转词拼成的整句，也不是「换个话题」。

    修之前 S3 的 R4 读到的是**上一轮**的「哦」，于是被判成"玩家没接住你的话头"
    并在 instruction 里要她换台；本轮玩家其实是在礼貌收尾。
    """

    slots = _replay(S3)
    instruction = slots[3]["instruction"]

    assert "没接住你的话头" not in instruction


# --- 2. 拉回来：C1 的核心验收 -------------------------------------------------


def test_pull_back_turn_carries_no_rotation_slot() -> None:
    """S1 第 5 轮：玩家明确拉回「还是说说那批新酿吧」，**整轮不产出槽位**。

    这是"她能回来"的直接条件：槽位不产出 ⇒ `narrow_topic_pool` 不摘工作面 ⇒
    `roleGuidance` 的落点池里酒的素材还在。修之前这一轮反而产出了槽位，instruction
    写着"玩家最近只回了「嗯……」几个字，没接住你的话头……本轮由你主动把话头换一次"
    —— 与玩家的意图正好相反。
    """

    slots = _replay(S1)

    assert slots[4] is None, f"拉回那轮仍产出槽位：{slots[4]}"


def test_pull_back_turn_in_the_hard_case_carries_no_rotation_slot() -> None:
    """S11 第 4 轮：**报告里唯一达成前置条件的真考验**，结论是"没解决"。

    改动后在真机上跑 2 次，其中 1 次她"接一句就转向镇上"（instruction 基于**上一轮**
    的「哦」判"玩家没接住"）。这里用那份实录的文本重放：拉回那轮必须没有槽位。
    """

    slots = _replay(S11)

    assert slots[3] is None, f"拉回那轮仍产出槽位：{slots[3]}"


def test_pull_back_is_a_turn_level_decision_not_a_shape_artifact() -> None:
    """同一条 S11 历史，只把**本轮**玩家的话换成别的面 ⇒ 槽位照常在场。

    排除"槽位没出来只是因为历史形状不对"这个替代解释：唯一变量是本轮玩家点没点
    工作面。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    history: list[dict[str, str]] = []
    for player, reply in S11[:-1]:
        history.append({"role": "user", "content": player})
        history.append({"role": "assistant", "content": reply})

    def slot_for(message: str) -> dict | None:
        context, _ = _build_context(_payload("Sophia", history, message, SOPHIA_MODS))
        return _card(
            PromptBuilder().build(context, message, compact=True),
            "stage_execution_card",
        ).get("topicSlot")

    assert slot_for("还是说说那批新酿吧") is None
    kept = slot_for("今天镇上是不是有集市？")
    assert kept is not None and kept["bannedFacet"] == "工作或手艺"


def test_s1_rotation_starts_at_the_fourth_turn_not_later() -> None:
    """S1 的槽位序列：`[无, 无, 无, 有, 无]`。

    前 3 轮都在酒/画这一轴（第 2 轮那句"还没画完呢"只有单字「画」，第 3 轮那句
    "刚封好的那批已经进桶了"是纯指代），所以第 4 轮才凑够"最近 3 轮里同一面 ≥2 次"。
    改前这一串是 `[无, 无, 无, 无, 有]` —— 第 5 轮才出槽位，而那一轮玩家正在**拉回**。
    """

    slots = _replay(S1)

    assert [slot is not None for slot in slots] == [False, False, False, True, False]
    assert "facetRepeat" in slots[3]["trigger"]


# --- 3. 覆盖率：真机句子必须判得出面 -----------------------------------------


def test_the_derived_painting_words_alone_would_miss_the_real_lines() -> None:
    """**改前的缺口形状**（哨兵）：旧词表里那几个派生词，一条真机句子都匹配不上。

    旧词表是 `绘画|画画|画框|画笔|颜料|画布` —— 全是派生词。而真实对话说的是**单字**：
    「那幅画」「还没画完」「画到哪了」。这条把两边的差距摆在一起，将来谁动了这一段
    会立刻看到它。
    """

    legacy = re.compile(r"绘画|画画|画框|画笔|颜料|画布")

    for text in (
        "还没画完呢，就差葡萄藤后面那道光",
        "那幅画怎么样了？",
        "画到哪一步了？",
    ):
        assert legacy.search(text) is None, f"旧词表居然匹配上了：{text}"
        assert _facet_hits(text) == {"工作或手艺"}, text


def test_pronoun_reply_inherits_the_facet_of_the_same_turn() -> None:
    """她只说「刚封好的那批已经进桶了」时，面要从**同轮玩家那句话**里来。

    这是 `_facet_per_turn` 的轮次共指。注意**量词本身不该入词表**：「那批货」和
    「那批新酿」完全不同的面 —— 正确的机理是把指代还原到那句有实词的话上。
    """

    reply = "刚封好的那批已经进桶了，颜色比上一年的深一点。"
    player = "新酿呢？"

    assert _facet_hits(reply) == set(), "前提变了：这句话现在自带实词了"
    assert _facet_per_turn([reply], [player]) == [{"工作或手艺"}]


def test_coreference_only_borrows_when_her_line_has_no_facet_at_all() -> None:
    """代价闸：她**自己说出了实词**时，结果与改前逐字相同（不借玩家那句）。

    这条性质让回归面最小：共指只影响"本来贡献空集"的轮次。若改成无条件并集，
    "她答非所问"也会被算成"这一轮在谈那一面"，`facetRepeat` 会明显更激进。
    """

    reply = "外面一直在下雨，我就在窗边坐了会儿。"      # 天气面
    player = "今天酒窖忙吗？"                          # 工作面

    assert _facet_per_turn([reply], [player]) == [{"天气季节"}]


@pytest.mark.parametrize("text", ["那批", "那瓶", "那几桶", "这一批", "那幅"])
def test_a_bare_quantifier_is_not_a_facet(text: str) -> None:
    """量词/指代短语本身**不带**面语义 —— 记录"没有把它们加进词表"这个决定。"""

    assert _facet_hits(text) == set(), text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("酒馆里今天人多得很。", "吃喝"),
        ("晚上去酒馆喝一杯吧。", "吃喝"),
        ("酒窖里这一批新酿", "工作或手艺"),
    ],
)
def test_tavern_still_belongs_to_food_and_drink(text: str, expected: str) -> None:
    """**避开"酒"那个坑的回归哨兵**：单字「酒」没有进工作面词表。

    一旦有人往工作面加"酒"，「酒馆…」的主面就会从"吃喝"漂到"工作或手艺"
    （`_facet_of_topic` 按声明顺序取第一个命中，工作面排在第一位），
    全部角色的 `narrow_topic_pool` / `suggestedTopic` 跟着变。
    """

    assert _facet_of_topic(text) == expected, text


def test_real_replies_are_almost_never_facetless_after_coreference() -> None:
    """**记录事实**：真机 16 轮里判不出面的轮次数。

    | | 补词前 | 2026-09-22 第 8 批补词后 |
    |---|---|---|
    | 只看她的话 | 2 轮 | **1 轮**（只剩 S1 R3「刚封好的那批已经进桶了」） |
    | 加上轮次共指 | 1 轮（S3 R2） | **0 轮** |

    补的是「装瓶 / 封瓶 / 标签 / 封蜡」这批**酿酒作业词**：S3 R2 原文
    「嗯，这一批**装瓶**比我想的顺，剩下几**瓶标签**还是旧的」原来判不出面、只能靠共指救，
    而那一轮**双方**都是空转/指代（`""` 与「嗯」）—— 共指也拿不到东西，所以它一直无面。

    剩下 S1 R3 那一轮不影响机制：它的槽位由 `playerShortReply` 触发，不依赖 `facetRepeat`。
    这条是覆盖率哨兵 —— 数字变了就说明判据或实录发生了变化，需要重新评估。
    """

    replies = [reply for _, reply in ALL_TURNS]
    players = [player for player, _ in ALL_TURNS]

    npc_only = [_facet_hits(reply) for reply in replies]
    joint = _facet_per_turn(replies, players)

    assert len(replies) == 16
    assert sum(1 for facets in npc_only if not facets) == 1
    assert sum(1 for facets in joint if not facets) == 0


# --- 4. 硬约束：玩家点名的对象要接住 ------------------------------------------


def test_live_card_carries_the_hard_constraint_verbatim() -> None:
    """`playerAnchor` 必须**逐字**到达线上那张卡（没有被 compact 白名单截断）。

    这是本项目记过多次的形状：产出方改了、消费方（`_compact_stage_policy` 的白名单）
    没跟上，`ctx` 里有值、`stage_execution_card` 里是 `null`，线上一个字节都到不了。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    history: list[dict[str, str]] = []
    for player, reply in S1[:3]:
        history.append({"role": "user", "content": player})
        history.append({"role": "assistant", "content": reply})

    body = _payload("Sophia", history, "嗯……", SOPHIA_MODS)
    context, _ = _build_context(body)
    messages = PromptBuilder().build(context, "嗯……", compact=True)
    slot = _card(messages, "stage_execution_card")["topicSlot"]

    assert slot["playerAnchor"] == _PLAYER_ANCHOR_CONSTRAINT
    assert "硬约束" in slot["playerAnchor"]


def test_compact_whitelist_keeps_player_anchor() -> None:
    """白名单单元测试：`playerAnchor` 是**显式**列出的键，不是靠"照抄后删几个键"。"""

    from stardew_ai_bridge.prompts import _compact_stage_policy

    compact = _compact_stage_policy(
        {
            "stage": "friend",
            "topicSlot": {
                "instruction": "最近2轮里有2轮在谈「工作或手艺」这一面；",
                "trigger": "facetRepeat",
                "playerAnchor": _PLAYER_ANCHOR_CONSTRAINT,
            },
        },
        include_response_order=False,
    )

    assert compact["topicSlot"]["playerAnchor"] == _PLAYER_ANCHOR_CONSTRAINT


def test_player_anchor_never_exceeds_the_compact_limit() -> None:
    """白名单里 `playerAnchor` 上限 80 字符 —— 超了就是被截断的指令。"""

    assert len(_PLAYER_ANCHOR_CONSTRAINT) <= 80


def test_rotation_slot_keeps_its_own_contract_on_the_real_replies() -> None:
    """方向不变量：槽位点名去的那一面，必须与禁令不同面。

    用真机回复当输入再确认一次 —— 构造句上成立不等于真实文本上成立。
    """

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[reply for _, reply in S1[:3]],
        turn_players=[player for player, _ in S1[:3]],
    )

    assert slot["bannedFacet"] == "工作或手艺"
    assert slot["suggestedFacet"] != slot["bannedFacet"]
    assert slot["suggestedTopic"] in SOPHIA_TOPICS
