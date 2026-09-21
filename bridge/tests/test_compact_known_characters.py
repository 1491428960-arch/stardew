"""紧凑路径的人物关系卡（`knownCharacters`）。

背景（2026-09-21 对话质量体检）：`PromptBuilder.build` 的 `if compact:` 分支把
`knownCharacters` 整块清空，于是索引里 **41 条已确认人物关系**（覆盖 23 个
可对话 NPC，每个 1–3 条）在游戏端**一条都进不了 prompt** —— 数据在索引里、
`known_characters` 卡的渲染代码也在，只有那一行把资料扔了。
与 `recentFacts` 被 `if not runtime_compact:` 整块挡住是同一形态。

修复口径：紧凑路径裁**字段**而不是**条数**。单 NPC 的候选本来就只有 1–3 条
（`ProfileIndexStore.known_characters` 的 `limit=8` 在单角色上根本不触顶），
所以「只给前 N 条」省不出 token；能省的是每条里模型读不到的构建侧字段
（`npcId` / `relationId` / `sourceMod` / `sourceRefs` / `knowledgeScope` /
`confidence`）。保留 `knownNpcId` / `relation` / `summary`。

本文件只钉 PromptBuilder 层的行为；访问器层的过滤与门控见
`test_known_characters_edges.py`，ContextBuilder 的投影见 `test_profile_context.py`。
"""

from __future__ import annotations

import copy
import json

from stardew_ai_bridge.prompts import PromptBuilder

MESSAGE = "你的孩子们还好吗？"

# 贴近索引里的真实条目形态（`vanilla-sve-rasmodia-profile-index-zh-CN`）。
RELATIONS = [
    {
        "relationId": "Jodi:knows:Kent:0",
        "npcId": "Jodi",
        "knownNpcId": "Kent",
        "relation": "丈夫",
        "summary": "Kent 是她的丈夫。",
        "sourceMod": "vanilla",
        "knowledgeScope": "canon_confirmed",
        "confidence": "high",
        "sourceRefs": ["Characters/Dialogue/Jodi"],
    },
    {
        "relationId": "Jodi:knows:Sam:1",
        "npcId": "Jodi",
        "knownNpcId": "Sam",
        "relation": "儿子",
        "summary": "Sam 是她的儿子。",
        "sourceMod": "vanilla",
        "knowledgeScope": "canon_confirmed",
        "confidence": "high",
        "sourceRefs": ["Characters/Dialogue/Jodi"],
    },
    {
        "relationId": "Jodi:knows:Vincent:2",
        "npcId": "Jodi",
        "knownNpcId": "Vincent",
        "relation": "儿子",
        "summary": "Vincent 是她的儿子。",
        "sourceMod": "vanilla",
        "knowledgeScope": "canon_confirmed",
        "confidence": "high",
        "sourceRefs": ["Characters/Dialogue/Jodi"],
    },
]

# 构建侧字段：模型读不到，紧凑路径必须去掉。
BUILD_SIDE_FIELDS = (
    "relationId",
    "npcId",
    "sourceMod",
    "sourceRefs",
    "knowledgeScope",
    "confidence",
    "requiredEventId",
)

# `Lewis→Marnie` 那条的写法：summary 里**没有**关系词，所以 `relation` 必须留下。
SUMMARY_WITHOUT_RELATION = [
    {
        "npcId": "Lewis",
        "knownNpcId": "Marnie",
        "relation": "熟人",
        "summary": "与 Marnie 的关系属于已确认的个人信息边界。",
        "sourceMod": "vanilla",
        "knowledgeScope": "canon_confirmed",
        "confidence": "medium",
    }
]


def _context(relations: object = RELATIONS) -> dict[str, object]:
    context: dict[str, object] = {
        "npcIdentity": {"npcId": "Jodi", "displayName": "Jodi"},
        "modSources": ["vanilla"],
        "gameState": {
            "season": "spring",
            "date": "25",
            "weather": "clear",
            "time": 1200,
            "location": "SeedShop",
            "friendship": 1500,
        },
        "recentFacts": [],
        "history": [],
    }
    if relations is not None:
        context["knownCharacters"] = copy.deepcopy(relations)
    return context


def _card(prompt: list[dict[str, str]]) -> dict[str, str] | None:
    return next(
        (message for message in prompt if message.get("name") == "known_characters"),
        None,
    )


def _payload(card: dict[str, str]) -> dict[str, object]:
    return json.loads(card["content"])


def _tokens(prompt: list[dict[str, str]]) -> int:
    """与项目其它 token 估算同一口径：CJK 记 1，其余记 0.25。"""

    total = 0.0
    for message in prompt:
        for char in message.get("content", ""):
            total += 1.0 if ord(char) > 0x2E80 else 0.25
    return int(round(total))


def test_compact_prompt_renders_known_characters_card() -> None:
    """核心回归：游戏端（compact=True）必须拿到这张卡，且三条一条不少。"""

    prompt = PromptBuilder().build(_context(), MESSAGE, compact=True)

    card = _card(prompt)
    assert card is not None
    entries = _payload(card)["knownCharacters"]
    assert [item["knownNpcId"] for item in entries] == ["Kent", "Sam", "Vincent"]


def test_compact_card_keeps_only_model_facing_fields() -> None:
    prompt = PromptBuilder().build(_context(), MESSAGE, compact=True)

    entries = _payload(_card(prompt))["knownCharacters"]  # type: ignore[arg-type]

    assert all(set(item) == {"knownNpcId", "relation", "summary"} for item in entries)


def test_compact_card_drops_build_side_fields() -> None:
    """审计与门控字段不该出现在送给模型的卡里。

    只看这张卡本身：`npcId` 等词当然还出现在 `npcIdentity` / `game_state`
    等别的卡上，那不是本卡的问题。
    """

    prompt = PromptBuilder().build(_context(), MESSAGE, compact=True)
    card_content = _card(prompt)["content"]  # type: ignore[index]
    entries = _payload(_card(prompt))["knownCharacters"]  # type: ignore[arg-type]

    for field in BUILD_SIDE_FIELDS:
        assert all(field not in item for item in entries)
    assert "Characters/Dialogue/Jodi" not in card_content
    assert "canon_confirmed" not in card_content


def test_full_prompt_still_carries_build_side_fields() -> None:
    """完整路径（离线评测 / 脚本）不受本次裁剪影响，字段照旧。"""

    prompt = PromptBuilder().build(_context(), MESSAGE, compact=False)

    entries = _payload(_card(prompt))["knownCharacters"]  # type: ignore[arg-type]
    assert entries[0]["relationId"] == "Jodi:knows:Kent:0"
    assert entries[0]["sourceRefs"] == ["Characters/Dialogue/Jodi"]
    assert entries[0]["knowledgeScope"] == "canon_confirmed"


def test_compact_card_keeps_relation_when_summary_lacks_it() -> None:
    """`summary` 不是总能替代 `relation`——关系词必须一起保留。"""

    prompt = PromptBuilder().build(
        _context(SUMMARY_WITHOUT_RELATION), MESSAGE, compact=True
    )

    entries = _payload(_card(prompt))["knownCharacters"]  # type: ignore[arg-type]
    assert entries[0]["relation"] == "熟人"
    assert entries[0]["summary"] == "与 Marnie 的关系属于已确认的个人信息边界。"


def test_no_known_characters_means_no_card() -> None:
    """没有资料的 NPC 不该凭空多出一张卡（线上 137 个角色里 114 个如此）。"""

    for relations in (None, []):
        prompt = PromptBuilder().build(_context(relations), MESSAGE, compact=True)
        assert _card(prompt) is None


def test_compact_card_keeps_its_instruction() -> None:
    prompt = PromptBuilder().build(_context(), MESSAGE, compact=True)

    instruction = _payload(_card(prompt))["instruction"]  # type: ignore[arg-type]
    assert "不要替这个 NPC 猜测其他人的秘密、想法或未确认决定" in instruction


def test_compact_card_stays_within_token_budget() -> None:
    """成本守卫：三条关系 + instruction 实测 137 tokens，留约 24% 余量。

    这条不是「越省越好」的指标，而是防止后续往卡里悄悄加字段——
    卡片增长必须是一次显式决定，不能靠改一行白名单顺带带上。
    """

    prompt = PromptBuilder().build(_context(), MESSAGE, compact=True)

    assert _tokens([_card(prompt)]) <= 170  # type: ignore[list-item]


def test_malformed_entries_are_skipped_without_breaking_the_card() -> None:
    """坏条目不该让整张卡消失，也不该让这一轮对话失败。"""

    prompt = PromptBuilder().build(
        _context(
            [
                "not-a-mapping",
                {"knownNpcId": "Kent"},  # 缺 summary，被渲染白名单挡掉
                RELATIONS[1],
            ]
        ),
        MESSAGE,
        compact=True,
    )

    entries = _payload(_card(prompt))["knownCharacters"]  # type: ignore[arg-type]
    assert [item["knownNpcId"] for item in entries] == ["Sam"]


def test_story_events_stay_hidden_in_compact() -> None:
    """`storyEvents` 仍**有意**保持清空——不要顺手一起放开。

    它与 `knownCharacters` 是同一处代码，但性质不同：索引里 `storyEvents`
    就是 0 条（根因是 SVE 的 55 个 xnb 未解包，不是在这里丢的），
    放开也拿不到内容。等数据侧补齐后再按同款策略放开；届时需单独评估成本，
    因为单条 `summary` 上限 240 字符，比人物关系这条通道长得多。
    """

    context = _context()
    context["storyEvents"] = [
        {
            "eventId": "sve:event-1",
            "sourceMod": "SVE",
            "participants": ["Jodi"],
            "summary": "玩家参加了葡萄园活动。",
            "canonical": True,
        }
    ]

    compact = PromptBuilder().build(copy.deepcopy(context), MESSAGE, compact=True)
    full = PromptBuilder().build(copy.deepcopy(context), MESSAGE, compact=False)

    assert not any(m.get("name") == "story_facts" for m in compact)
    assert any(m.get("name") == "story_facts" for m in full)
