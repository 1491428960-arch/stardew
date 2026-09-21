"""批次 4：生活面**硬槽位**（`topicSlot`）与 4b 的数据改写（2026-09-21）。

诊断结论是"机制为主、数据为辅"：索菲亚的 `preferredTopics` 已有 4 条跨簇素材、
`roleGuidance` 也已有动作式轮换指令，**仍然连着 6 轮画／酒**。所以问题不是
"候选不够"，而是候选池只是**语义层软约束**，压不过职业轴在词频层与具体性层的
双重牵引。这一批把生活面从"候选池"提升为**每轮由代码指定的槽位**：

* `rotation_topic_slot(preferred_topics, recent_replies=...)` 读最近
  `_FACET_LOOKBACK` 轮 NPC 回复，用 `_LIFE_FACET_PATTERNS` 匹配落点簇；
  **同一个面连着两轮**就把该面列为硬禁用，并从该角色自己的素材里挑一条
  **不同面**的作为指定项；
* 只在触发时产出，其余轮次零成本（字段不进 prompt）；
* 单一层级：只点名被禁的那一面 + 一个可去的面，不留第二个可比对象
  （`stage_policy` 里记过两次"两个层级 → 模型挑最松读法"的教训）。

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
    _facet_of_topic,
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
    """用户要的两半都要在：**禁什么** + **改去哪一面**。"""

    slot = rotation_topic_slot(SOPHIA_TOPICS, recent_replies=BREW_REPLIES)

    assert slot["bannedFacet"] == "工作或手艺"
    assert "不要再出现这一面" in slot["instruction"]
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
    assert "本轮不要再出现这一面" in blob


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
    """对照实验：把槽位机制关掉，prompt 里**没有任何**"这一面不要再出现"的指令。

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

    assert "本轮不要再出现这一面" in with_slot
    assert "本轮不要再出现这一面" not in without_slot
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
