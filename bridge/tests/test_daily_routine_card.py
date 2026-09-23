"""L3 静态作息（persona `dailyRoutine`）的注入通道与降级路径。

**这一层要解决的问题**：此前 `data/personas/*.json` 全无作息字段（4 份文件全角色
扫描，`schedule/routine/home/作息/居所` 命中 0），模型只能从「地点变化」这类一次性
信号猜「这个角色平时白天在忙什么」，于是同一个角色在不同轮次里作息自相矛盾。

**为什么不走 `knowledgeFacts`**：普通闲聊只注入 1 条（`prompts.py` 的
`_MAX_KNOWLEDGE_FACTS` 门控），而索菲亚现成的那条
（`sophia-vineyard-work`）已经占着这个名额；作息是 2–4 条成组出现的规律，
挤进同一条 summary 要么丢掉时段结构，要么把当轮唯一名额撑爆。所以这里走
**独立的 `daily_routine` 卡**，并自带「通常 / 多数日子」的措辞门控。

**降级方向**：没有 `dailyRoutine` 的角色、字段形态不认识的条目、非 SVE 来源下的
索菲亚 —— 一律**不发卡**，prompt 与改动前逐字节相同，而不是发一张空卡或半张卡。
"""

from __future__ import annotations

import json
from typing import Any

from stardew_ai_bridge.app import _build_context
from stardew_ai_bridge.prompts import PromptBuilder


SOPHIA = "Sophia"
SVE_MODS = ["SVE", "FlashShifter.SVECode", "FlashShifter.StardewValleyExpandedCP"]
MESSAGE = "你好呀，今天过得怎么样？"


def _payload(
    *,
    npc_id: str = SOPHIA,
    source_mods: list[str] | None = None,
    message: str = MESSAGE,
    compact: bool = True,
    extra_state: dict[str, object] | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {
        "npcId": npc_id,
        "displayName": npc_id,
        "season": "spring",
        "date": "25",
        "weather": "clear",
        "location": "Forest",
        "time": 900,
        "friendship": 1500,
        "friendshipHearts": 6,
        "relationship": "friend",
    }
    if extra_state:
        state.update(extra_state)
    return {
        "npcId": npc_id,
        "message": message,
        "intent": "chat",
        "provider": "fake",
        "compactPrompt": compact,
        "sourceMods": list(source_mods if source_mods is not None else SVE_MODS),
        "recentFacts": [],
        "history": [],
        "gameState": state,
    }


def _messages(**kwargs: Any) -> list[dict[str, str]]:
    _, prompt = _build_context(_payload(**kwargs))
    return prompt


def _card(messages: list[dict[str, str]], name: str) -> dict[str, Any] | None:
    entry = next((item for item in messages if item.get("name") == name), None)
    return json.loads(entry["content"]) if entry else None


def _daily_routine(**kwargs: Any) -> dict[str, Any] | None:
    return _card(_messages(**kwargs), "daily_routine")


# --- 真实 persona 数据确实走到了 prompt ---------------------------------------


def test_sophia_routine_reaches_the_prompt_with_period_labels() -> None:
    """四条作息按「早上 / 白天 / 傍晚 / 夜里」的顺序进 prompt，且逐字来自 persona。

    2026-09-21 的两处补写不是装饰（依据 `.tmp/diagnosis-f9-sophia-20260921.md`）：

    - **白天条补「也常去镇上送酒、买东西，顺路和谁聊上几句」**：落点池第 3 类
      「小镇日常」此前在 prompt 里**零素材**，四个类别里它只有一个名字、
      没有任何可落地的内容 —— 补的是这一类的唯一依据。
    - **傍晚条补「新酿出来时会分装几瓶，留一瓶给朋友尝」**：给「酒」补一个
      **成果形态**。她此前在 prompt 里的酒全是劳作（葡萄园、酒窖、贴标签），
      而「分享作品」这个功能位只有画能兑现。

    本条刻意用**逐字**断言：作息文案属于会被模型照抄的事实卡，改动必须显式
    落到测试上；改成"从 JSON 读回来再比"就成了同义反复，抓不到任何回归。

    2026-09-24（SVE 查证）：白天条的「画架前／画起来」与傍晚条的「洗干净画笔」
    换成「手工房／缝起东西来」与「收起布料和线」。依据是她自己的原话与 SVE
    非对白资源 —— 她的创作面是**角色扮演 + 缝纫**（`CharacterDialogue.136/144/166`、
    `Marriage.004`、`10hearts.01`），家里那句是「很多布料和油漆」（`SophiaHouse.18`，
    油漆是手工材料），**没有任何画具／画作证据**。酒那条「留一瓶给朋友尝」不动。
    """

    card = _daily_routine()

    assert card is not None
    assert card["通常作息"] == [
        "早上：多数日子的早上都在忙手上的活：看藤、剪枝、整理布料，或者把工具搬来搬去。",
        "白天：白天通常也在葡萄园和手工房之间来回；有时去镇上送东西、买点布和线，"
        "顺路和谁说上几句。",
        "傍晚：傍晚一般开始收尾：把工具和布料收好，慢慢回屋；"
        "天气好的时候会绕去山上走一小段。",
        "夜里：夜里大多待在家里，不太出门。会窝在毯子里看电视，或者就看着窗外发一会儿呆。",
    ]


def test_sophia_routine_survives_the_compact_online_path() -> None:
    """线上游戏端走 compact 路径，作息不能只在评测路径可见。"""

    compact_card = _daily_routine(compact=True)
    full_card = _daily_routine(compact=False)

    assert compact_card is not None
    assert compact_card == full_card


def test_every_routine_line_carries_hedging_language() -> None:
    """措辞门控：每条都必须自带「通常 / 多数 / 一般 / 大多」这类模糊量词。

    这是 L3 与今日实况之间的缓冲：作息是静态知识，今天可能完全不是这样。
    """

    card = _daily_routine()
    assert card is not None

    hedges = ("通常", "多数", "一般", "大多", "平时", "往往")
    for line in card["通常作息"]:
        assert any(hedge in line for hedge in hedges), line


def test_instruction_declares_scene_card_authority() -> None:
    card = _daily_routine()
    assert card is not None

    instruction = card["instruction"]
    assert "通常" in instruction
    assert "不是今天的实际行程" in instruction
    assert "场景卡" in instruction
    assert "不要拿它当此刻的行踪" in instruction


def test_routine_does_not_take_the_single_knowledge_fact_slot() -> None:
    """回归护栏：作息**不得**挤占普通闲聊那条唯一的 knowledgeFact 名额。

    这一条刻意绕开 `PersonaStore` / profile index：直接给上下文两条知识事实，
    断言普通闲聊仍然只渲染 1 条（`_MAX_KNOWLEDGE_FACTS` 门控没被这次改动放宽），
    同时作息卡照样出现——即作息走的是**并行通道**，不是抢名额。
    """

    messages = PromptBuilder().build(
        {
            "npcIdentity": {
                "npcId": SOPHIA,
                "dailyRoutine": ["早上：多数日子的早上都在葡萄园里忙。"],
            },
            "knowledgeFacts": [
                {
                    "factId": "sophia-vineyard-work",
                    "summary": "生活与葡萄园、酿造和绘画创作有关。",
                    "knowledgeScope": "canon_confirmed",
                },
                {
                    "factId": "sophia-second-fact",
                    "summary": "另一条本该被门控挡掉的事实。",
                    "knowledgeScope": "canon_confirmed",
                },
            ],
            "gameState": {},
            "recentFacts": [],
            "history": [],
            "modSources": SVE_MODS,
        },
        MESSAGE,
        compact=True,
    )

    facts = _card(messages, "knowledge_facts")
    routine = _card(messages, "daily_routine")

    assert facts is not None
    assert len(facts["knowledgeFacts"]) == 1
    assert "葡萄园" in json.dumps(facts["knowledgeFacts"], ensure_ascii=False)
    assert routine is not None
    assert routine["通常作息"] == ["早上：多数日子的早上都在葡萄园里忙。"]


# --- 降级路径 ---------------------------------------------------------------


def test_character_without_routine_gets_no_card() -> None:
    """Harvey 在四份 persona 文件里都没有作息：不许出现空卡。"""

    assert _daily_routine(npc_id="Harvey", source_mods=[]) is None


def test_routine_requires_the_matching_persona_source() -> None:
    """索菲亚的作息来自 SVE overlay：没装 SVE 时不该凭空出现。"""

    assert _daily_routine(source_mods=[]) is None


def test_sophia_vanilla_only_has_no_sve_routine() -> None:
    """只报 vanilla 来源时，SVE 那份 overlay（含作息）不应用。"""

    assert _daily_routine(source_mods=["vanilla"]) is None


def test_malformed_routine_shapes_never_emit_a_partial_card() -> None:
    """形态坏掉的作息：**不发卡**，而不是发一张只剩半截的卡。

    这里是真实数据损坏时的失效方向：宁可退回「这个角色没有作息」，
    也不要让模型看到 `{'morning': '…'}` 这种 repr 或者一张空壳卡。
    """

    for broken in (
        "早上在葡萄园",
        {"morning": "在葡萄园"},
        [],
        [{"period": "morning"}],
        [{"period": "morning", "summary": "   "}],
        [None, 42, {"period": "noon"}],
    ):
        messages = PromptBuilder().build(
            {
                "npcIdentity": {"npcId": SOPHIA, "dailyRoutine": broken},
                "gameState": {},
                "recentFacts": [],
                "history": [],
                "modSources": SVE_MODS,
            },
            MESSAGE,
            compact=True,
        )

        assert "daily_routine" not in [
            item.get("name") for item in messages
        ], broken


def test_routine_entry_cap_and_shape_tolerance() -> None:
    """压缩函数本身：只认两种形态、最多四条、认不出 period 时只留 summary。"""

    from stardew_ai_bridge.prompts import _compact_daily_routine

    assert _compact_daily_routine(None) == []
    assert _compact_daily_routine("早上在葡萄园") == []
    assert _compact_daily_routine([None, 3, {}]) == []
    assert _compact_daily_routine([{"period": "noon", "summary": "中午在家"}]) == [
        "中午在家"
    ]
    assert _compact_daily_routine(["一句纯文本"]) == ["一句纯文本"]
    assert _compact_daily_routine(
        [{"period": "morning", "summary": f"第{index}条"} for index in range(9)]
    ) == [
        "早上：第0条",
        "早上：第1条",
        "早上：第2条",
        "早上：第3条",
    ]


def test_prompt_is_unchanged_for_characters_without_routine() -> None:
    """没有作息的角色：新卡完全不出现，避免给全部 34 个角色抬预算。"""

    names = [item.get("name") for item in _messages(npc_id="Emily", source_mods=[])]

    assert "daily_routine" not in names
