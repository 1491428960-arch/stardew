"""「这条记忆该不该进 prompt」的单一实现（语义层审计 P1 第 27 条）。

## 背景

同一个问题——「哪条记忆值得进 prompt」——此前有两条互不相干的通道：

- `profile_index.knowledge_facts`：按 `knowledgeScope` 白名单 + `confidence`
  （low 直接丢）+ `requiredEventId` 事件门控筛选；
- `RecentMemoryFacts`（SMAPI 侧）→ 请求里的 `recentFacts` → Bridge：**只按时间
  取最近 6 条**，`Confidence` / `Importance` / `KnownBy` / `Status` 这些字段
  写进了存档，却没有任何选择逻辑读它们。

Bridge 侧此前还额外做了一件事：把整份 `recentFacts` 原样塞进
`game_state` 卡片，连长度上限与重复都没有处理。

## 本次建立的语义

Bridge 侧只保留一处准入实现 `prompts.select_memory_facts`：

- **结构化记忆记录**（`content` / `confidence` / `importance` / `status` /
  `knowledgeScope` / `knownBy`）按与 `knowledge_facts` 同一套口径筛选：
  置信度低于 `MEMORY_FACT_CONFIDENCE_FLOOR` 丢弃、非 `active` 状态丢弃、
  `knownBy` 不含当前 NPC 或玩家时丢弃、同一内容只保留一次；
  排序按重要性、再按置信度——「重要的事实」不再被「最近但琐碎的事实」挤掉。
- **纯文本行**（当前 SMAPI 实际发送的形态，`IReadOnlyList<string>`）：
  做空白归一、空值丢弃与完全重复去重，不假装能判定它没有携带的元数据。
- 超长内容按 `MEMORY_FACT_TEXT_LIMIT` 丢弃而不是截成半句。

两处调用（`_build_context_core` 与 `_safe_context`）都走这同一个函数。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.prompts import (
    MEMORY_FACT_CONFIDENCE_FLOOR,
    MEMORY_FACT_TEXT_LIMIT,
    select_memory_facts,
)


def _record(content: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "content": content,
        "confidence": 0.9,
        "importance": 1,
        "status": "active",
        "knownBy": ["Shane", "player"],
        "knowledgeScope": "participants",
    }
    base.update(overrides)
    return base


# --- 结构化记录：与 knowledge_facts 同一套口径 ------------------------------


def test_a_confident_active_record_is_admitted() -> None:
    assert select_memory_facts([_record("玩家上周送过一束花")], npc_id="Shane") == [
        "玩家上周送过一束花"
    ]


def test_low_confidence_records_are_dropped() -> None:
    # 与 `knowledge_facts` 的 `confidence == "low"` 门控对齐：数值化后低于下限即丢。
    facts = [
        _record("也许是玩家提过的事", confidence=MEMORY_FACT_CONFIDENCE_FLOOR - 0.01),
        _record("玩家确实提过的事", confidence=MEMORY_FACT_CONFIDENCE_FLOOR),
    ]

    assert select_memory_facts(facts, npc_id="Shane") == ["玩家确实提过的事"]


def test_records_without_a_confidence_are_kept() -> None:
    # 缺字段是「未标注」，不是「低置信」；不能因为旧存档没有这个字段就清空记忆。
    assert select_memory_facts([_record("旧存档的记忆", confidence=None)], npc_id="Shane") == [
        "旧存档的记忆"
    ]


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        # 索引侧 `knowledgeFacts` 用的是 high/medium/low 字面量；
        # 同一个概念的另一种写法必须换算到同一把尺子上（high≈0.9、medium≈0.7、
        # low≈0.3），否则「统一准入」会按数据形态给出不同结论。
        ("high", True),
        ("  MEDIUM  ", True),
        ("low", False),
        (0.9, True),
        ("0.9", True),
        ("没听说过", True),  # 读不出数值 = 未标注，不是低置信
    ],
)
def test_confidence_accepts_both_spellings(confidence: object, expected: bool) -> None:
    picked = select_memory_facts(
        [_record("一条带置信度的记忆", confidence=confidence)], npc_id="Shane"
    )

    assert (picked == ["一条带置信度的记忆"]) is expected


@pytest.mark.parametrize("status", ["Corrected", "superseded", "Forgotten", "  forgotten  "])
def test_inactive_records_are_dropped(status: str) -> None:
    # `MemoryStatus` 的三种非 Active 取值以前完全没有被读过：被更正的、
    # 被取代的、被遗忘的记忆照样会进 prompt。
    assert select_memory_facts([_record("已经被更正的说法", status=status)], npc_id="Shane") == []


@pytest.mark.parametrize("status", ["active", "Active", None, ""])
def test_active_or_unlabelled_records_are_kept(status: object) -> None:
    assert select_memory_facts([_record("仍然有效的记忆", status=status)], npc_id="Shane") == [
        "仍然有效的记忆"
    ]


def test_records_not_known_by_this_npc_are_dropped() -> None:
    facts = [
        _record("只写给 Emily 看的事", knownBy=["Emily"]),
        _record("Shane 知道的事", knownBy=["Shane"]),
    ]

    assert select_memory_facts(facts, npc_id="Shane") == ["Shane 知道的事"]


def test_records_known_only_by_the_player_are_dropped() -> None:
    # 记忆挂在谁的 prompt 上，判断标准就是**谁记得它**：玩家知情不是充分条件。
    assert select_memory_facts(
        [_record("玩家知道但 Shane 不知道", knownBy=["player"])], npc_id="Shane"
    ) == []


def test_records_known_by_the_player_and_this_npc_are_kept() -> None:
    # 玩家告诉 NPC 的事会同时写进双方的 knownBy；这一条必须留下。
    assert select_memory_facts(
        [_record("玩家告诉 Shane 的事", knownBy=["player", "Shane"])], npc_id="Shane"
    ) == ["玩家告诉 Shane 的事"]


def test_records_without_known_by_are_kept() -> None:
    assert select_memory_facts([_record("没标注知情者", knownBy=None)], npc_id="Shane") == [
        "没标注知情者"
    ]


def test_private_scope_records_are_dropped_for_group_prompts() -> None:
    facts = [
        _record("只有自己知道的秘密", knowledgeScope="private"),
        _record("玩家也在场的事", knowledgeScope="participants"),
    ]

    assert select_memory_facts(facts, npc_id="Shane") == ["玩家也在场的事"]


def test_blank_contents_are_dropped() -> None:
    assert select_memory_facts([_record("   "), _record("")], npc_id="Shane") == []


def test_duplicate_contents_collapse_to_one_line() -> None:
    facts = [_record("同一件事"), _record("同一件事", importance=2)]

    assert select_memory_facts(facts, npc_id="Shane") == ["同一件事"]


def test_higher_importance_comes_first() -> None:
    facts = [
        _record("最近但琐碎", importance=1, confidence=0.99),
        _record("很久以前但重要", importance=3, confidence=0.7),
    ]

    assert select_memory_facts(facts, npc_id="Shane") == ["很久以前但重要", "最近但琐碎"]


def test_confidence_breaks_a_tie_in_importance() -> None:
    facts = [
        _record("不太确定的同级事实", importance=2, confidence=0.7),
        _record("确定无疑的同级事实", importance=2, confidence=0.95),
    ]

    assert select_memory_facts(facts, npc_id="Shane") == [
        "确定无疑的同级事实",
        "不太确定的同级事实",
    ]


def test_result_is_plain_text_not_the_record_object() -> None:
    # 返回的是进 prompt 的文本行；把整条记录塞给调用方会让 live 对象泄漏进上下文。
    picked = select_memory_facts([_record("一句话")], npc_id="Shane")

    assert picked == ["一句话"]
    assert all(isinstance(item, str) for item in picked)


def test_the_index_side_summary_field_is_also_accepted() -> None:
    # SMAPI 的 `MemoryRecord` 用 `content`，索引侧 `knowledgeFacts` 用 `summary`——
    # 同一条事实的两种存放形态，准入实现必须都能读，否则「统一」只统一了一半。
    fact = {
        "factId": "wizard-tower-residence",
        "npcId": "Wizard",
        "summary": "居住并工作的地点是法师塔。",
        "knowledgeScope": "canon_confirmed",
        "confidence": "high",
    }

    assert select_memory_facts([fact], npc_id="Wizard") == ["居住并工作的地点是法师塔。"]


# --- 纯文本行：当前 SMAPI 实际发送的形态 ------------------------------------


def test_plain_text_lines_stay_supported() -> None:
    assert select_memory_facts(["记忆（春3）：玩家来过法师塔"], npc_id="Shane") == [
        "记忆（春3）：玩家来过法师塔"
    ]


def test_plain_text_lines_are_stripped_and_deduplicated() -> None:
    assert select_memory_facts(["  同一句话  ", "同一句话", "另一句话"], npc_id="Shane") == [
        "同一句话",
        "另一句话",
    ]


def test_blank_plain_text_lines_are_dropped() -> None:
    assert select_memory_facts(["", "   ", None, 42], npc_id="Shane") == []


def test_plain_text_keeps_its_input_order() -> None:
    # 文本行没有时间以外的排序依据，不能凭空重排——那会让 prompt 每次都不一样。
    facts = ["第一句", "第二句", "第三句"]

    assert select_memory_facts(facts, npc_id="Shane") == facts


def test_over_long_plain_text_is_dropped_rather_than_cut_in_half() -> None:
    too_long = "很长的记忆" * 200

    assert len(too_long) > MEMORY_FACT_TEXT_LIMIT
    assert select_memory_facts([too_long, "正常长度"], npc_id="Shane") == ["正常长度"]


def test_mixed_shapes_go_through_one_entry_point() -> None:
    # 结构化记录与纯文本行共用同一个入口；不是「两条通道各一套判定」。
    assert select_memory_facts(
        [_record("结构化记录"), "纯文本记忆"], npc_id="Shane"
    ) == ["结构化记录", "纯文本记忆"]
