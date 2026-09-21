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
SOPHIA_TOPICS = ["酒窖里这一批新酿", "画布上还没画完的那一块",
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
    断言跟着换成新句；「禁什么 + 去哪一面」这两半本身没变。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert slot["bannedFacet"] == "工作或手艺"
    assert "别再以这一面做新的落点" in slot["instruction"]
    assert "都不算换" in slot["instruction"]  # 「换物件/换时段/换个说法」都不算
    assert slot["suggestedFacet"] == "镇上或邻里"
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
        "suggestedTopic": "镇上今天谁在广场上吵",
    }}

    compact = _compact_stage_policy(policy, include_response_order=False)

    assert compact["topicSlot"]["bannedFacet"] == "工作或手艺"
    assert compact["topicSlot"]["suggestedTopic"] == "镇上今天谁在广场上吵"


def test_slot_reaches_the_live_compact_card_and_the_provider() -> None:
    """端到端：`_build_context` 与 `PromptBuilder` 之后，槽位在发送给模型的消息里。"""

    from stardew_ai_bridge.app import _build_context
    from stardew_ai_bridge.prompts import PromptBuilder

    body = _payload("Sophia", _history(BREW_REPLIES), SOPHIA_MODS)
    context, _ = _build_context(body)
    messages = PromptBuilder().build(context, body["message"], compact=True)
    slot = _card(messages, "stage_execution_card")["topicSlot"]

    assert slot["bannedFacet"] == "工作或手艺"
    assert slot["suggestedTopic"] == "镇上今天谁在广场上吵"
    blob = json.dumps(messages, ensure_ascii=False)
    assert "别再以这一面做新的落点" in blob


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
    assert "镇上今天谁在广场上吵" in blob


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

    assert "别再以这一面做新的落点" in with_slot
    assert "别再以这一面做新的落点" not in without_slot
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
        ("Sophia", ["酒窖里这一批新酿", "画布上还没画完的那一块",
                    "镇上今天谁在广场上吵", "她刚搬来镇上时住的那间旧房子"]),
        ("Elliott", ["卡住的那一段稿子", "海风里退潮后的那片沙滩",
                     "手边正在读的那本书", "你上次提到的那个地方"]),
    ],
)
def test_试点两人的素材已改写(npc_id: str, expected: list[str]) -> None:
    """用户点名的两组改写（只在这两人身上试点，其余角色等效果）。"""

    assert _preferred_topics(npc_id) == expected


@pytest.mark.parametrize(
    ("npc_id", "mods"),
    [("Sophia", SOPHIA_MODS), ("Elliott", ELLIOTT_MODS)],
)
def test_rewritten_topics_keep_the_guidance_within_the_compact_limit(
    npc_id: str, mods: list[str]
) -> None:
    """同源化的代价：池子变长会把 roleGuidance 推向 240 字上限，超了就白改。"""

    from stardew_ai_bridge.app import _build_context

    _, messages = _build_context(_payload(npc_id, [], mods))
    guidance = _card(messages, "stage_execution_card")["conversationLead"]["roleGuidance"]

    assert len(guidance) <= 240, f"{npc_id} 的 roleGuidance 有 {len(guidance)} 字"
    for topic in _preferred_topics(npc_id):
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

    索菲亚的 `roleGuidance` 第一句是「先明确接住玩家点名的酒、酒窖、喝一口等当前
    对象」——不加豁免，两条硬指令会在同一张卡里互相封口，等于把"两层打架"搬个位置。

    2026-09-22：豁免从 instruction 的**括号从句**升成 `topicSlot` 的**一级字段**
    `playerAnchor`。旧写法是「别再以这一面做新的落点（玩家本轮自己点名的对象仍要
    接住；他要是继续追问这一面，就顺着他的方向聊，别为了换面绕开它）」——位置上是从句、
    语气上是提醒，模型很容易在"本轮由你主动把话头换一次"这条主线下面读成可选项。
    而它是"方向盘在玩家手里"的**唯一**措辞层保障：代码层的撤回只在"玩家点的正好是
    被禁那一面"时生效，玩家点名别的面时全靠这一条。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert "硬约束" in slot["playerAnchor"]
    assert "先接住" in slot["playerAnchor"]
    assert "顺着聊" in slot["playerAnchor"]
    # 升成独立字段之后，instruction 里不再有那段括号从句（不留第二份措辞）
    assert "玩家本轮自己点名的对象仍要接住" not in slot["instruction"]
    # 但禁令本身一个字都不许少
    assert "别再以这一面做新的落点" in slot["instruction"]


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

    素材只覆盖两面的角色（索菲亚＝工作／镇上）在交替对话里，`used` 会等于它的全部
    素材面。旧写法此时**每一轮**都落进"没有候选"的泛化分支，建议指向它根本没有素材
    的面（吃喝、天气、家人…）——"换到空的"比不换更差。禁令只针对 `banned` 这一面，
    回到别的面并不违规。
    """

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=ALTERNATING_REPLIES)

    assert slot["suggestedTopic"] in SOPHIA_TOPICS
    # 确实用了一条"最近出现过"的面的素材，也就是降级分支真的生效了
    assert _facet_of_topic(slot["suggestedTopic"]) == "镇上或邻里"
    assert slot["suggestedTopic"] == "镇上今天谁在广场上吵"


# --- 7. 落点池收窄：拿掉被禁面 -----------------------------------------------


def test_narrow_topic_pool_drops_the_banned_facet() -> None:
    narrowed = narrow_topic_pool(SOPHIA_TOPICS, "工作或手艺")

    assert narrowed == ["镇上今天谁在广场上吵", "她刚搬来镇上时住的那间旧房子"]


def test_narrow_topic_pool_without_a_ban_is_the_original_pool() -> None:
    assert narrow_topic_pool(SOPHIA_TOPICS, None) == SOPHIA_TOPICS
    assert narrow_topic_pool(SOPHIA_TOPICS, "") == SOPHIA_TOPICS


def test_narrow_topic_pool_returns_empty_when_the_whole_pool_is_banned() -> None:
    """全被禁光时返回空列表 —— 调用方据此退回不点名的中性说法。

    **不能**退回原始列表：那等于把被禁面又写回 prompt。
    """

    assert narrow_topic_pool(["酒窖里这一批新酿"], "工作或手艺") == []


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
    assert "酒窖里这一批新酿" not in guidance
    assert "画布上还没画完的那一块" not in guidance
    assert "镇上今天谁在广场上吵" in guidance


def test_guidance_keeps_the_whole_pool_when_no_slot_fires() -> None:
    """未触发的轮次必须原样保留四条 —— 收窄只在触发轮生效，不是常态缩池。"""

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
    for topic in SOPHIA_TOPICS:
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
    # 被禁面的素材条目一条都不许留在池子里（模板里"谈过酿造或绘画"那句是通用轮换
    # 指令、不是落点池，所以这里只逐条核对**素材**，不整段扫面关键词）。
    for topic in SOPHIA_TOPICS:
        if _facet_of_topic(topic) == slot["bannedFacet"]:
            assert topic not in guidance, topic


# --- 9. 素材覆盖：禁掉任一面之后还剩得下东西吗 --------------------------------


def _prompt_topics(npc_id: str) -> list[str]:
    """`_build_context` 真正喂给 stage policy 的那一份 preferredTopics。"""

    from stardew_ai_bridge.prompts import _preferred_topics_for_prompt

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
                return topics
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

    * `Sophia` 的 4 条只有两面（工作或手艺 / 镇上或邻里）→ 剩 2 条，触发轮次的建议
      方向因此只在"镇上"里挑；
    * `Alex` 的缺口**已关闭**（2026-09-21 三次拆面，见第 10 节）：他的 4 条里原本有 3 条
      落进"工作或手艺"—— 体育词（四分卫、投球、俯卧撑）被 `四分卫|投球|俯卧撑|训练|运动`
      这一段正则收编，禁工作面后只剩一条不映射任何面的素材（`_facet_of_topic` 返回
      `None`），**不能作为建议候选**，于是每一轮都走"换到另一个生活面（…）"的泛化降级。
      运动词归位到"爱好或消遣"之后，他名下已经**没有任何工作面条目**，禁工作面等于不
      收窄，候选回到 3 条。

    这是数据层的事：补素材会让这两条断言失败，那时按新数据更新即可。
    """

    assert len(narrow_topic_pool(_prompt_topics("Sophia"), "工作或手艺")) == 2
    assert narrow_topic_pool(_prompt_topics("Alex"), "工作或手艺") == _prompt_topics("Alex")
    assert _facet_of_topic("职业选手目标，以及后来发现的微不足道的小事") is None


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
    """拆面的结果本身：4 条素材的新归属（第 4 条仍不映射任何面）。"""

    assert {topic: _facet_of_topic(topic) for topic in _prompt_topics("Alex")} == {
        "全明星四分卫和夹克上的小星星": "爱好或消遣",
        "海滩、投球和镇上的朋友": "镇上或邻里",
        "俯卧撑、酸痛与进步": "爱好或消遣",
        "职业选手目标，以及后来发现的微不足道的小事": None,
    }


def test_alex_gets_a_concrete_suggestion_after_the_sports_split() -> None:
    """③ 核心验收：Alex 谈完农场被要求换面时，给出**具体**建议而不是泛化降级。

    改前面貌：4 条里 3 条被"工作或手艺"收编 ⇒ 禁工作面后只剩一条无面素材 ⇒
    `suggestedTopic` 恒为空，instruction 退化成"换到另一个生活面（吃喝、天气季节…）"。
    改后：素材里没有工作面条目，候选落到"爱好或消遣"这一面上。
    """

    slot = rotation_topic_slot(_prompt_topics("Alex"), recent_replies=ALEX_FARM_REPLIES)

    assert slot["bannedFacet"] == "工作或手艺"
    assert slot["suggestedFacet"] == "爱好或消遣"
    assert slot["suggestedTopic"] == "全明星四分卫和夹克上的小星星"
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

    assert slot["suggestedFacet"] == "爱好或消遣"
    assert slot["suggestedTopic"] == "全明星四分卫和夹克上的小星星"
    assert slot["suggestedTopic"] in guidance
    # 工作面素材：Alex 本来就没有，所以禁令摘不掉任何一条他名下的素材。
    for topic in _prompt_topics("Alex"):
        if _facet_of_topic(topic) == "工作或手艺":
            assert topic not in guidance, topic


def test_sports_talk_now_reads_as_hobbies_repeat() -> None:
    """行为面的变化：同两轮回复，改前判"工作或手艺"、改后判"爱好或消遣"。

    `banned` 是**按素材占比**在重复面里挑的（`rotation_topic_slot` 的 tie-break），
    所以这里禁的会是爱好面，建议退到那条主面为"镇上或邻里"的素材上。
    """

    slot = rotation_topic_slot(_prompt_topics("Alex"), recent_replies=ALEX_PUSHUPS_REPLIES)

    assert slot["bannedFacet"] == "爱好或消遣"
    assert slot["suggestedFacet"] == "镇上或邻里"


def test_alex_cross_facet_topic_penetration_is_recorded() -> None:
    """**次要面穿透**（记录事实，不是判 bug）：跨面条目的主面之外仍留着被禁面的词。

    「海滩、投球和镇上的朋友」同时命中三个面，`_facet_of_topic` 按声明顺序取主面
    = "镇上或邻里"，于是禁"爱好或消遣"时它**不会**被 `narrow_topic_pool` 摘掉，
    而文本里仍写着"投球"（被禁面的词）。这与"槽位禁某面、guidance 仍列该面"那种
    **同面冲突**不是一回事：`narrow_topic_pool` 一直按**主面**收窄，那条规则没变。

    影响面是可数的：48 个角色里只有 Alex 的这一条素材跨界。真要连次要面一起摘，
    得让 `narrow_topic_pool` / `_pick` 改用 `_facet_hits`（命中即摘）——那是另一轮
    机制改动，会改变全部角色的收窄口径，不在这里顺手做。
    """

    topic = "海滩、投球和镇上的朋友"

    assert _facet_of_topic(topic) == "镇上或邻里"
    assert _facet_hits(topic) == {"爱好或消遣", "镇上或邻里", "家人朋友"}
    assert topic in narrow_topic_pool(_prompt_topics("Alex"), "爱好或消遣")
