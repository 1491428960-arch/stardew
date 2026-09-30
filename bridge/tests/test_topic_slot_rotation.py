"""批次 4：生活面**硬槽位**（`topicSlot`）与 4b 的数据改写（2026-09-21）。

诊断结论是"机制为主、数据为辅"：索菲亚的 `preferredTopics` 已有 4 条跨簇素材、
`roleGuidance` 也已有动作式轮换指令，**仍然连着 6 轮画／酒**。所以问题不是
"候选不够"，而是候选池只是**语义层软约束**，压不过职业轴在词频层与具体性层的
双重牵引。这一批把生活面从"候选池"提升为**每轮由代码指定的槽位**：

* `rotation_topic_slot(preferred_topics, recent_replies=...)` 读最近
  `_FACET_LOOKBACK` 轮 NPC 回复，用 `_LIFE_FACET_PATTERNS` 匹配落点簇；
  **最近 3 轮里同一面出现 ≥2 次**就把该面列为硬禁用，并从该角色自己的素材里挑一条
  **不同面**的作为指定项（2026-09-21 二次：原口径是"连续两轮"，见第 6 节）；
* 只在触发时产出，其余轮次零成本（字段不进 prompt）；
* 单一层级：只点名被禁的那一面 + 一个可去的面，不留第二个可比对象
  （`stage_policy` 里记过两次"两个层级 → 模型挑最松读法"的教训）；
* 2026-09-21 二次：槽位算在 `build_stage_policy` **之前**，被禁面同时从
  `{topicPool}` 里摘掉 —— 否则"slot 说别谈酒、guidance 还列着酒"又是一次
  "一紧一松、取最松"（第 7、8 节）。

本文件另外钉住三个**容易假通过**的点：

1. `topicSlot` 必须过 `_compact_stage_policy` 的字段白名单 —— 它是白名单重建，
   没列出的顶层字段会静默消失（诊断线第一版就踩了这个：`ctx.stagePolicy` 里有、
   `stage_execution_card` 里是 `null`，线上一个字节都到不了模型）；
2. 素材来源必须是**真的** `preferredTopics`（第一版读了一个从不存在的
   `_preferredTopics` 键，于是"优先压素材占比最高的面"与"建议去一个素材里就有的面"
   两条设计同时落空，退化成按码点挑一个）；
3. `_facet_of_topic` 必须**确定**（第一版用 `next(iter(set))`，字符串哈希按进程
   随机化 ⇒ 同一份数据在不同进程映射到不同的面）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.stage_policy import (
    _LIFE_FACET_PATTERNS,
    CONVERSATION_LEAD_TRIAL_NPC_IDS,
    _facet_hits,
    _facet_of_topic,
    build_stage_policy,
    canonical_npc_id,
    narrow_topic_pool,
    rotation_topic_slot,
)

ROOT = Path(__file__).resolve().parents[2]
SOPHIA_MODS = ["vanilla", "SVE", "FlashShifter.StardewValleyExpandedCP"]
ELLIOTT_MODS = ["female-bachelors", "vanilla"]

# 最近两轮都落在「酿造」——正是用户实测的那个 case
BREW_REPLIES = [
    "刚把新酿的葡萄酒装进橡木桶，酒窖里全是葡萄的甜味。",
    "是啊，葡萄园的收成很好，我又酿了一批酒。",
]
WRITING_REPLIES = [
    "卡在那一段稿子上，改了三遍都不满意。",
    "又写了一页稿子，但句子还是不顺。",
]
MIXED_REPLIES = [
    "刚把酒窖里的橡木桶擦了一遍。",
    "外面下雨了，我就在窗边坐了会儿。",
]
# 索菲亚的 `preferredTopics`，与 `data/personas/sve.json` **逐字一致**
# （由 `test_pilot_topics_match_the_data_source` 钉住，防止两边各自演化）。
# 2026-09-23：从 2 面 4 条补到 **5 面 6 条**（第 4 条由"镇上"改写为"过去的回忆"，
# 另加吃喝、爱好两条），让她在每个被禁面上都还有落点可去。
# 2026-09-24：第 2 条由「画布上还没画完的那一块」换成「给下一个角色扮演挑的布料」——
# SVE 从没把她设定成画画的（她家「很多布料和油漆」是手工材料，她自称的是
# 「艺术瓶颈」），她的创作面在原话里是**角色扮演 + 缝纫**。面归属不变（都落
# 「工作或手艺」，「布料」本就在该面词表里），所以 `expected_facets` 一个字没动。
# 2026-09-25：从 7 条补到 **12 条 / 9 面全覆盖**（`_PREFERRED_TOPICS_LIMIT`）。
# 两条约束同时满足，缺一不可：
#   * **写法压短**（10 字/条 → 约 6 字/条）。`roleGuidance` 走
#     `_compact_conversation_lead` 的 **240 字截断线**，越过就**静默失效**；
#     12 条若沿用旧写法是 268 字（超 28），压短后 230 字才装得下。
#     —— 这是"写了也白写"的闸门，`test_preferred_topics_fit_the_prompt_limit`
#     只钉条数，钉不住这个，所以口径记在这里。
#   * **不与被禁面撞词**。固定文案里本来就有「角色扮演」（"谈过酿造或角色扮演"），
#     素材再用「角色扮演」会让 `test_any_banned_facet_still_leaves_a_readable_guidance`
#     的"被禁面素材不得残留"断言失效 —— 而且语义自相矛盾（既说谈过、又当落点）。
#     故该条改用「动漫展」（同属爱好面，原话"终于等到动漫展了"）。
# 新增的 4 条补上了原先缺的三个面（玩家自己 / 过去的回忆 / 家人朋友）。
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

# **只覆盖两个面**的素材形状 —— `_pick(allow_used=False)` 选空后退到"用过但未被禁"
# 那一级（降级分支）的回归用例。用 2026-09-23 之前的索菲亚素材，因为那正是缺口
# 角色的样子（补素材之后她本人已经不再走这条分支，见
# `test_sophia_no_longer_needs_the_fallback_branch`）。
NARROW_ROLE_TOPICS = ["酒窖里这一批新酿", "画布上还没画完的那一块",
                      "镇上今天谁在广场上吵", "她刚搬来镇上时住的那间旧房子"]

TOWN_REPLIES = [
    "今天广场上有人在吵架，围了一圈人。",
    "镇上的集市比平时热闹，我逛了一圈。",
]
WEATHER_REPLIES = ["外面一直在下雨，我就坐在窗边看了会儿。"]
EATING_REPLIES = ["我刚煮了一锅汤，还烤了面包。"]
HOBBY_REPLIES = ["晚上弹了会儿吉他，又翻了几页书。"]

# 隔一轮提同一件事：相邻两轮**从不同面**出发。
# 旧窗口（最近两轮取交集）在这个形状上**一次都不触发** —— 正是用户点名的代价场景。
ALTERNATING_REPLIES = [BREW_REPLIES[0], TOWN_REPLIES[0], BREW_REPLIES[1]]


def _payload(npc: str, history: list[dict[str, str]], mods: list[str]) -> dict:
    return {
        "npcId": npc, "message": "今天过得怎么样？", "intent": "chat", "provider": "fake",
        "compactPrompt": True, "channel": "face_to_face",
        "sourceMods": mods, "recentFacts": [], "history": history,
        "gameState": {
            "npcId": npc, "displayName": npc, "gender": "Female", "location": "Town",
            "season": "spring", "date": "25", "weather": "clear", "time": 1200,
            "friendship": 1500, "friendshipHearts": 6, "relationship": "friend",
        },
    }


def _history(replies: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for index, reply in enumerate(replies):
        items.append({"role": "user", "content": f"第{index + 1}轮提问"})
        items.append({"role": "assistant", "content": reply})
    return items


def _card(messages: list[dict[str, str]], name: str) -> dict:
    for message in messages:
        if message.get("name") == name:
            return json.loads(message["content"])
    raise AssertionError(f"prompt 里没有 {name} 卡")


# --- 1. 槽位本身的语义 --------------------------------------------------------


def test_slot_bans_the_repeated_facet_and_names_another_one() -> None:
    """用户要的两半都要在：**禁什么** + **改去哪一面**。

    2026-09-22：禁令的**说法**换成"别再以这一面做新的落点"，并在它前面加了一句
    「先接住上一轮的具体东西、从它拉一根线过去」（用户抱怨的"硬拐"）。
    2026-09-23：**禁令改成范例**（用户拍板"减约束、给示例"）——「换物件／换时段／
    换个说法都不算换」这份反例清单换成一个可照抄的句式（"手上这件先这样……对了，
    说起来"）。断言跟着换到新句；「禁什么 + 去哪一面」这两半本身没变。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert slot["bannedFacet"] == "工作或手艺"
    assert "这一面本轮先搁着" in slot["instruction"]
    assert "不要以同一面另起一件事" in slot["instruction"]
    assert "像这样换" in slot["instruction"]  # 范例式，不再是反例清单
    assert slot["suggestedFacet"] == "家人朋友"
    assert slot["suggestedTopic"] in SOPHIA_TOPICS
    assert slot["suggestedFacet"] != slot["bannedFacet"]
    assert "只说一件" in slot["instruction"]  # 不许罗列


def test_slot_does_not_fire_when_the_last_two_turns_differ() -> None:
    assert rotation_topic_slot(SOPHIA_TOPICS, recent_replies=MIXED_REPLIES) == {}


def test_slot_does_not_fire_without_enough_history() -> None:
    assert rotation_topic_slot(SOPHIA_TOPICS, recent_replies=[]) == {}
    assert rotation_topic_slot(SOPHIA_TOPICS, recent_replies=[BREW_REPLIES[0]]) == {}


def test_suggested_topic_comes_from_the_characters_own_material() -> None:
    """指定项必须**来自该角色自己的素材** —— 否则就是"要求落 A 而 A 不在 prompt 里"。"""

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert slot["suggestedTopic"] in SOPHIA_TOPICS
    assert slot["bannedFacet"] not in slot["suggestedTopic"]


def test_slot_falls_back_to_a_readable_phrase_without_material() -> None:
    """拿不到素材时也要给出可读的替代面列表，而不是空指令。"""

    slot = rotation_topic_slot(None, recent_replies=BREW_REPLIES)

    assert slot["bannedFacet"]
    assert "suggestedTopic" not in slot
    assert "换到另一个生活面" in slot["instruction"]
    for facet, _ in _LIFE_FACET_PATTERNS:
        if facet != slot["bannedFacet"]:
            assert facet in slot["instruction"], facet


def test_zero_history_phrasing_has_no_dangling_reference() -> None:
    """零历史时不许出现"刚才那一面" —— 她没有"刚才"（S13 的另一半）。

    B/C 理由共用那条 `else` 措辞。零历史 + 玩家开口第一句就说「换个话题」时，
    "刚才那一面"是一个**没有先行词**的指代；而若该角色连素材都没有
    （`preferredTopics` 为空），"她惯常的落点"这一级也拿不到禁令 —— 此时整条
    instruction 不该点名任何面，也不该留下指代。
    """

    slot = rotation_topic_slot(None, recent_replies=[], player_replies=["换个话题吧"])

    assert slot["trigger"] == "playerAsksNewTopic"
    assert "bannedFacet" not in slot
    assert "刚才那一面" not in slot["instruction"]
    assert "新的话头" in slot["instruction"]


# --- 2. 面映射必须是确定的 ----------------------------------------------------


def test_facet_lookup_is_order_determined_not_hash_determined() -> None:
    """一句同时命中多面时，取**声明顺序最靠前**的那一面。

    原先写的是 `next(iter(_facet_hits(...)))`：从 `set` 里取"第一个"，
    而字符串哈希按进程随机化 ⇒ 同一份数据在不同进程映射到不同的面，
    `banned` 的挑选与所有断言都不可复现。这条用一个**同时命中靠前与靠后两面**
    的句子把它钉死。
    """

    text = "以前在酒窖里酿过一批酒"
    facets = [name for name, pattern in _LIFE_FACET_PATTERNS
              if __import__("re").search(pattern, text)]

    assert "工作或手艺" in facets and "过去的回忆" in facets, "测试句失效"
    assert _facet_of_topic(text) == "工作或手艺"


@pytest.mark.parametrize("topic", SOPHIA_TOPICS)
def test_every_rewritten_topic_maps_to_a_facet(topic: str) -> None:
    """4b 的素材必须映射得到面。

    映射不到（`None`）的素材会被 `rotation_topic_slot` 的候选筛选直接跳过 ——
    即"永远不可能被指定"，等于白写。
    """

    assert _facet_of_topic(topic) is not None, topic


# --- 3. 到达线上路径 ----------------------------------------------------------


def test_compact_card_keeps_the_slot() -> None:
    """`_compact_stage_policy` 是白名单重建，字段不在名单里就静默消失。"""

    from stardew_ai_bridge.prompts import _compact_stage_policy

    policy = {"stage": "friend", "topicSlot": {
        "bannedFacet": "工作或手艺",
        "instruction": "最近2轮都在谈「工作或手艺」这一面；本轮不要再出现这一面。",
        "suggestedFacet": "镇上或邻里",
        "suggestedTopic": "镇上的新鲜事",
    }}

    compact = _compact_stage_policy(policy, include_response_order=False)

    assert compact["topicSlot"]["bannedFacet"] == "工作或手艺"
    assert compact["topicSlot"]["suggestedTopic"] == "镇上的新鲜事"


def test_slot_reaches_the_live_compact_card_and_the_provider() -> None:
    """端到端：`_build_context` 与 `PromptBuilder` 之后，槽位在发送给模型的消息里。"""

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Sophia", _history(BREW_REPLIES), SOPHIA_MODS)
    context, _ = _build_context(body)
    messages = PromptBuilder().build(context, body["message"], compact=True)
    slot = _card(messages, "stage_execution_card")["topicSlot"]

    assert slot["bannedFacet"] == "工作或手艺"
    assert slot["suggestedTopic"] == "斯嘉丽和朋友们"
    blob = json.dumps(messages, ensure_ascii=False)
    assert "这一面本轮先搁着" in blob


def test_slot_reaches_the_provider_through_the_http_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """再上一层：走真实 HTTP 路由，捕获 provider 实际收到的 messages。"""

    from fastapi.testclient import TestClient

    import stardew_ai_bridge.app as app_module
    from stardew_ai_bridge.models import ProviderResult

    captured: list[list[dict[str, str]]] = []

    class CapturingRouter:
        def has_configured_upstream(self) -> bool:
            return True

        def generate(self, request: object, *, messages=None) -> ProviderResult:  # type: ignore[no-untyped-def]
            del request
            captured.append(list(messages or []))
            return ProviderResult(reply="嗯，我去广场看看。", provider="local")

    monkeypatch.setattr(app_module, "provider_router", CapturingRouter())
    client = TestClient(app_module.app)

    response = client.post(
        "/api/dialogue/test",
        json=_payload("Sophia", _history(BREW_REPLIES), SOPHIA_MODS),
    )

    assert response.status_code == 200
    assert captured, "provider 没被调用"
    blob = json.dumps(captured[0], ensure_ascii=False)
    assert "topicSlot" in blob
    assert "工作或手艺" in blob
    assert "斯嘉丽和朋友们" in blob


# --- 4. 硬禁用确实改变了送给模型的东西（对照证明） ---------------------------


def test_without_the_slot_the_prompt_never_tells_the_model_to_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """对照实验：把槽位机制关掉，prompt 里**没有任何**"别再落这一面"的指令。

    这正是旧版连着 6 轮不换的机制原因 —— 落点池只给候选，没给禁令。
    两次渲染的差集证明：禁用语**只来自** `topicSlot`，不是别处的既有文案。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder
    import stardew_ai_bridge.prompts as prompts_module

    body = _payload("Sophia", _history(BREW_REPLIES), SOPHIA_MODS)
    context, _ = _build_context(body)
    with_slot = json.dumps(
        PromptBuilder().build(context, body["message"], compact=True), ensure_ascii=False
    )

    # 注意顺序：槽位是在 `_build_context`（ContextBuilder）里算的，所以补丁必须
    # 打在**重新构建 context 之前** —— 先建 context 再 patch，拿到的还是带槽位的那份。
    monkeypatch.setattr(prompts_module, "rotation_topic_slot", lambda *a, **k: {})
    context, _ = _build_context(body)
    without_slot = json.dumps(
        PromptBuilder().build(context, body["message"], compact=True), ensure_ascii=False
    )

    assert "这一面本轮先搁着" in with_slot
    assert "这一面本轮先搁着" not in without_slot
    assert "topicSlot" in with_slot and "topicSlot" not in without_slot
    # 关掉机制后，"酒" 仍然在 prompt 里（素材与 roleGuidance 都还在）——
    # 也就是说旧版**没有任何东西**阻止模型继续谈酒。
    assert "酒窖" in without_slot


# --- 5. 4b：素材必须是"可落座的具体物" ----------------------------------------


def _preferred_topics(npc_id: str) -> list[str]:
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        profile = (payload.get("personas") or {}).get(npc_id)
        if not isinstance(profile, dict):
            continue
        voice_style = profile.get("voiceStyle")
        topics = (voice_style or {}).get("preferredTopics") if isinstance(voice_style, dict) else None
        if topics:
            return [str(topic) for topic in topics]
    raise AssertionError(f"data/personas 里找不到 {npc_id} 的 preferredTopics")


def _window_topics(npc_id: str, turn_index: int = 0) -> list[str]:
    """**真正进 prompt 的那一批**落点（见 `test_preferred_topics_fit_the_prompt_limit`）。

    2026-09-30 起 `preferredTopics` 是素材库，进 prompt 的只有
    `_topic_window_for_turn` 切出的 12 条窗口。凡"渲染成什么 / 进了什么"的断言
    都要按窗口算。
    """

    from stardew_ai_bridge.prompts import _topic_window_for_turn

    return _topic_window_for_turn(_preferred_topics(npc_id), turn_index)


# 抽象元类目：模型无法从这类词直接取用物件，只能回退到职业轴的具体名词。
ABSTRACT_TOPIC_MARKERS = ("日常", "见闻", "烦恼", "计划", "近况", "感受", "过程", "细节", "创作")


@pytest.mark.parametrize("npc_id", ["Sophia", "Elliott"])
def test_rewritten_topics_are_concrete_objects_not_meta_categories(npc_id: str) -> None:
    """4b 的核心判据：条目要能**直接落成对白里的一个东西**。

    旧条目「小镇日常」「安全感与新开始」「写作和正在观察的细节」是元类目 ——
    诊断里那条"具体性不对等"说的就是它：职业轴给出"葡萄园、酒窖、画框"这种
    可直接取用的名词，生活面给出"日常/近况/感受"，模型只能退回前者。
    """

    offenders = [
        topic
        for topic in _preferred_topics(npc_id)
        if any(marker in topic for marker in ABSTRACT_TOPIC_MARKERS)
    ]

    assert offenders == [], f"{npc_id} 还有抽象元类目：{offenders}"


@pytest.mark.parametrize(
    ("npc_id", "expected"),
    [
        ("Sophia", [
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
        ]),
        ("Elliott", ["卡住的那一段稿子", "海风里退潮后的那片沙滩",
                     "手边正在读的那本书", "你上次提到的那个地方",
                     "不想老了以后做个孤独的隐士"]),
    ],
)
def test_试点两人的素材已改写(npc_id: str, expected: list[str]) -> None:
    """用户点名的两组改写（只在这两人身上试点，其余角色等效果）。

    2026-09-23：目标从"能落座的具体物"提到"**补到 5 个生活面**"——
    索菲亚 2 面 → 5 面（加吃喝、爱好，并把"旧房子"那条由"镇上"改写为"过去的回忆"，
    那是全库唯一一条覆盖"过去的回忆"的素材），埃琳娜 4 面 → 5 面（加"自己的状态"）。
    2026-09-25：索菲亚再提到 **12 条 / 9 面全覆盖**（见 `SOPHIA_TOPICS` 上方说明）；
    埃琳娜维持原样等效果，所以两人不再"停在 6/5 条"。

    2026-09-30 口径改为**子集**：素材库扩到几十条之后，"恰好等于这 12 条"不再
    是这批素材的用途（它们只是最早的 12 条，现在还有别的）。要守的性质是
    **这批改写没有回退**——它们仍在库里，一条都没被冲掉。
    """

    assert set(expected) <= set(_preferred_topics(npc_id)), (
        f"{npc_id} 的试点改写被冲掉了：{sorted(set(expected) - set(_preferred_topics(npc_id)))}"
    )


@pytest.mark.parametrize(
    ("npc_id", "expected_facets"),
    [
        ("Sophia", {"工作或手艺", "镇上或邻里", "天气季节", "爱好或消遣",
                    "自己的状态或烦恼", "吃喝", "家人朋友", "玩家自己",
                    "过去的回忆"}),
        ("Elliott", {"工作或手艺", "天气季节", "爱好或消遣", "玩家自己", "自己的状态或烦恼"}),
    ],
)
def test_试点两人的素材覆盖到五个生活面(npc_id: str, expected_facets: set[str]) -> None:
    """**本轮的目标本身**（审计报告的缺口：全库没有一个人到 5 面）。

    面数不够的后果不是"素材少"，而是**换面一换就撞回原地**：索菲亚原先只有
    工作 / 镇上两面，槽位一旦禁掉工作面，`_pick` 只剩镇上可挑，第三轮就穷尽 ——
    机制只能靠规则硬压（用户体感"只聊画"的直接来源）。

    2026-09-25 索菲亚到 **9/9 面**：`_LIFE_FACET_PATTERNS` 里每一个面的判定词表
    都有一条能命中它 —— 也就是**禁掉任何一面，都还有别的面可去**。

    2026-09-30 口径改为**父集**：扩库只可能加面、不可能减面，所以"至少覆盖这些"
    才是要守的性质；相等断言会在每次扩库时假红。判不出面的素材（`None`）不算面，
    必须先滤掉再比 —— 否则 `sorted()` 会撞 `None` 直接抛 `TypeError`。
    """

    got = {_facet_of_topic(topic) for topic in _preferred_topics(npc_id)}
    got.discard(None)
    assert expected_facets <= got, (
        f"{npc_id} 少了生活面：{sorted(expected_facets - got)}（现有 {sorted(got)}）"
    )


def test_pilot_topics_match_the_data_source() -> None:
    """测试里那份 `SOPHIA_TOPICS` 必须与 `data/personas/sve.json` **逐字一致**。

    本条防的是"两边各自演化"：素材改了而常量没跟上，`rotation_topic_slot` 那一批
    用例就会在**另一份数据**上跑，测的却不是线上真正喂进去的东西 ——
    与 b307388 那次「要求落 A，而 A 不在 prompt 里」同型。

    2026-09-30 起数据源比常量宽（扩库），所以门是**单向**的：常量里的每一条都
    必须仍能在数据源里逐字找到；反过来不要求 —— 数据源多出来的那些是扩库新增的。
    """

    assert set(SOPHIA_TOPICS) <= set(_preferred_topics("Sophia"))
    # 降级用例的素材形状必须仍是"只覆盖两面"，否则那条用例测不到降级分支
    assert {_facet_of_topic(topic) for topic in NARROW_ROLE_TOPICS} == {
        "工作或手艺",
        "镇上或邻里",
    }


@pytest.mark.parametrize(
    ("npc_id", "mods"),
    [("Sophia", SOPHIA_MODS), ("Elliott", ELLIOTT_MODS)],
)
def test_rewritten_topics_keep_the_guidance_within_the_compact_limit(
    npc_id: str, mods: list[str]
) -> None:
    """同源化的代价：池子变长会把 roleGuidance 推向 240 字上限，超了就白改。

    这是**真实路径**（`_build_context`），所以要看的是它当轮真正渲染的那一批：
    history 为空 ⇒ 第 0 轮窗口。拿整库去要求"每条都在 guidance 里"已经不成立。
    """

    from stardew_ai_bridge.app import _build_context

    _, messages = _build_context(_payload(npc_id, [], mods))
    guidance = _card(messages, "stage_execution_card")["conversationLead"]["roleGuidance"]

    assert len(guidance) <= 240, f"{npc_id} 的 roleGuidance 有 {len(guidance)} 字"
    for topic in _window_topics(npc_id):
        assert topic in guidance, topic


# --- 6. 窗口收紧：最近 3 轮里同一面出现 ≥2 次（2026-09-21 二次，用户拍板） ----
#
# 用户嫌的不是"连续"本身，而是「内容永远围着'创作／手艺'这一轴」（索菲亚＝画／酒、
# 埃琳娜＝写作）。旧口径（最近两轮取交集）只看得见连续：`[酒, 镇上, 酒]` 上相邻两轮
# 交集为空，**一次都不触发**，手艺轴照样以 2/3 的密度占位。


def test_slot_fires_when_the_same_facet_repeats_within_three_turns() -> None:
    """隔一轮提同一件事也要命中 —— 这是本次收紧要拿下的形状。"""

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=ALTERNATING_REPLIES)

    assert slot["bannedFacet"] == "工作或手艺"
    assert "3轮里有2轮" in slot["instruction"]


def test_healthy_rotation_never_fires() -> None:
    """代价闸：每轮都换面的写法不许被误伤 —— 收紧不能变成"为换而换"。"""

    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLIES[0], WEATHER_REPLIES[0]],
    ) == {}
    assert rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[EATING_REPLIES[0], HOBBY_REPLIES[0], WEATHER_REPLIES[0]],
    ) == {}


def test_two_turns_are_enough_to_judge_and_one_is_not() -> None:
    """阈值 2 的边界：两轮同面就要判（回归不变），一轮无从谈"出现过两次"。"""

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert slot["bannedFacet"] == "工作或手艺"
    assert "2轮里有2轮" in slot["instruction"]
    assert rotation_topic_slot(SOPHIA_TOPICS, recent_replies=[BREW_REPLIES[0]]) == {}


def test_window_only_looks_at_the_three_most_recent_turns() -> None:
    """更早的重复必须滑出窗口，否则一次重复会把槽位永久卡住。"""

    replies = BREW_REPLIES + [
        TOWN_REPLIES[0],
        WEATHER_REPLIES[0],
        EATING_REPLIES[0],
    ]

    assert rotation_topic_slot(SOPHIA_TOPICS, recent_replies=replies) == {}


def test_player_anchor_is_a_standalone_hard_constraint() -> None:
    """禁令只压 NPC **主动**选落点；玩家点名的对象必须接住 —— 且这是**硬约束**。

    索菲亚的 `roleGuidance` 第一句是「先明确接住玩家点名的当前对象」——不加豁免，
    两条硬指令会在同一张卡里互相封口，等于把"两层打架"搬个位置。

    2026-09-22：豁免从 instruction 的**括号从句**升成 `topicSlot` 的**一级字段**
    `playerAnchor`。旧写法是「别再以这一面做新的落点（玩家本轮自己点名的对象仍要
    接住；他要是继续追问这一面，就顺着他的方向聊，别为了换面绕开它）」——位置上是从句、
    语气上是提醒，模型很容易在"本轮由你主动把话头换一次"这条主线下面读成可选项。
    而它是"方向盘在玩家手里"的**唯一**措辞层保障：代码层的撤回只在"玩家点的正好是
    被禁那一面"时生效，玩家点名别的面时全靠这一条。

    2026-09-23：上面那句 `roleGuidance` 里的举例（"酒、酒窖、喝一口等"）为腾 240 字
    预算删掉了 —— 它本来就是 `playerAnchor` 的第二份措辞。豁免本身一个字没动。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert "硬约束" in slot["playerAnchor"]
    assert "先接住" in slot["playerAnchor"]
    assert "顺着聊" in slot["playerAnchor"]
    # 升成独立字段之后，instruction 里不再有那段括号从句（不留第二份措辞）
    assert "玩家本轮自己点名的对象仍要接住" not in slot["instruction"]
    # 但禁令本身一个字都不许少（2026-09-23：说法换成范例，意图断言保持不变）
    assert "这一面本轮先搁着" in slot["instruction"]
    assert "不要以同一面另起一件事" in slot["instruction"]


def test_player_anchor_is_unconditional() -> None:
    """硬约束**无条件**在场：B/C 理由（没有重复面可禁）触发的槽位也带着它。

    有重复面时"撤回"能把玩家点名的面整体让回去；没有重复面时没有任何代码层保障，
    更没有理由把这句话省掉。
    """

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], TOWN_REPLIES[0], WEATHER_REPLIES[0]],
        player_replies=["嗯"],
    )

    assert "bannedFacet" not in slot
    assert slot["playerAnchor"]


def test_suggestion_falls_back_to_a_used_but_unbanned_facet() -> None:
    """降级：首选"最近没用过"的面被用光时，退到"至少不与禁令同面"的素材上。

    素材只覆盖两面的角色在交替对话里，`used` 会等于它的全部素材面。旧写法此时
    **每一轮**都落进"没有候选"的泛化分支，建议指向它根本没有素材的面（吃喝、天气、
    家人…）——"换到空的"比不换更差。禁令只针对 `banned` 这一面，回到别的面并不违规。

    2026-09-23：素材换成 `NARROW_ROLE_TOPICS`（**只覆盖两面**的形状）—— 索菲亚本人
    补到 5 面之后已经不走这条分支了，但缺口角色还在走，降级逻辑必须继续有人守。
    """

    slot = rotation_topic_slot(NARROW_ROLE_TOPICS, recent_replies=ALTERNATING_REPLIES)

    assert slot["suggestedTopic"] in NARROW_ROLE_TOPICS
    # 确实用了一条"最近出现过"的面的素材，也就是降级分支真的生效了
    assert _facet_of_topic(slot["suggestedTopic"]) == "镇上或邻里"
    # 2026-09-25：`_pick` 的遍历起点改成按内容哈希偏移后，这里从"镇上今天谁在
    # 广场上吵"换成**同一个面**里的"她刚搬来镇上住的那间旧房子"。
    # 语义没变（降级到"用过但未被禁"的面），变的只是面**内部**挑哪一条 ——
    # 这正是偏移要拿到的东西。所以真正的不变量是上面那两行。
    assert slot["suggestedTopic"] == "她刚搬来镇上时住的那间旧房子"


def test_sophia_no_longer_needs_the_fallback_branch() -> None:
    """补素材的**直接效果**：同一场景下她不再退到"用过但未被禁"的面。

    两轮落在工作面之后（`used` = {工作或手艺}），素材里有的是**没被用过、
    也不与禁令同面**的候选 —— 槽位因此给出一个真正的新方向，而不是"换个说法说镇上"。
    这正是"素材补上去，规则减下来"要拿到的形状：换面不再靠降级兜底，而是有地方可去。

    2026-09-25：补到 12 条 / 9 面后，这一轮点名的是池中第一条**未被禁**的「斯嘉丽和朋友们」
    （家人朋友面）—— 池首「精灵石和矿石」正是工作面、被禁令挡下，所以跳过它去了下一条。
    两个面都满足"未被用过 + 不与禁令同面"，所以 `suggestedFacet` 这个具体值只是数据快照，
    **不变量是下面那两行**。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert slot["suggestedFacet"] == "家人朋友"
    assert _facet_of_topic(slot["suggestedTopic"]) != slot["bannedFacet"]

    # 交替场景（used = {工作或手艺, 镇上或邻里}）里也不会退到泛化分支
    alternating = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=ALTERNATING_REPLIES)

    assert alternating["suggestedTopic"] in SOPHIA_TOPICS
    assert alternating["suggestedFacet"] not in {"工作或手艺", "镇上或邻里"}
    assert "换到另一个生活面（" not in alternating["instruction"]


# --- 7. 落点池收窄：拿掉被禁面 -----------------------------------------------


def test_narrow_topic_pool_drops_the_banned_facet() -> None:
    """禁工作面之后，她**剩下 9 条**（12 条里去掉 3 条工作面）。

    2026-09-25：原为 6 条。当日把 `preferredTopics` 由 7 条补到 12 条 / 9 面全覆盖，
    禁工作面后剩下的落点从 6 条升到 9 条 —— 这个数就是"换面时还有多少地方可去"。
    """

    narrowed = narrow_topic_pool(SOPHIA_TOPICS, "工作或手艺")

    assert narrowed == [
        "斯嘉丽和朋友们",
        "海边的咸风",
        "毯子和电视",
        "格斯做的菜",
        "独处时的孤独",
        "镇上的新鲜事",
        "你今天要忙什么",
        "记得把头发染成粉色那天",
        "动漫展",
    ]


def test_narrow_topic_pool_without_a_ban_is_the_original_pool() -> None:
    assert narrow_topic_pool(SOPHIA_TOPICS, None) == SOPHIA_TOPICS
    assert narrow_topic_pool(SOPHIA_TOPICS, "") == SOPHIA_TOPICS


def test_narrow_topic_pool_returns_empty_when_the_whole_pool_is_banned() -> None:
    """全被禁光时返回空列表 —— 调用方据此退回不点名的中性说法。

    **不能**退回原始列表：那等于把被禁面又写回 prompt。
    """

    assert narrow_topic_pool(["蓝月亮招牌酒今年这一批的味道"], "工作或手艺") == []


# --- 8. 端到端：同一张卡里，禁令与落点池必须自洽 -------------------------------


def test_banned_facet_disappears_from_the_guidance_of_the_same_card() -> None:
    """收窄的实质：槽位说"别谈酒和画"，同一张卡的 roleGuidance 就不许再列它们。

    这是本次修的那个 bug —— 修复前 guidance 里四条照旧，槽位在另一处说"别再谈工作
    面"，两层并排就是"一紧一松、取最松"。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Sophia", _history(BREW_REPLIES), SOPHIA_MODS)
    context, _ = _build_context(body)
    card = _card(
        PromptBuilder().build(context, body["message"], compact=True),
        "stage_execution_card",
    )
    guidance = card["conversationLead"]["roleGuidance"]

    assert card["topicSlot"]["bannedFacet"] == "工作或手艺"
    assert "蓝月亮招牌酒今年这一批的味道" not in guidance
    assert "画布上还没画完的那一块" not in guidance
    assert "斯嘉丽和朋友们" in guidance


def test_guidance_keeps_the_whole_pool_when_no_slot_fires() -> None:
    """未触发的轮次必须原样保留**当轮那一批** —— 收窄只在触发轮生效，不是常态缩池。

    口径是**当轮窗口**而不是整库：2026-09-30 扩库后进 prompt 的只有 12 条窗口
    （见 `_prompt_topics`），整库级别的"一条都不许少"已不成立。
    """

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload(
        "Sophia",
        _history([BREW_REPLIES[0], TOWN_REPLIES[0], WEATHER_REPLIES[0]]),
        SOPHIA_MODS,
    )
    context, _ = _build_context(body)
    card = _card(
        PromptBuilder().build(context, body["message"], compact=True),
        "stage_execution_card",
    )
    guidance = card["conversationLead"]["roleGuidance"]

    assert "topicSlot" not in card
    for topic in _prompt_topics("Sophia"):
        assert topic in guidance, topic


def test_suggested_topic_is_visible_in_the_same_card() -> None:
    """同源不变式：槽位点名的方向必须在同一张卡的落点池里看得到。"""

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Sophia", _history(ALTERNATING_REPLIES), SOPHIA_MODS)
    context, _ = _build_context(body)
    card = _card(
        PromptBuilder().build(context, body["message"], compact=True),
        "stage_execution_card",
    )
    slot = card["topicSlot"]
    guidance = card["conversationLead"]["roleGuidance"]

    assert slot["suggestedTopic"]
    assert slot["suggestedTopic"] in guidance
    # 被禁面的素材条目一条都不许留在池子里（模板里"谈过酿造或角色扮演"那句是通用轮换
    # 指令、不是落点池，所以这里只逐条核对**素材**，不整段扫面关键词）。
    for topic in SOPHIA_TOPICS:
        if _facet_of_topic(topic) == slot["bannedFacet"]:
            assert topic not in guidance, topic


# --- 9. 素材覆盖：禁掉任一面之后还剩得下东西吗 --------------------------------


def _prompt_topics(npc_id: str, turn_index: int = 0) -> list[str]:
    """`_build_context` 真正喂给 stage policy 的那一份 preferredTopics。

    2026-09-30 起是 `_topic_window_for_turn` 按已聊轮数切出的 12 条窗口
    （逐轮滑动），**不再是整库** —— 扩库之后"整库"既不是线上会发生的输入，
    也会让下游断言假红（本文件原先就有一批这样的断言）。
    """

    from stardew_ai_bridge.prompts import (
        _preferred_topics_for_prompt,
        _topic_window_for_turn,
    )

    wanted = canonical_npc_id(npc_id).casefold()
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, profile in (payload.get("personas") or {}).items():
            if not isinstance(profile, dict):
                continue
            if canonical_npc_id(name).casefold() != wanted:
                continue
            voice_style = profile.get("voiceStyle")
            raw = (
                voice_style.get("preferredTopics")
                if isinstance(voice_style, dict)
                else None
            )
            topics = _preferred_topics_for_prompt(raw)
            if topics:
                return _topic_window_for_turn(topics, turn_index)
    raise AssertionError(f"data/personas 里找不到 {npc_id} 的 preferredTopics")


@pytest.mark.parametrize("npc_id", sorted(CONVERSATION_LEAD_TRIAL_NPC_IDS))
def test_any_banned_facet_still_leaves_a_readable_guidance(npc_id: str) -> None:
    """换面不能换到"空的"：禁掉任一面后 roleGuidance 仍是一句可读、且不含被禁面的指令。

    素材真被抽空时（该角色所有条目都落在被禁面）由 `_topic_pool_phrase` 的中性说法
    兜底 —— 可读性保住了，但**不等于**素材够用；真实缺口由下一条哨兵测试记录。
    """

    topics = _prompt_topics(npc_id)
    assert topics, npc_id

    for facet, _ in _LIFE_FACET_PATTERNS:
        narrowed = narrow_topic_pool(topics, facet)
        guidance = build_stage_policy(
            npc_id, "dating", preferred_topics=narrowed
        )["conversationLead"]["roleGuidance"]

        assert guidance.strip(), (npc_id, facet)
        assert "{topicPool}" not in guidance, (npc_id, facet)
        for topic in topics:
            if _facet_of_topic(topic) == facet:
                assert topic not in guidance, (npc_id, facet, topic)


def test_narrow_material_roles_are_recorded() -> None:
    """素材缺口**哨兵**（记录事实，不是判 bug）：禁「工作或手艺」后剩几条。

    * `Sophia`：2026-09-23 补到 5 面 6 条之后，禁工作面**剩 4 条**（改前是 2 条）；
      2026-09-25 三轮改动后**剩 6 条**。
      这个数字是"换面时还有多少地方可去"的直接度量 —— 2 条意味着第三轮就穷尽，
      机制只能退回泛化降级；
    * `Alex` 的缺口**已关闭**（2026-09-21 三次拆面，见第 10 节）：他的 4 条里原本有 3 条
      落进"工作或手艺"—— 体育词（四分卫、投球、俯卧撑）被 `四分卫|投球|俯卧撑|训练|运动`
      这一段正则收编，禁工作面后只剩一条不映射任何面的素材（`_facet_of_topic` 返回
      `None`），**不能作为建议候选**，于是每一轮都走"换到另一个生活面（…）"的泛化降级。
      运动词归位到"爱好或消遣"之后，他名下已经**没有任何工作面条目**，禁工作面等于不
      收窄，候选回到 3 条。

    这是数据层的事：补素材会让这两条断言失败，那时按新数据更新即可（本次 Sophia
    那一行就是这么更新的）。
    """

    # 2026-09-30 口径是**当轮窗口**（`_prompt_topics` 已改为窗口）：扩库之后
    # "禁工作面后还剩几条可去"要按真正进 `_pick` 的那一批算。数额会随池子继续变，
    # 所以守**下界**（历史最低是 docstring 里记的 6 条），不守精确值。
    remaining = narrow_topic_pool(_prompt_topics("Sophia"), "工作或手艺")
    assert len(remaining) >= 6, f"索菲亚禁工作面后只剩 {len(remaining)} 条：{remaining}"
    assert narrow_topic_pool(_prompt_topics("Alex"), "工作或手艺") == _prompt_topics("Alex")
    assert _facet_of_topic("职业选手目标，以及后来发现的微不足道的小事") is None


def test_preferred_topics_fit_the_prompt_limit() -> None:
    """**一次可见的条数 = `_PREFERRED_TOPICS_LIMIT`**（2026-09-30 语义更新）。

    2026-09-23 这条守的是"素材条数不得超过 12"：当时两端都是
    `_compact_text_list(limit=12)` 的「取前 12 条」，超出的条目既进不了
    `persona_core`、也进不了 `_pick` 的池子，是"写了也白写"。

    2026-09-30 素材库扩到几十条之后，**那个口径反过来成了瓶颈**：池子宽了，
    可见的却永远只有前 12 条，于是第 13 条起照样白写。改成
    `_topic_window_for_turn` 按已聊轮数在完整池上滑动之后：

    * **条数不再是数据约束** —— 池子可以宽（上限见合并脚本的 `MAX_POOL`）；
    * 不变的是**窗口宽度**：任何一轮发给模型、交给 `_pick` 的都恰好是
      `_PREFERRED_TOPICS_LIMIT` 条（池子更窄时就是全池）；
    * 而且窗口**真的会动** —— 否则"扩池"等于没扩。

    这条哨兵现在守的是后两件事。240 字预算则由 `worst_window_render`
    在合并时逐个窗口验（本文件第 9 节另有 roleGuidance 的长度回归）。
    """

    from stardew_ai_bridge.prompts import (
        _PREFERRED_TOPICS_LIMIT,
        _topic_window_for_turn,
    )

    assert _PREFERRED_TOPICS_LIMIT == 12

    wrong_width: dict[str, tuple[int, int]] = {}
    not_rotating: list[str] = []
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, profile in (payload.get("personas") or {}).items():
            voice_style = (profile or {}).get("voiceStyle")
            topics = (
                voice_style.get("preferredTopics") if isinstance(voice_style, dict) else None
            )
            if not topics:
                continue
            key = f"{path.name}:{name}"
            clean = [t.strip() for t in topics if isinstance(t, str) and t.strip()]
            window = _topic_window_for_turn(topics, 0)
            expect = min(len(clean), _PREFERRED_TOPICS_LIMIT)
            if len(window) != expect:
                wrong_width[key] = (len(window), expect)
            # 池子比窗口宽时，轮次推进必须让窗口真的移动
            if len(clean) > _PREFERRED_TOPICS_LIMIT and (
                _topic_window_for_turn(topics, 0) == _topic_window_for_turn(topics, 1)
            ):
                not_rotating.append(key)

    assert wrong_width == {}, (
        f"窗口宽度不等于可见上限（前者是实际取到的条数，后者是应有的）：{wrong_width}"
    )
    assert not_rotating == [], (
        f"这些角色的池子宽于窗口、但窗口不随轮次移动（扩池等于没扩）：{not_rotating}"
    )


# --- 10. 2026-09-21 三次：运动词归位（Alex 的素材缺口关闭） -------------------
#
# 父任务拍板的方案：**把"四分卫／投球／俯卧撑"从"工作或手艺"拆到"爱好或消遣"**，
# 判据是"打橄榄球是爱好，不是工作"。这一节钉住三件事：
#   ① 这五个词只属于爱好面（拆干净，不是两边都留）；
#   ② 真正的工作类说法**一条都没跟着走**（Alex 的"农场帮忙"必须留在工作面）；
#   ③ Alex 触发换面时给出的是**具体**建议，而不是泛化降级。

ALEX_MODS = ["vanilla"]

# 最近两轮都落在"工作或手艺"：Alex 在农场帮忙 —— 那个落点**留在工作面**（拆面不许搬走）。
ALEX_FARM_REPLIES = [
    "今天在农场帮着搬了半天饲料，胳膊都酸了。",
    "刚又去农场搭了会儿手，回来倒头就睡。",
]

# 运动词归位后，连着谈身体算"爱好或消遣"重复（改前它算"工作或手艺"）。
ALEX_PUSHUPS_REPLIES = [
    "刚做完三组俯卧撑，胳膊都抬不起来了。",
    "睡前又补了一组俯卧撑，今天就够了。",
]


@pytest.mark.parametrize("word", ["四分卫", "投球", "俯卧撑", "训练", "运动"])
def test_sports_words_live_in_the_hobbies_facet_only(word: str) -> None:
    """① 拆干净：这五个词**只**命中"爱好或消遣"，工作面一个都不留。"""

    assert _facet_hits(word) == {"爱好或消遣"}, word


@pytest.mark.parametrize(
    "text",
    [
        "今天去农场帮忙搬了半天的箱子。",  # Alex 游戏里的实际落点
        "明天还得早起开公交，先不聊了。",  # Pam
        "铁匠铺里还有一批工具要锻造。",  # Clint
        "木工台上那批图纸今天得画完。",  # Robin
        "实验室的记录还要再核对一遍。",  # Demetrius / Maru
        "诊所今天排了一天的班。",  # Harvey
        "博物馆那批文物要重新登记。",  # Gunther
        "店里今天要进货，得早点开门。",  # Pierre
        "今天出海钓鱼，风不大。",  # Willy
    ],
)
def test_work_patterns_did_not_get_swept_into_hobbies(text: str) -> None:
    """② 拆的是体育词，不是"提到身体或户外就搬走"：工作类说法必须留在工作面。"""

    hits = _facet_hits(text)

    assert "工作或手艺" in hits, text
    assert "爱好或消遣" not in hits, text


def test_alex_topics_land_on_their_new_facets() -> None:
    """拆面的结果本身：6 条素材的新归属（2026-09-22 第 4 批补到 5 面）。

    前三条是 2026-09-21 三次拆面的结果（原第 4 条「职业选手目标，以及后来发现的
    微不足道的小事」判不出任何面，**永远不会被 `_pick` 选为落点**，第 4 批用三条
    具体素材换掉了它）。补上的三条同时保住了那条拆面结论的**前提**：Alex 名下
    仍然没有任何工作面条目（否则 `test_narrow_material_roles_are_recorded` 会红）。
    """

    got = {topic: _facet_of_topic(topic) for topic in _preferred_topics("Alex")}
    expected = {
        "全明星四分卫和夹克上的小星星": "爱好或消遣",
        "海滩、投球和镇上的朋友": "镇上或邻里",
        "俯卧撑、酸痛与进步": "爱好或消遣",
        "夏天是一年里最有活力的季节": "天气季节",
        "祖父母把我带大": "家人朋友",
        "小时候那些不太快乐的日子": "过去的回忆",
        # 2026-09-30 补素材时新增（第 8 批）：三条都是**非工作面**，所以上文那句
        # "Alex 名下没有任何工作面条目"的前提没被破坏。
        "烧烤和汉堡包": "吃喝",
        "音乐盒和母亲": "家人朋友",
        "读书和学习": "爱好或消遣",
    }
    # 2026-09-30 口径改为**子集**：素材库扩到几十条之后，"不多不少就这 9 条"不再
    # 是这条用例要守的东西（新补的素材会一直加进来）。要守的是**这 9 条的归属
    # 没有漂移**，以及 Alex 名下仍然没有工作面素材。
    assert got.items() >= expected.items(), (
        f"Alex 的素材归属漂了：{ {k: (expected[k], got.get(k)) for k in expected if got.get(k) != expected[k]} }"
    )
    assert "工作或手艺" not in got.values(), "Alex 名下出现了工作面素材"


def test_alex_gets_a_concrete_suggestion_after_the_sports_split() -> None:
    """③ 核心验收：Alex 谈完农场被要求换面时，给出**具体**建议而不是泛化降级。

    改前面貌：4 条里 3 条被"工作或手艺"收编 ⇒ 禁工作面后只剩一条无面素材 ⇒
    `suggestedTopic` 恒为空，instruction 退化成"换到另一个生活面（吃喝、天气季节…）"。
    改后：素材里没有工作面条目，候选落到他名下的某一面上。

    2026-09-30：素材补到 7 条后，`_pick` 返回的落点不再是"爱好或消遣"那一条 ——
    但**验收意图**是"给出具体建议而非泛化降级"，与落点具体落在哪一面无关，
    故改钉不变量（非空、是他自己的素材、不与禁令同面）。核心那行"泛化降级一个字
    都不许出现"保持不变。
    """

    slot = rotation_topic_slot(_prompt_topics("Alex"), recent_replies=ALEX_FARM_REPLIES)

    assert slot["bannedFacet"] == "工作或手艺"
    assert slot["suggestedTopic"], "具体建议退化成空 —— 这正是改前的表现"
    assert slot["suggestedTopic"] in _prompt_topics("Alex")
    assert slot["suggestedFacet"] and slot["suggestedFacet"] != slot["bannedFacet"]
    # 泛化降级的那句"换到另一个生活面（…）"一个字都不许出现 —— 它正是改前的表现。
    assert "换到另一个生活面（" not in slot["instruction"]


def test_alex_suggestion_reaches_the_live_card() -> None:
    """端到端：具体建议真的进了 `stage_execution_card`，且与同一张卡的落点池自洽。"""

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Alex", _history(ALEX_FARM_REPLIES), ALEX_MODS)
    context, _ = _build_context(body)
    card = _card(
        PromptBuilder().build(context, body["message"], compact=True),
        "stage_execution_card",
    )
    slot = card["topicSlot"]
    guidance = card["conversationLead"]["roleGuidance"]

    # 同 `test_alex_gets_a_concrete_suggestion_after_the_sports_split`：钉不变量。
    assert slot["suggestedTopic"] in _prompt_topics("Alex")
    assert slot["suggestedTopic"] in guidance
    # 工作面素材：Alex 本来就没有，所以禁令摘不掉任何一条他名下的素材。
    for topic in _prompt_topics("Alex"):
        if _facet_of_topic(topic) == "工作或手艺":
            assert topic not in guidance, topic


def test_sports_talk_now_reads_as_hobbies_repeat() -> None:
    """行为面的变化：同两轮回复，改前判"工作或手艺"、改后判"爱好或消遣"。

    `banned` 是**按素材占比**在重复面里挑的（`rotation_topic_slot` 的 tie-break），
    所以这里禁的会是爱好面，建议退到他的素材里**另一个面**上。

    2026-09-25：`_pick` 的遍历起点改成按内容哈希偏移后，建议从"镇上或邻里"变成
    "天气季节"。两者都是"另一个面"，所以这里断言的不变量是**"不与禁令同面、
    且素材是他自己的"**，不是具体哪一个面。

    2026-09-30：哈希偏移再次漂移（素材从 6 条补到 7 条，偏移量随之改变），落点
    又变成"过去的回忆"。docstring 早就写明**不变量不是具体哪一个面**，而上一行
    断言违背了它 —— 故删掉，保留下方两条真正的不变量。
    """

    slot = rotation_topic_slot(_prompt_topics("Alex"), recent_replies=ALEX_PUSHUPS_REPLIES)

    assert slot["bannedFacet"] == "爱好或消遣"
    assert slot["suggestedTopic"] in _prompt_topics("Alex")
    assert slot["suggestedFacet"] != slot["bannedFacet"]


def test_alex_cross_facet_topic_penetration_is_recorded() -> None:
    """**次要面穿透**（记录事实，不是判 bug）：跨面条目的主面之外仍留着被禁面的词。

    「海滩、投球和镇上的朋友」同时命中三个面，`_facet_of_topic` 按声明顺序取主面
    = "镇上或邻里"，于是禁"爱好或消遣"时它**不会**被 `narrow_topic_pool` 摘掉，
    而文本里仍写着"投球"（被禁面的词）。这与"槽位禁某面、guidance 仍列该面"那种
    **同面冲突**不是一回事：`narrow_topic_pool` 一直按**主面**收窄，那条规则没变。

    影响面是**可数的**（第 7 批实测：全库 25 条跨面条目，本轮还原原话新增了其中 3 条，
    见下面的 `test_secondary_facet_penetration_added_by_restoring`）。

    **2026-09-23 已结案**：这里原先写着"得改用 `_facet_hits`（命中即摘）——那是另一轮"。
    那一轮**已经做了**（代价实测为零：396 个角色 × 面组合里摘空增量为 0，报告 §9.3），
    所以下面第三条断言现在是**反向**的。
    """

    topic = "海滩、投球和镇上的朋友"

    assert _facet_of_topic(topic) == "镇上或邻里"
    assert _facet_hits(topic) == {"爱好或消遣", "镇上或邻里", "家人朋友"}
    # 2026-09-23 起为「命中即摘」：禁次要面时它**也会**被摘掉（这正是本次的目的）
    assert topic not in narrow_topic_pool(_prompt_topics("Alex"), "爱好或消遣")


# --- 11. 2026-09-22 第 4 批：素材横向推广的两条不变式（**遍历全部角色**） ------
#
# 第 4 批把 12 个角色的素材从 1~2 面补到 5 面（Sophia／Elliott 在更早的批次到 5 面）。
# 补素材有**两个静默的失败方向**，各自做成一条遍历全库的断言：
#
#   ① **写了也白写**：素材条数超过 `_PREFERRED_TOPICS_LIMIT` —— 已由第 9 节的
#      `test_preferred_topics_fit_the_prompt_limit` 覆盖（逐 key 口径）。
#   ② **写了也选不中**：条目**判不出任何生活面**。槽位的 `_pick` 会跳过它，所以它
#      既不会被选为落点，也永远不会被禁 —— 每一条都白占 6 条上限里的一个位置。
#
# ② 的口径是"每角色**至多一条**无面素材"：留一条最能定义人设的抽象方向是**有意
# 为之**（Claire 的「新生活里的小变化」、Krobus 的「下水道生活」、Kent 的
# 「家庭日常」…），它仍会进 `{topicPool}` 当方向提示；两条以上就是纯占位。

# 已达 5 个生活面的角色（第 4 批 + 第 5 批的数据层事实，按**并集**口径统计）。
# 补素材会让这份名单变化，那时按新数据更新即可 —— 这条哨兵的作用是"改少了会报警"。
FIVE_FACET_ROLES = frozenset(
    {
        "Alex", "Andy", "Claire", "Clint", "Demetrius", "Dwarf", "Elliott", "Evelyn",
        "Kent", "Krobus", "Lance", "Leah", "Lewis", "Linus", "Maru", "Morris",
        "Olivia", "Penny", "Pierre", "Robin", "Sandy", "Sophia", "Victor", "Willy",
        "Wizard",
        # 第 5 批（16 个角色收尾）：除 Marlon 挖不动之外全部到 5 面
        # （当时 Birdie 停在 4 面，第 6 批才补上，见下）
        "Abigail", "Caroline", "Emily", "George", "Gus", "Haley", "Harvey", "Jodi",
        "Marnie", "Sam", "Sebastian", "Shane", "Vincent",
        # ⚠ 第 6 批曾把 Birdie 从 4 面补到 5 面（词表补上「气候」「丈夫」之后，
        #   第 5 批为规避词表而改写的两条素材换回了原话）。**该角色已按用户口径删除**
        #   —— `SocialTab=HiddenAlways`、游戏里没有社交面板，所以不做她的对话；
        #   这条名单项随角色条目一起移除。她那一批原话仍是词表回归用例，
        #   留在 `bridge/tests/test_facet_wordlist.py` 里（见该文件 402 行附近）。
        # 第 7 批：Pam 从 4 面到 5 面 —— 词表补上「爱好」之后，她原话里
        # 「要是自己有个什么爱好就好了」终于判得出爱好面（此前"探不动"）。
        "Pam",
        # 第 9 批（2026-09-30 横向补素材）：Gunther 从 4 面到 5 面
        # （补上「图书馆的炉火」「社区花园」后爱好面有了具体落点）。
        "Gunther",
    }
)

# 还没做素材横向推广的角色（它们的无面抽象条目还没被具体素材换掉）。
# 这份清单是**待办**，不是事实断言：补掉其中一个从清单里删掉即可，不删也不会变红。
#
# 第 5 批清空到只剩 Marlon：Birdie（用 `Data/ExtraDialogue` 的原话补了 4 面，该角色
# 后来已删除）、Haley／Jodi／Shane／Vincent 都已补到 5 面且各自只剩 1 条无面核心。
# 删掉它们让这条哨兵**对它们生效**——否则回退到 2 条无面也不会有人报警。
UNFILLED_NO_FACET_ROLES = frozenset({"Marlon"})

# 每个 12 条窗口里至少要有这么多条"判得出生活面"的素材（2026-09-30）。
# `_pick` 会 `continue` 掉判不出面的素材，所以窗口里无面素材太密时它会空手而归、
# `suggestedFacet` 为空、"换面"静默失效 —— 而且不报错。宽池合并脚本的
# `fit_faceless` 在写入前保证这个数，
# `test_every_role_keeps_enough_faceted_material_in_every_window` 在数据被手改时挡住。
_WINDOW_MIN_FACED = 3


def _personas_topics():
    """遍历 data/personas 的每个 key：(文件名, key, preferredTopics)。"""

    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, profile in (payload.get("personas") or {}).items():
            voice_style = (profile or {}).get("voiceStyle")
            topics = (
                voice_style.get("preferredTopics") if isinstance(voice_style, dict) else None
            )
            yield path.name, name, list(topics or ())


def test_every_role_keeps_enough_faceted_material_in_every_window() -> None:
    """② 无面素材预算（2026-09-30 语义更新）：每个角色的**每个窗口**都要留下够多有面素材。

    旧口径是"每角色至多一条无面素材"，理由是原 docstring 里那句
    「每一条无面素材都**白占 6 条上限**里的一个位置，而且 `_pick` 会直接跳过它」。
    这两条前提**都不再成立**：

    * 上限从 6 条变成 `_PREFERRED_TOPICS_LIMIT`(=12)，而且窗口**逐轮滑动**——
      无面素材不再永久占位，只是被轮换稀释；
    * "`_pick` 跳过无面素材"仍然为真（`stage_policy._pick` 里
      `if not facet or facet == banned: continue`），但**跳过本身不再是问题**：
      只要窗口里还有够多有面素材，换面照样有得挑。

    所以真正要守的性质变成了后者：**任何一轮的窗口里都必须有足量有面素材**，
    否则那一轮 `_pick` 空手而归、`suggestedFacet` 为空、"换面"静默失效 ——
    失败方式依旧是"不报错"。宽池合并脚本用 `fit_faceless` 在写入前保证这一点，
    这条哨兵负责在数据被手改时把它挡住。
    """

    from stardew_ai_bridge.prompts import _topic_window_for_turn

    thin: dict[str, int] = {}
    for _fname, name, topics in _personas_topics():
        cid = canonical_npc_id(name)
        clean = [str(topic) for topic in topics if str(topic).strip()]
        if len(clean) <= _WINDOW_MIN_FACED:  # 池子本来就窄，轮换不生效，跳过
            continue
        worst = min(
            sum(1 for topic in _topic_window_for_turn(clean, turn) if _facet_of_topic(topic))
            for turn in range(len(clean))
        )
        if worst < _WINDOW_MIN_FACED:
            thin[cid] = worst

    assert thin == {}, (
        f"这些角色有窗口留不下 {_WINDOW_MIN_FACED} 条有面素材（换面会静默失效）：{thin}"
    )


def test_roles_lifted_to_five_facets_are_recorded() -> None:
    """第 4 批的覆盖结果（数据层事实）：这些角色现在有 5 个生活面。

    与 `test_narrow_material_roles_are_recorded` 同一性质：记录事实，不是判 bug。
    失败时先看是"补过头"还是"退回 5 面以下"，再按新数据更新这份名单。
    """

    covered: dict[str, set[str]] = {}
    for _fname, name, topics in _personas_topics():
        for topic in topics:
            facet = _facet_of_topic(topic)
            if facet:
                covered.setdefault(canonical_npc_id(name), set()).add(facet)

    reached = frozenset(cid for cid, facets in covered.items() if len(facets) >= 5)

    assert reached == FIVE_FACET_ROLES, (
        f"新达到 5 面（补过头或确实补上了）：{sorted(reached - FIVE_FACET_ROLES)}；"
        f"退回 5 面以下：{sorted(FIVE_FACET_ROLES - reached)}"
    )


# --- 12. 2026-09-23 第 5 批：两个只可能靠"人"守住的边界 -----------------------
#
# 第 5 批是横向推广的收尾：16 个角色补完，**2 个生活面的角色清零**。补完之后
# 低于 3 面的**只剩 Marlon 一个**（6 个面的 own 命中全 0，见第 4 批 §3.1）。
# 它不是"还没做"，是**做不了**——所以它值得一条断言，否则下一轮很容易被误当成
# 待办重新挖一遍。
#
# 本节原先还有一条同型的 Birdie 断言（她"索引里 0 条语料却仍有素材"，靠
# `Data/ExtraDialogue` 的原话补到 5 面）。**该角色已按用户口径删除**：游戏侧
# `SocialTab=HiddenAlways`、没有社交面板，所以不做她的对话，断言随之移除。
# 索引侧"`Data/ExtraDialogue` 曾整块漏掉"的缺口结论仍留在 `docs/` 与下面
# 第 14 / 15 节的历史注释里；她那批原话带来的扩词收益，由
# `bridge/tests/test_facet_wordlist.py` 的两条用例继续守着（见该文件 402 行附近）。

BELOW_THREE_FACET_ROLES = frozenset({"Marlon"})


# --- 13. 人设与**真原话**一致：多份 persona 的取用与一致性断言 ----------------
#
# 这节的哨兵一律走 `_persona_profile()`：同一角色可能散在多个文件里
# （`Shane` / `Sebastian` 各有两份，必须逐份核，只核一份会漏）。
#
# 起因是第 5 批查语料缺口时，顺手发现某个角色的 persona 与她本人的原话
# **互相矛盾** —— 那份人设是"当年没有语料时推出来的"，`tone` 说她喜欢钓鱼
# （她其实只散步）、`signatureMoves` 写她"不先寒暄、提自己用名字不用'我'"、
# `addressing.player` 写错、`sourceRefs` 指向**不存在**的
# `Characters/Dialogue/Birdie`。用户的验收口径是"**像这个人该说的话**"，
# 人设与真原话一致是这条的底线。
#
# ⚠ 那组哨兵（`_BIRDIE_REJECTED_PHRASES`："钓鱼"／"手作"／"针线"／"不先寒暄"／
# "用名字而不用"，以及人设、`sourceRefs` 两条断言）是针对 **Birdie** 写的。
# **该角色已按用户口径删除**（游戏侧 `SocialTab=HiddenAlways`、没有社交面板），
# 断言随角色条目一起移除；她那批原话仍是词表用例，留在
# `bridge/tests/test_facet_wordlist.py`。本节现存哨兵见下面的 Shane 一条。


def _persona_profile(npc_id: str):
    """返回该角色在 data/personas 里的 (文件名, profile)；多份时返回全部。"""

    out = []
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, profile in (payload.get("personas") or {}).items():
            if canonical_npc_id(name) == npc_id:
                out.append((path.name, profile or {}))
    return out


# --- 14. 2026-09-22 第 6 批：Shane 的救赎线换回来了，面数不降 -----------------
#
# 第 5 批为了让 Shane 补上三个新面，删掉了「戒掉坏习惯后的日常」——那是他
# **救赎线的核心**，是本批唯一承认的取舍争议。第 6 批的改法不是把它原样加回来
# （那条判不出生活面，会挤掉一个**有面**条目、把 5 面压到 4 面），而是换成
# 有面写法「改喝苏打水以后的日子」——出处在 `Data/Events/AnimalShop.zh-CN.json`
# 的 `3910974`（他自己的原话：「现在我已经改喝苏打水了」）。
#
# 让位的是**同属吃喝面**的「微波炉做的披萨卷」，不是那条无面人设核心
# 「值得信任的人」：无面核心是"每角色至多一条"里那一条，删它等于重犯第 5 批的错。
SHANE_REDEMPTION_TOPIC = "改喝苏打水以后的日子"


def test_shane_redemption_line_is_back_without_losing_a_facet() -> None:
    """救赎线回来了，而且面数仍然是 5 —— 两件事一起钉住。"""

    found = _persona_profile("Shane")
    assert found, "找不到 Shane 的 persona"

    for fname, profile in found:
        topics = profile["voiceStyle"]["preferredTopics"]

        assert SHANE_REDEMPTION_TOPIC in topics, f"{fname} 里没有救赎线素材"
        assert _facet_of_topic(SHANE_REDEMPTION_TOPIC) == "吃喝"
        # 让位的是同面的披萨卷，不是那条无面人设核心
        assert "值得信任的人" in topics, f"{fname} 把无面人设核心换掉了"
        assert _facet_of_topic("值得信任的人") is None

        facets = {_facet_of_topic(topic) for topic in topics} - {None}
        # 2026-09-30 第 9 批（宽池）：面覆盖改**父集** —— 扩库只可能加面，不会再
        # 精确等于这 5 面；"救赎线所在的这 5 面一个都没丢"才是这条要守的性质。
        assert {"工作或手艺", "吃喝", "家人朋友", "天气季节", "自己的状态或烦恼"} <= facets, (
            f"{fname} 丢了生活面：{sorted(facets)}"
        )
        assert len(topics) >= 7, f"{fname} 的素材条数变少了：{topics}"


def test_shane_material_is_identical_across_both_persona_files() -> None:
    """同一角色的多份 persona 必须同步 —— 第 4 批在 Wizard 上踩过这个坑。

    Shane 同时出现在 `vanilla.json` 与 `female-bachelors.json`；两份不同步时
    实际行为取决于加载顺序，改一份看不出问题、真机上却时好时坏。
    """

    found = _persona_profile("Shane")
    assert len(found) == 2, f"Shane 应该有 2 份 persona，实际 {len(found)}"

    material = {fname: profile["voiceStyle"]["preferredTopics"] for fname, profile in found}
    distinct = {tuple(topics) for topics in material.values()}

    assert len(distinct) == 1, f"两份 Shane 的素材不同步：{material}"


def test_roles_still_below_three_facets_are_recorded() -> None:
    """第 5 批收尾时，低于 3 个生活面的角色只剩两个（遍历全库）。

    与 `test_roles_lifted_to_five_facets_are_recorded` 反方向：那条记"补到了多少"，
    这条记"还差多少"。两条都失败在**回退**上——某个角色掉出 3 面却没人发现，
    在真机上表现为"翻来覆去只有一两个方向可聊"，而数据层一声不响。
    """

    covered: dict[str, set[str]] = {}
    for _fname, name, topics in _personas_topics():
        for topic in topics:
            facet = _facet_of_topic(topic)
            if facet:
                covered.setdefault(canonical_npc_id(name), set()).add(facet)

    low = frozenset(cid for cid, facets in covered.items() if len(facets) < 3)

    assert low == BELOW_THREE_FACET_ROLES, (
        f"新掉到 3 面以下（回退）：{sorted(low - BELOW_THREE_FACET_ROLES)}；"
        f"已经补上 3 面、可以从名单里删掉：{sorted(BELOW_THREE_FACET_ROLES - low)}"
    )


# --- 15. 2026-09-23 第 7 批：把"为绕开词表而改写的字面"换回原话 ----------------
#
# 起因是用户口径「主要是要自然一点，像真实对话，也要像这个人该说的话」：
# 前几批为了让素材判得出生活面，把若干条**原话的字面改了**（`跳舞`→`舞蹈`、
# `童年`→`小时候`、`儿子`→`孩子`…）。第 3 / 6 批把词表补齐之后，这些改写就
# 失去了理由 —— 而**原话才是最像这个人说的话的那个版本**，所以本轮把它们还回去。
#
# 两类改写必须分开处理（这是本轮的方法论，不是凭感觉）：
#
#   · **A 类 = 当初只为绕开词表**：词表补上之后原话判得出面，**还原**；
#   · **B 类 = 原话里的副面词会抢走主面**（`雾在毯子里看电视` 带上"下雨"就漂到
#     天气面、Clint 的"铁匠"漂到工作面、Sandy 的"在镇上"漂到镇上或消遣…）：
#     **保留改写**，那是有意的设计。
#
# 判据一律是 `_facet_of_topic` 回测：**预期面没变才还原**，变了就保留。
# 逐条回测产物在 `.tmp/facet-coverage/b7-restore.txt`：25 条候选中
# **还原 7 条 + 新增 1 条（Pam）= 8 条落进数据**，其余 17 条保留（下面三类理由各自可验证）。
RESTORED_TO_THE_ORIGINAL_LINE: dict[str, tuple[str, str, str]] = {
    # 角色: (还原后的素材, 还原前的改写, 面)
    "Emily": ("我和海莉是姐妹，这事我跟你说过吗？", "海莉是我妹妹", "家人朋友"),
    "Jas": ("我得自己发明游戏，感谢我的玩具们", "和玩具一起编出来的游戏", "爱好或消遣"),
    "Robin": (
        "现在的农田美得令人难以置信，我记得我读到过关于它的新闻",
        "记得读到过关于这片农田的新闻",
        "过去的回忆",
    ),
    # Kent 这条的还原版本之所以还判得出面，靠的是原话后半句的「疲惫」——
    # 也就是说"失眠"本身仍然不在词表里，但整句是他的原话且面不变，所以还原。
    "Kent": (
        "我有失眠的毛病，所以如果我看起来很疲惫的话，请你不要介意",
        "夜里睡不着的毛病",
        "自己的状态或烦恼",
    ),
    "Vincent": (
        "我爸爸几年前建造了那座木桥，这样我就可以在夏天去看潮汐池了",
        "夏天去潮汐池看的那片浅水",
        "天气季节",
    ),
    "Abigail": ("我父母弄的我压力好大", "他们弄得我压力好大", "自己的状态或烦恼"),
    "Dwarf": (
        "我有很多关于我的朋友和家人的回忆，他们都和那些矿井有关",
        "很久没见的那些家人",
        "家人朋友",
    ),
    # Pam 不是"还原"而是"新增"：她原话里的「爱好」二字原先判不出面，
    # 所以第 5 批直接放弃了这个面（"探不动"），素材**一条都没有**。
    "Pam": ("要是自己有个什么爱好就好了", "", "爱好或消遣"),
}


@pytest.mark.parametrize("npc_id", sorted(RESTORED_TO_THE_ORIGINAL_LINE))
def test_restored_material_is_the_original_line_and_keeps_its_facet(npc_id: str) -> None:
    """还原后的素材**真的在数据里**，而且面与还原前**一模一样**。

    两个方向都要钉：① 新字面进去了；② 旧字面（那份为绕开词表而改写的说法）
    不许再回来 —— 否则下一轮有人按旧报告"修回去"，面归属就悄悄变了。
    """

    restored, previous, facet = RESTORED_TO_THE_ORIGINAL_LINE[npc_id]

    assert _facet_of_topic(restored) == facet, f"{npc_id} 的还原版没落到 {facet}"
    if previous:
        assert _facet_of_topic(previous) == facet, (
            f"{npc_id} 的改写版本来就不在 {facet}，这条不是 A 类还原"
        )

    found = _persona_profile(npc_id)
    assert found, f"找不到 {npc_id} 的 persona"
    for fname, profile in found:
        topics = profile["voiceStyle"]["preferredTopics"]
        assert restored in topics, f"{fname} 里没有还原后的原话素材：{topics}"
        if previous:
            assert previous not in topics, f"{fname} 里旧改写还留着：{topics}"


def test_pam_finally_has_a_hobby_facet() -> None:
    """Pam 的爱好面是第 5 批公开记为"探不动"的那一个（词表不收「爱好」）。

    第 6 批补词、第 7 批把她那句原话写进素材 —— 这条钉住"补词必须落到素材上"，
    否则又是一次"词表认得出、而 material 里根本没有"的空转。
    """

    topics = _preferred_topics("Pam")
    assert "要是自己有个什么爱好就好了" in topics
    # 2026-09-30 第 9 批（宽池）：条数与面覆盖都改成**下界 / 父集** ——
    # 扩库让"恰好 9 条、恰好这 5 面"不再成立，但"爱好面没丢、素材没变少"仍要守。
    assert len(topics) >= 9, f"Pam 的素材条数变少了：{topics}"

    facets = {_facet_of_topic(topic) for topic in topics} - {None}
    assert {"工作或手艺", "吃喝", "家人朋友", "过去的回忆", "爱好或消遣"} <= facets, (
        f"Pam 的面覆盖少了：{sorted(facets)}"
    )
    # 那条无面人设核心仍在（"每角色至多一条"，不许为了凑面数删掉）
    assert "如何在麻烦里保留选择" in topics
    assert _facet_of_topic("如何在麻烦里保留选择") is None


# 还原原话的**代价**，一并记下来：原话比改写版"多带词"，其中三条带的是**别的面**的词。
# 这不改变任何机制（`narrow_topic_pool` 一直按主面收窄），但会在两处看得见：
#   ① `_facet_hits`（"她这一轮聊了哪些面"的统计口径，命中即算）会多记一个面；
#   ② 禁那个次要面时，这条素材**仍留在落点池里**，文本里也仍写着被禁面的词。
# 与 `test_alex_cross_facet_topic_penetration_is_recorded` 同一类事实，只是这三条
# 是本轮**新引入**的 —— 所以单独钉住，免得日后被当成"机制坏了"。
SECONDARY_FACET_PENETRATION_ADDED_BY_RESTORING: dict[str, tuple[str, str, str]] = {
    # 角色: (还原后的素材, 主面, 原话里带出来的次要面)
    "Emily": ("我和海莉是姐妹，这事我跟你说过吗？", "家人朋友", "玩家自己"),
    "Vincent": (
        "我爸爸几年前建造了那座木桥，这样我就可以在夏天去看潮汐池了",
        "天气季节",
        "家人朋友",
    ),
    "Dwarf": (
        "我有很多关于我的朋友和家人的回忆，他们都和那些矿井有关",
        "家人朋友",
        "过去的回忆",
    ),
}


@pytest.mark.parametrize("npc_id", sorted(SECONDARY_FACET_PENETRATION_ADDED_BY_RESTORING))
def test_secondary_facet_penetration_added_by_restoring(npc_id: str) -> None:
    """三条还原后的素材**多带了一个次要面**。

    2026-09-23 起 `narrow_topic_pool` 改为「命中即摘」，所以禁**次要**面时它们也会
    被摘掉 —— 那是本次的目的（原先的"主面穿透"正是漏掉 Harvey 那类素材的成因）。
    """

    topic, main, secondary = SECONDARY_FACET_PENETRATION_ADDED_BY_RESTORING[npc_id]

    assert _facet_of_topic(topic) == main
    assert _facet_hits(topic) == {main, secondary}
    # 禁**次要**面时也会被摘掉（命中即摘，2026-09-23）
    assert topic not in narrow_topic_pool(_prompt_topics(npc_id), secondary)
    # 禁**主**面时同样
    assert topic not in narrow_topic_pool(_prompt_topics(npc_id), main)


# B 类改写**保留**的逐句理由：原话里的那个副面词会改主面，所以不能还原。
# 这不是"忘了还原"，是**有意的设计** —— 这里把理由本身钉成断言，
# 让下一个想"顺手还原"的人先看到回测结果（第 7 批 25 条候选里 17 条属于这一类）。
#
# 每条的值为 `(原因, 原话现在落在哪个面)`：
#
#   * `drift`        —— 原话落**别的面**，会抢走主面；
#   * `no-facet`     —— 原话**判不出任何面**，还原等于让这条素材永远选不上
#                       （`rotation_topic_slot._pick` 会直接跳过无面条目）；
#   * `same-fragile` —— 面没变，但靠的是词表里的**巧合子串**，且原话本身
#                       读起来不像一条落点（Lewis 那句是他自己嘀咕的省略句）。
KEPT_REWRITES_WHOSE_ORIGINAL_WOULD_DRIFT: dict[tuple[str, str, str], tuple[str, str]] = {
    # (角色, 保留的改写, 原话): (原因, 原话的面)
    ("Shane", "忙起来那股压力", "工作压力"): ("drift", "工作或手艺"),
    ("Sophia", "毯子和电视", "下雨了！在这样的日子里，我只想窝在毯子里看电视。"): (
        "drift", "天气季节",
    ),
    # 2026-09-25：「刚搬来镇上那阵子，和现在比变化有多大」已从 preferredTopics 移除
    # （8 条额度内让位给「自己的状态或烦恼」面），这条 drift 裁决随之失效 —— 原话
    # 「她刚搬来镇上时住的那间旧房子」现在与它同面（都落「镇上或邻里」），不再漂。
    ("Sandy", "如果你遇见我的朋友艾米丽，记得帮我打个招呼",
     "啊你好！如果你在镇上遇见我的朋友艾米丽，记得帮我打个招呼？"): ("drift", "镇上或邻里"),
    ("Clint", "我爸爸以前也是干这一行的", "我当这个铁匠都是因为我爸爸非要让我当啊"): (
        "drift", "工作或手艺",
    ),
    ("Clint", "我小时候想干的根本不是这行", "我小时候的梦想不是当铁匠"): ("drift", "工作或手艺"),
    ("Demetrius", "女儿玛鲁总在屋里帮我打下手", "玛鲁有时也会在实验室里帮我一把"): (
        "drift", "工作或手艺",
    ),
    ("Vincent", "在镇上到处乱跑找虫子", "我想去捉虫子，但每次搞得脏兮兮又会被妈妈骂"): (
        "drift", "家人朋友",
    ),
    ("Gunther", "镇上那些跑野外的探险的人", "不久之后，探险家公会在小镇里成立"): (
        "drift", "工作或手艺",
    ),
    ("Sam", "以前住在城里的那段日子", "我有告诉过你我们一家人曾经是住在城里的吗？"): (
        "drift", "家人朋友",
    ),
    ("Alex", "祖父母把我带大", "我别无他法只能搬到我的爷爷奶奶那里去住"): ("no-facet", ""),
    ("Alex", "小时候那些不太快乐的日子", "我的童年或许不怎么快乐，但至少它让我变得很坚强"): (
        "no-facet", "",
    ),
    ("Claire", "没人的时候偷偷练的舞蹈", "我在没人的时候练习跳舞。我还没被别人看到过呢！"): (
        "no-facet", "",
    ),
    ("Claire", "换完班之后那股疲惫", "每次换班后我都觉得精疲力尽，但我又确实需要用钱"): (
        "no-facet", "",
    ),
    ("Leah", "以前那间又小又旧的小木屋", "这房子比我旧旧的小木屋好多了！我不想念它。"): (
        "no-facet", "",
    ),
    ("Marnie", "Shane 和 Jas 这两个孩子", "我的侄子谢恩已经在我这待了几个月了"): ("no-facet", ""),
    # Lewis 的原话「哼……收税……春季节日开销……」之所以仍落在天气面，是因为
    # **「春季节日开销」里含子串「季节」** —— 巧合命中，不是语义命中；而那句
    # 断断续续的自言自语作为落点条目也不合格。保留改写版更稳。
    ("Lewis", "春天收税和节日的开销", "哼……收税……春季节日开销……"): (
        "same-fragile", "天气季节",
    ),
}


@pytest.mark.parametrize(
    ("npc_id", "kept", "original", "kind", "expected_original_facet"),
    [(npc, kept, original, kind, facet) for (npc, kept, original), (kind, facet) in
     KEPT_REWRITES_WHOSE_ORIGINAL_WOULD_DRIFT.items()],
)
def test_kept_rewrites_are_kept_for_a_reason(
    npc_id: str, kept: str, original: str, kind: str, expected_original_facet: str
) -> None:
    """保留改写的三类理由，逐句可验证（这条红了说明词表变了，要重新裁决）。"""

    kept_facet = _facet_of_topic(kept)
    assert kept_facet is not None, f"{npc_id} 保留的素材本身判不出面：{kept}"

    original_facet = _facet_of_topic(original)
    assert original_facet == (expected_original_facet or None), (
        f"{npc_id} 的原话现在落在「{original_facet}」（回测记的是 "
        f"「{expected_original_facet or '无面'}」）—— 词表变了，这条改写该不该留要重新判"
    )

    if kind == "drift":
        assert original_facet != kept_facet, (
            f"{npc_id} 的原话不再漂到别的面（现在与改写版同为「{kept_facet}」）—— "
            f"可以还原了，改数据 + 重跑全量回测"
        )
    elif kind == "no-facet":
        assert original_facet is None
    else:
        assert kind == "same-fragile"
        assert original_facet == kept_facet


# --- 16. 无面折算：判不出面的轮次不许在计数里消失（2026-09-22） -----------------
#
# 起因：云端实测里她连说三轮酿酒（工作 → **词表判不出** → 工作），槽位一次都没触发。
# `facetRepeat` 数的是"最近 3 轮里同一面出现 ≥2 次"，而**判不出面的轮次在计数里
# 等于不存在** —— 这种形状窗口内只算 1 次。
#
# 依据（不是猜的）：两批云端实测共 5 轮「无面」，逐条判 **5/5 都是「她说了具体物、
# 但词表没收录」**（酒 / 标签 / 葡萄 / 发酵 / 桶 / 塞 / 封蜡），**没有一条**是
# "她什么实质都没说"。丢弃它们等于把她的持续话题当成没发生。
#
# 离线形状矩阵（`.tmp/topic-probe/facet_shape_matrix.py`，用真实批次回复作文本）：
#   「工作 / 无面」交替     → 折算前 i=3、5、7 间歇触发（漏掉一半）；折算后 i=2 起稳触发
#   「工作 / 无面 / 吃喝 / 无面」 → 折算前 **8 轮一次都不触发**；折算后 i=2 触发
#   「工作 / 吃喝 / 镇上」轮转   → 折算前后都**不该**触发（她本来就在换面）

# 判不出任何生活面的真形态（量词指代句，代码注释里点名过；由下面的断言自证有效性）
NO_FACET_REPLIES = [
    "那批还得再等等。",
    # 2026-09-23：原第二句是「刚封好的那批已经进桶了。」—— 补 `封口|封上|封好` 之后
    # 它**判得出面了**（工作面），样本因此失效。去掉"封好的"三字后仍是真实形态的
    # 量词指代句（且「桶」按既定口径**不在**词表里）。这不是"为了过测试改数据"：
    # 那句真实回复现在**本来就该**判成工作面，这里只是换一个仍无面的样本。
    "那批已经进桶了。",
]


def test_unjudged_turns_are_not_dropped_from_the_repeat_count() -> None:
    """「工作 → 判不出面」要和「工作 → 工作」一样触发 —— 这是本次修的漏判形状。"""

    for reply in NO_FACET_REPLIES:
        assert _facet_hits(reply) == set(), f"这句现在判得出面了，样本失效：{reply}"

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[BREW_REPLIES[0], NO_FACET_REPLIES[0]],
    )

    assert slot["bannedFacet"] == "工作或手艺"


def test_the_inherited_facet_is_the_previous_turn_not_a_default() -> None:
    """继承的是**上一轮的面**：她刚从工作换到镇上，判不出面的那轮该算镇上。"""

    slot = rotation_topic_slot(
        SOPHIA_TOPICS,
        recent_replies=[TOWN_REPLIES[0], NO_FACET_REPLIES[0]],
    )

    assert slot["bannedFacet"] == "镇上或邻里"


def test_an_unjudged_first_turn_invents_no_facet() -> None:
    """边界：第一轮就判不出面时不许凭空造面（没有"上一轮"可继承）。"""

    assert rotation_topic_slot(
        SOPHIA_TOPICS, recent_replies=[NO_FACET_REPLIES[0]]
    ) == {}


# --- 17. 真机 8 轮实录：折算救回的那条链路（2026-09-23 00:5x） -------------------
#
# 数据来源：`.tmp/topic-probe/cloud_rotation_probe.py --stage friend --turns 8`，
# **8 请求 / 96,912 tokens**，cloud provider，与游戏端 payload 同形
# （intent=topic、message=""、compact、history 只含 assistant 项、无玩家输入）。
# 完整表格与三条结论见 `docs/report-facet-rotation-2026-09-22.md` §7。
#
# 这一节钉住**当时唯一一次真实触发**，而它恰好是"改前不触发、改后触发"的形状：
#
#   轮次   她的原话判成什么面      说明
#   1      工作或手艺
#   2      过去的回忆
#   3      天气季节             ← 靠次要从句里的「风会软下来」命中（报告 §7.4）
#   4      （无面）             ← 「酒液 / 分装」都不在词表
#   5      工作或手艺           ← 槽位在这里触发，禁「天气季节」，她照做了
#
# **改前**：窗口 [工作, 回忆, 天气, 无面] 里「天气季节」只 1 次 ⇒ 不触发；
# **折算后**：第 4 轮继承第 3 轮的「天气季节」⇒ 2 次 ⇒ 触发。
#
# ⚠ **判面序列本身也是断言**，因为词表一改它就会变 —— 比如报告 §8 那批缝纫词
# （`亚麻|棉布|帆布|呢绒` 等）一旦落地，第 4 轮就会从"无面"变成"工作或手艺"。
# 那时这条用例会红，那是**提醒你同步报告**，不是噪音 —— 别直接把期望值改掉了事。
#
# **2026-09-23：预判应验了**，而且比预判多一处 —— 第 3 轮也多了工作面（不只是第 4 轮）。
# 期望值已按实测更新，报告 §7 与 §15 同步；折算机理本身改由下面的**构造样本**用例钉住
# （8 轮实录的前 3 轮已经够触发了，折算不再是第 5 轮触发的唯一原因）。

REAL_8_TURNS = [
    "嘿，刚把今天最后一张便签贴到酒瓶上，手还有点粘。这批新酿闻着比上一批甜一点，我不敢太早下结论。你晚上都在忙什么呀？",
    "哇，这批苹果的颜色比我记得的还亮。我本来只打算看一眼就回屋，结果又蹲下来挨个转了半圈。你看这颗，蒂上还挂着一小片叶子，我差点舍不得摘它。",
    "哦哦哦，我想起来了！艾米丽给过我一整块亚麻布，我一直没舍得动它。要不今晚先裁个样子出来……等等，秋十八了，风会软下来。先放着吧，明天早点起，脑子清醒再说。",
    "今晚这批酒液比昨天清亮多了，我盯着看了好一会儿。再放两三天就该分装，给你留一瓶尝尝。还有那块亚麻布，等这批酒弄完，我先裁一小块试试手。",
    "嘶，贴标签贴到第三排，手指上全是胶。本来只想核对一下日期，结果一下就蹲到现在。你看我手腕这儿，还印着一条没洗掉的墨。",
    "刚才去广场那边的杂货铺送酒，听见玛丽和皮埃尔隔着柜台吵。就为了一篮子放错摊位的南瓜，两个人谁也不肯先挪。我抱着箱子站在那儿，想劝又插不上嘴。最后还是克林特出来，把南瓜搬到墙角，两人就都不说了。你要是在场，会不会也觉得那南瓜无辜得很。",
    "哇，你看这批的颜色——我本来只想看看发酵罐，结果一待就待到现在。而且我今天在酒窖角落翻到了去年写的那张配方，纸上还有一小块酒渍。要不要一会儿我念给你听？",
    "刚洗完最后一个发酵罐，手还凉着呢。对了，刚才在阁楼翻箱子，翻出刚搬来那阵子的旧屋钥匙，锈得都不像钥匙了。那时候房里就一张旧床垫，晚上抱着杯子蹲在窗边看星星。先不忙着收，我再瞅它两眼。",
]

REAL_8_FACETS: tuple[tuple[str, ...], ...] = (
    ("工作或手艺",),
    ("过去的回忆",),
    # 2026-09-23 补「亚麻|棉布|帆布|呢绒|裁缝|裁剪」之前这里是 ("天气季节",) —— 第 3 轮
    # 那句"艾米丽给过我一整块亚麻布…先裁个样子出来"当时只有"风会软下来"命中天气面。
    # 补词后它**自带工作面**，于是这一轮变成两面。
    # 2026-09-25 第 10 批补「斯嘉丽|海莉|维克多|艾米丽」后**变三面** ——
    # 那一轮里出现了「艾米丽」，家人朋友面因此命中。这是词表扩容的**预期结果**。
    ("天气季节", "家人朋友", "工作或手艺"),
    # 同理：第 4 轮的"那块亚麻布，等这批酒弄完，我先裁一小块试试手"从"判不出面"变成
    # **工作面** —— 这正是下面注释里预判过的事（它猜的是第 4 轮由 `亚麻` 触发，
    # 实际第 3、4 轮都受影响）。
    ("工作或手艺",),
    ("工作或手艺",),
    ("镇上或邻里",),
    ("工作或手艺",),
    ("工作或手艺", "过去的回忆"),
)


def test_the_measured_eight_turns_still_resolve_to_these_facets() -> None:
    """真机 8 轮的逐轮判面 —— 词表或折算一改就红，提醒同步报告 §7。"""

    assert len(REAL_8_TURNS) == len(REAL_8_FACETS)

    for index, (reply, expected) in enumerate(
        zip(REAL_8_TURNS, REAL_8_FACETS), start=1
    ):
        actual = tuple(sorted(_facet_hits(reply)))

        assert actual == tuple(sorted(expected)), (
            f"真机第 {index} 轮的判面变了：期望 {expected}，实际 {actual}。"
            "若这是词表落地的预期结果，请一并更新报告 §7 与本期望值。"
        )


def test_the_fold_still_carries_a_facetless_turn_into_the_count() -> None:
    """折算本身仍在工作：一串「工作 / 无面 / 无面」里，无面轮照样计数。

    本条原先叫 `test_the_fifth_turn_fires_only_because_of_the_fold`，用的是 8 轮实录的
    前 3 轮。**2026-09-23 补词之后那个前提失效了**：第 3 轮现在自带「工作或手艺」
    （亚麻布 / 裁），前 3 轮就已经 2 次同面、槽位提前一轮触发 —— 那是**改善**，
    但本条要钉的是**折算机理本身**，所以换成一组不含任何实词的构造样本。
    实录那边的变化由下面那条记录。
    """

    replies = [BREW_REPLIES[0], "那批还得再等等。", "那批已经进桶了。"]

    # 后两句都判不出面，全靠折算继承第 1 轮的工作面 ⇒ 窗口内 3 次
    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=replies)

    assert slot["trigger"] == "facetRepeat"
    assert slot["bannedFacet"] == "工作或手艺"


def test_the_eight_turns_now_fire_one_turn_earlier() -> None:
    """补词之后，真机 8 轮**第 3 轮就够触发**了（原先要等到第 5 轮靠折算才触发）。

    这是词表落地的**收益**：第 3 轮从"只有天气面"变成"天气 + 工作"，窗口里的工作面
    因此达到 2 次；原先这条链路要靠第 4 轮的无面折算才补得上。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=REAL_8_TURNS[:3])

    assert slot["trigger"] == "facetRepeat"
    assert slot["bannedFacet"] == "工作或手艺"
