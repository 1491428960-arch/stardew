"""隐性知识卡片（latent_knowledge）。

背景 —— 用户口径（2026-10-04）：

    「我想的『有机连结』大概就是有一个感觉上是连续的 NPC 的人格，他不会因为
     在 F8 还是 F9 中出现导致不像同一个人。」

诊断出的断裂点：晨间消息已经走 `AppendHistory` 进了私聊发送窗口
（`BridgeClient.RememberMorningMessage`），所以晨间 → F8 是通的；
但群聊发言既不写私聊历史，也不进长期记忆——NPC 之间说了什么，一条都不记。

用户对「隐性知识库」的定义（原话）：

    「群聊记忆中别的 NPC 说了什么能不能作为一个隐性的知识库这样的形式，
     我不主动提到就不唤醒」

所以本卡片承载的是**别的 NPC 在群聊里说的话**，语义是：

    - 她**知道**这件事（在场，听见了）
    - 但**不主动提起**（不是她自己说的，不该抢别人的话头）
    - 玩家问起或被相关话题带出来时，**可以自然地提到**

为什么必须是独立卡片而不是塞进 `recent_memory`
------------------------------------------------

项目实测过「取最宽」规则（`test_prompts.py`）：同一个 prompt 里存在同类约束的
多个实例时，模型跟**最松**的那个。若把「不主动提」混进 `recent_memory` 那张
泛记忆卡，那条指令会被同卡里「把记忆自然用起来」的指令稀释掉——等于没有约束。

独立成卡才能让这条约束有独立的话语权。
"""

from __future__ import annotations

from stardew_ai_bridge.prompts import PromptBuilder


def _context(**overrides):
    context = {
        "npcIdentity": {"npcId": "Sophia", "displayName": "索菲娅"},
        "gameState": {"date": "春 28", "time": "0900", "location": "Farm"},
        "history": [],
        "recentFacts": [],
    }
    context.update(overrides)
    return context


def _names(messages):
    return [message.get("name") for message in messages]


def test_latent_knowledge_card_absent_when_no_latent_facts() -> None:
    """没有隐性知识时不该出现这张卡——零成本的默认形态。"""

    messages = PromptBuilder().build(_context(), "早上好")

    assert "latent_knowledge" not in _names(messages)


def test_plain_strings_render_a_card() -> None:
    """**游戏端发来的就是纯字符串**（2026-10-04 实机口径）。

    C# 侧 `StoryStateStore.LatentKnowledge` 返回 `IReadOnlyList<string>`，
    每一条**已经**是拼好的「听说 Abigail 说：……」；说话人标记由
    `GroupUtteranceRules.memorySpeakerLabel` 在写入时就拼进文本。
    请求模型也是 `list[str]`。

    本用例钉住「纯字符串能成卡」。之前的实现只认结构化 `Mapping`，
    而字符串被 `if not isinstance(item, Mapping): continue` **整条静默跳过**
    —— 结果是线上永远一张空卡、且不报任何错。这正是本项目反复出现的
    「资料在、代码把它扔了」形态。
    """
    messages = PromptBuilder().build(
        _context(latentKnowledge=["听说 Abigail 说：我倒是想练练剑。"]),
        "早上好",
    )

    assert "latent_knowledge" in _names(messages)

    card = next(m for m in messages if m.get("name") == "latent_knowledge")
    assert "练练剑" in str(card.get("content"))


def test_strings_and_records_both_work() -> None:
    """两种形态都要支持，不能只留一种。

    字符串是**游戏端**的口径；结构化记录是 **Mod 内部 / 离线评测**的口径
    （`MemoryRecord` 直出）。只支持一种会让另一条路静默失效。
    """
    messages = PromptBuilder().build(
        _context(
            latentKnowledge=[
                "听说 Abigail 说：我倒是想练练剑。",
                {
                    "ownerNpcId": "Sophia",
                    "content": "听说 Sebastian 说：今晚有雨。",
                    "status": "active",
                },
            ]
        ),
        "早上好",
    )

    card = next(m for m in messages if m.get("name") == "latent_knowledge")
    content = str(card.get("content"))

    assert "练练剑" in content
    assert "今晚有雨" in content


def test_latent_knowledge_card_present_with_facts() -> None:
    """有隐性知识时必须成卡，且带约束指令。"""

    messages = PromptBuilder().build(
        _context(
            latentKnowledge=[
                {
                    "ownerNpcId": "Sophia",
                    "content": "阿比盖尔在群里说她最近在练剑",
                    "participants": ["Sophia", "Abigail"],
                    "gameDate": "春 27",
                }
            ]
        ),
        "早上好",
    )
    names = _names(messages)

    assert "latent_knowledge" in names


def test_latent_knowledge_card_sits_after_recent_memory_and_before_relationship_world() -> None:
    """位置：属于「背景资料」区，不是开场素材位。

    `recent_memory` 之后 —— 与它会话记忆的定位一致；
    `relationship_world` 之前 —— 关系卡是更强的行为约束，该压在后头。
    """

    messages = PromptBuilder().build(
        _context(
            recentFacts=["记忆（春 27）：玩家送过我一条项链"],
            latentKnowledge=[
                {
                    "ownerNpcId": "Sophia",
                    "content": "阿比盖尔在群里说她最近在练剑",
                    "participants": ["Sophia", "Abigail"],
                }
            ],
            relationshipWorld={
                "coSpouses": [{"npcId": "Abigail", "acceptance": "accepted"}],
            },
        ),
        "早上好",
    )
    names = _names(messages)

    assert "latent_knowledge" in names
    if "recent_memory" in names:
        assert names.index("recent_memory") < names.index("latent_knowledge")
    if "relationship_world" in names:
        assert names.index("latent_knowledge") < names.index("relationship_world")


def test_latent_knowledge_card_carries_the_do_not_volunteer_constraint() -> None:
    """卡片的**核心**：知道，但不主动提。

    这条断言是本需求的验收点。用户原话「我不主动提到就不唤醒」——
    如果指令里没有这条约束，卡片就退化成普通记忆，需求落空。
    """

    messages = PromptBuilder().build(
        _context(
            latentKnowledge=[
                {
                    "ownerNpcId": "Sophia",
                    "content": "阿比盖尔在群里说她最近在练剑",
                    "participants": ["Sophia", "Abigail"],
                }
            ]
        ),
        "早上好",
    )
    card = next(m for m in messages if m.get("name") == "latent_knowledge")
    content = card["content"]

    assert "不主动" in content
    assert "阿比盖尔" in content


def test_latent_knowledge_card_does_not_fake_first_person() -> None:
    """别人的话不能被写成「她自己说过」。

    这是 `historyByNpc` 与 `latent_knowledge` 的分工线：
    - 她**自己**在群里说的 → 进私聊历史（第一人称，像她说过的话）
    - **别人**说的 → 进隐性知识（第三人称转述，不是她的台词）

    两者混在一起，NPC 会在私聊里把别人的话当成自己的话说出口。
    """

    messages = PromptBuilder().build(
        _context(
            latentKnowledge=[
                {
                    "ownerNpcId": "Sophia",
                    "content": "阿比盖尔在群里说她最近在练剑",
                    "participants": ["Sophia", "Abigail"],
                }
            ]
        ),
        "早上好",
    )
    card = next(m for m in messages if m.get("name") == "latent_knowledge")
    content = card["content"]

    # 转述必须指明说话人，不能只剩内容让人误以为是本 NPC 的发言。
    assert "谁说的" in content or "第三人称" in content or "转述" in content


def test_latent_knowledge_card_only_includes_facts_owned_by_current_npc() -> None:
    """`ownerNpcId` 不是当前 NPC 的隐性知识不能出现。

    与 `_memory_record_text` 的 `knownBy` 判定同一条口径：记忆挂在谁的
    prompt 上，判断标准就是谁记得它。
    """

    messages = PromptBuilder().build(
        _context(
            latentKnowledge=[
                {
                    "ownerNpcId": "Sophia",
                    "content": "索菲娅该看到的",
                    "participants": ["Sophia", "Abigail"],
                },
                {
                    "ownerNpcId": "Emily",
                    "content": "艾米丽才知道的",
                    "participants": ["Emily", "Abigail"],
                },
            ]
        ),
        "早上好",
    )
    card = next(m for m in messages if m.get("name") == "latent_knowledge")
    content = card["content"]

    assert "索菲娅该看到的" in content
    assert "艾米丽才知道的" not in content


def test_latent_knowledge_card_is_hard_capped() -> None:
    """条数封顶，避免群聊攒久了把 prompt 撑爆。"""

    facts = [
        {
            "ownerNpcId": "Sophia",
            "content": f"第 {index} 条隐性知识",
            "participants": ["Sophia", "Abigail"],
        }
        for index in range(40)
    ]

    messages = PromptBuilder().build(_context(latentKnowledge=facts), "早上好")
    card = next(m for m in messages if m.get("name") == "latent_knowledge")

    # 40 条远超任何合理上限；卡片内容不该随输入线性膨胀。
    assert len(card["content"]) < 6000