"""婚姻的另一端必须真的到达 Prompt，而不只是存在于 view 里。

2026-10-04：这条修复一路撞到**三个**静默吞字段点，每个都不报错：

1. `StoryStateStore` 造 view 时压根没写 `CounterpartNpcId`（已补）；
2. `project_relationship_context` 的字段元组是一份白名单，新字段不在里面就被丢；
3. `prompts._compact_relationship_world` 还有**第二份**白名单，同样会丢。

第 2、3 点各自的两侧单测都是绿的 —— 只有一条走完
`payload → ContextBuilder → PromptBuilder` 真实组装链的用例才问得出
「请求里的数据有没有走到 Prompt」。这与 `knownCharacters` / `recentFacts` /
`latentKnowledge` 是同一个失效模式，见 `docs/STATE.md` §四。
"""

from __future__ import annotations

import json

from stardew_ai_bridge.models import RelationshipWorldContext
from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder


def _messages(payload: dict[str, object]) -> list[dict[str, object]]:
    """走生产路径：payload → ContextBuilder → PromptBuilder。

    ⚠ 但 `relationshipWorld` 必须先过 `RelationshipWorldContext` 校验 ——
    折叠 `fromNpcId/toNpcId → npcId` 的 `_fold_relationship_edges` 挂在它的
    `model_validator(mode="before")` 上。直接喂 ContextBuilder 会拿到
    `knowledge: []`，测出来的是与生产无关的形状（现有用例正是这么写的）。
    """
    if isinstance(payload.get("relationshipWorld"), dict):
        payload = dict(payload)
        payload["relationshipWorld"] = RelationshipWorldContext.model_validate(
            payload["relationshipWorld"]
        )
    context = ContextBuilder().build(payload)
    return PromptBuilder().build(context, str(payload.get("message", "")))


def _relationship_card(messages: list[dict[str, object]]) -> dict[str, object]:
    for message in messages:
        if message.get("name") == "relationship_world":
            return json.loads(str(message["content"]))
    raise AssertionError("relationship_world 卡没有生成")


def _world() -> dict[str, object]:
    """C# 真实发出来的形状：`objectiveRelationships` 是**有向边**。

    ⚠ 这里刻意用 `fromNpcId` / `toNpcId`，**不是** `npcId`。
    2026-10-04 查明：生产 payload 走 `models._fold_relationship_edges` 折叠成
    `npcId`，而折叠时会把两端字段 pop 掉。用 `npcId` 手写 fixture 会绕过那一层，
    于是测试全绿、线上 `knowledge` 恒空 —— 现有用例正是这么写的。
    """
    return {
        "objectiveRelationships": [
            {
                "fromNpcId": "player",
                "toNpcId": "Olivia",
                "relationType": "married",
                "publicEventId": "wedding:olivia",
                "publicOn": "Spring 12",
            },
        ],
        "views": [],
    }


def _payload(viewer: str) -> dict[str, object]:
    return {
        "npcId": viewer,
        "message": "今天过得怎么样？",
        "intent": "chat",
        "compactPrompt": True,
        "channel": "face_to_face",
        "gameState": {"friendshipHearts": 8, "relationship": "friend"},
        "relationshipWorld": _world(),
    }


def test_counterpart_reaches_the_prompt_for_the_spouses_family() -> None:
    """Victor（Olivia 的儿子）必须拿到「Olivia 嫁给了玩家」。"""

    card = _relationship_card(_messages(_payload("Victor")))
    knowledge = card["relationshipWorld"]["knowledge"]
    olivia = next(item for item in knowledge if item["subjectNpcId"] == "Olivia")

    assert olivia["counterpartNpcId"] == "player", (
        "婚姻的另一端在到达 Prompt 前被丢了 —— 这正是那三处白名单的要害"
    )


def test_counterpart_reaches_the_prompt_for_every_viewer() -> None:
    """两端一致：viewer 是配偶本人还是配偶的亲属，看到的事实相同。"""

    for viewer in ("Olivia", "Victor", "Sophia"):
        card = _relationship_card(_messages(_payload(viewer)))
        knowledge = card["relationshipWorld"]["knowledge"]
        olivia = next(item for item in knowledge if item["subjectNpcId"] == "Olivia")
        assert olivia["counterpartNpcId"] == "player", viewer


def test_marriage_instruction_explains_the_counterpart_field() -> None:
    """卡里必须说明这个字段是什么，否则模型只会看到一个孤立的 id。"""

    card = _relationship_card(_messages(_payload("Victor")))
    instruction = str(card["instruction"])

    assert "counterpartNpcId" in instruction
    assert "player" in instruction