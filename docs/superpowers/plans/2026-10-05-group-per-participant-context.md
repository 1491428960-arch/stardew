# 群聊「每人一份」私有上下文 实现计划

> **面向 AI 代理的工作者：** 按任务顺序内联执行；每完成一个任务再进下一个。项目红线：**不提交 git、不启动游戏**。

**目标：** 让 F9 群聊里**每位参与者**都拿到自己那份关系世界与记忆事实，使 NPC 在 F9／F8／晨间读起来是同一个人格（用户 2026-10-04 08:27 的验收标准：「有一个感觉上是连续的 npc 的人格，他不会因为在 f8 还是 f9 中出现导致不像同一个人」）。

**架构：** 三处改动。①**协议层**：`GroupDialogueParticipant` 增加 `relationshipWorld`／`recentFacts` 两个可选字段（C# record + Python `GroupParticipant`）。②**Bridge 渲染层**：把它们做成**带归属的独立 system 消息块**，插在该参与者角色卡段落的段首 —— 沿用 2026-09-22 修群聊 BUG-1/BUG-2 时已经验证过的两层归属机制（`participant_card_boundary` + name 后缀）。③**收集层**：`GroupDialogueMenu` 为每位参与者调 `RelationshipSnapshotFor(npcId)` 与 `RecentMemoryFacts(npcId)`。

顶层（无归属）的 `recentFacts`／`relationshipWorld` 槽位**保留在 Bridge 侧**以兼容旧 DLL，但新 DLL 不再发它们。

**技术栈：** C# 12 / .NET 6 / SMAPI / xUnit；Python 3.10 / pydantic v2 / pytest。

**发布顺序（红线）：** **Bridge 先、DLL 后**。`ApiModel` 是 `extra="forbid"`，新 DLL + 旧 Bridge = HTTP 422。

---

## 为什么改这三个地方（判据来源）

2026-09-22 在 `GroupDialogueMenu.cs:681-703` 写下的决定是**刻意的、不是漏接线**：

- `RecentMemoryFacts(npcId)` 是按 `OwnerNpcId` 过滤的**单 NPC 视角**，里面既有群里当众说过的事，也有玩家**只跟这一个 NPC** 私下说过的事；
- `RelationshipSnapshotFor(npcId)` 同理，是以该 NPC 为 viewer 组织的「我认识谁、谁和谁是什么关系」；
- 而当时 `group_scene` 卡里的这两个槽位都是**无归属的单槽位**，把三份并排塞进去 = 让另外两人读到别人的私事（「把 Alex 的关系网塞给 Shane」）—— **越界知识，比不传更糟**。

同一份注释里已经写下了正确做法：**「按参与者拆成「每人一份」的槽位（与参与者角色卡同构），那是 Bridge 侧的改动」**，并明确警告「不要顺手把它补成 active speaker 的快照」。本计划做的就是这件事。

归属问题为什么能在卡内解决：`_participant_card_boundary`（2026-09-22 修 BUG-2）已经证明——**给出明确归属 + 明确禁令后，模型能守住**；BUG-1/BUG-2 的根因正是「无归属」，不是「模型看到了别人的内容」（multi_turn 本来就会把所有人的角色卡拼进同一个数组）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `bridge/src/stardew_ai_bridge/models.py` | `GroupParticipant` 承载每位参与者自己的关系世界与记忆 | 修改 L508-526 |
| `bridge/src/stardew_ai_bridge/group_conversation.py` | 把私有上下文渲染成带归属的消息块 | 修改 L220-349，新增 helper |
| `bridge/tests/test_group_participant_context.py` | Bridge 侧回归 | 创建 |
| `smapi/ConversationModels.cs` | 协议字段 | 修改 L123-126 |
| `smapi/BridgeClient.cs` | 把字段投出去（含截断） | 修改 L592-597 |
| `smapi/GroupDialogueMenu.cs` | 收集每人一份 + 改写过时注释 | 修改 L681-693、L695-703、L704-717 |
| `smapi/tests/GroupDialogueParticipantContextTests.cs` | C# 侧回归 | 创建 |

---

## 任务 1：Bridge 接受每位参与者自己的关系世界与记忆

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/models.py:508-526`
- 测试：`bridge/tests/test_group_participant_context.py`（创建）

- [ ] **步骤 1：编写失败的测试**

创建 `bridge/tests/test_group_participant_context.py`：

```python
"""群聊「每人一份」私有上下文：协议层。"""

from __future__ import annotations

from stardew_ai_bridge.models import GroupDialogueRequest


def _payload() -> dict[str, object]:
    return {
        "message": "你们谁更喜欢夜市？",
        "strategy": "multi_turn",
        "channel": "remote",
        "participants": [
            {"npcId": "Abigail"},
            {"npcId": "Emily"},
        ],
    }


def test_group_participant_carries_its_own_recent_facts() -> None:
    payload = _payload()
    payload["participants"][0]["recentFacts"] = ["玩家上周说要去矿洞"]
    payload["participants"][1]["recentFacts"] = ["玩家说过想换把好锄头"]

    request = GroupDialogueRequest.model_validate(payload)

    assert request.participants[0].recent_facts == ["玩家上周说要去矿洞"]
    assert request.participants[1].recent_facts == ["玩家说过想换把好锄头"]


def test_group_participant_carries_its_own_relationship_world() -> None:
    payload = _payload()
    payload["participants"][0]["relationshipWorld"] = {
        "acceptanceByNpc": {"Abigail": "accepted"},
    }

    request = GroupDialogueRequest.model_validate(payload)

    assert request.participants[0].relationship_world is not None
    assert request.participants[0].relationship_world.acceptance_by_npc == {
        "Abigail": "accepted"
    }
    # 未给的那位保持空，绝不串用别人的那一份。
    assert request.participants[1].relationship_world is None
    assert request.participants[1].recent_facts == []
```

- [ ] **步骤 2：运行测试验证失败**

```powershell
$wt = 'E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory'
$env:PYTHONPATH = "$wt;$wt\bridge\src;$wt\scripts"
$env:PYTHONIOENCODING = 'utf-8'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest `
  bridge/tests/test_group_participant_context.py -q -p no:cacheprovider
```

预期：2 failed（`GroupParticipant` 不接受 `recentFacts`／`relationshipWorld`，报 `Extra inputs are not permitted`）。

- [ ] **步骤 3：编写最少实现代码**

`models.py` 的 `GroupParticipant`（L508-526）改为：

```python
class GroupParticipant(ApiModel):
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    display_name: str | None = Field(
        default=None,
        alias="displayName",
        min_length=1,
        max_length=100,
    )
    source_mods: list[str] = Field(
        default_factory=list,
        alias="sourceMods",
        max_length=50,
    )
    game_state: NpcGameState | None = Field(default=None, alias="gameState")
    # 2026-10-05：每位参与者**自己那份**私有上下文。
    #
    # 此前 group_scene 卡里只有无归属的单槽位 recentFacts / relationshipWorld，
    # 多人场里取谁的都是把别人的私事摊给全场看，所以生产端一直传 null（见
    # `GroupDialogueMenu.cs` 里 2026-09-22 的判据）。把槽位下移到参与者身上后，
    # 归属由 Bridge 侧的 `participant_private_context` 卡声明，越界问题在卡内解决。
    #
    # 顶层同名字段保留以兼容旧版 DLL（它仍在发无归属的那一份）。
    relationship_world: RelationshipWorldContext | None = Field(
        default=None,
        alias="relationshipWorld",
    )
    recent_facts: list[str] = Field(
        default_factory=list,
        alias="recentFacts",
        max_length=50,
    )

    _strip_npc_id = field_validator("npc_id", mode="before")(_strip_text)
    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )
```

- [ ] **步骤 4：运行测试验证通过**

同步骤 2 的命令。预期：`2 passed`。

---

## 任务 2：Bridge 把私有上下文渲染成带归属的消息块

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/group_conversation.py`（新增 helper；改 `build_group_messages` L262-294）
- 测试：`bridge/tests/test_group_participant_context.py`（追加）

- [ ] **步骤 1：编写失败的测试**

在 `bridge/tests/test_group_participant_context.py` 追加：

```python
import json

from stardew_ai_bridge.group_conversation import build_group_messages


def _messages(participants):
    return build_group_messages(
        participants=participants,
        active_npc_id="Abigail",
        participant_prompts={
            "abigail": [{"role": "system", "content": "A 卡", "name": "persona_core"}],
            "emily": [{"role": "system", "content": "E 卡", "name": "persona_core"}],
        },
        strategy="multi_turn",
        player_message="你们谁更喜欢夜市？",
    )


def test_each_participant_gets_its_own_private_context_block() -> None:
    messages = _messages(
        [
            {
                "npcId": "Abigail",
                "displayName": "Abigail",
                "recentFacts": ["玩家上周说要去矿洞"],
            },
            {
                "npcId": "Emily",
                "displayName": "Emily",
                "recentFacts": ["玩家说过想换把好锄头"],
            },
        ]
    )

    blocks = [
        json.loads(item["content"])
        for item in messages
        if item.get("name", "").startswith("participant_private_context")
    ]

    by_npc = {item["npcId"]: item for item in blocks}
    assert by_npc["Abigail"]["recentFacts"] == ["玩家上周说要去矿洞"]
    assert by_npc["Emily"]["recentFacts"] == ["玩家说过想换把好锄头"]
    # 归属化：块名带上 npcId，且块内声明只属于本人。
    assert any(
        item.get("name") == "participant_private_context_Abigail"
        for item in messages
    )
    assert "只属于" in by_npc["Abigail"]["scope"]
    # 明确禁止把别人的私事算到自己头上。
    assert "不要让名单里的其他人" in by_npc["Abigail"]["scope"]


def test_participant_without_private_context_gets_no_block() -> None:
    messages = _messages([{"npcId": "Abigail"}, {"npcId": "Emily"}])

    assert not [
        item
        for item in messages
        if item.get("name", "").startswith("participant_private_context")
    ]


def test_private_context_block_precedes_its_owner_card() -> None:
    """归属链必须连续：边界卡 → 本人私有上下文 → 本人角色卡。"""

    messages = _messages(
        [{"npcId": "Abigail", "recentFacts": ["玩家上周说要去矿洞"]}, {"npcId": "Emily"}]
    )
    names = [item.get("name", "") for item in messages]

    boundary_at = names.index("participant_card_boundary")
    context_at = next(
        index
        for index, name in enumerate(names)
        if name.startswith("participant_private_context")
    )
    card_at = names.index("persona_core")

    assert boundary_at < context_at < card_at
```

- [ ] **步骤 2：运行测试验证失败**

同任务 1 步骤 2 的命令。预期：3 failed（`participant_private_context*` 块不存在）。

- [ ] **步骤 3：编写最少实现代码**

在 `group_conversation.py` 的 `_participant_card_boundary` 之后（约 L127）新增：

```python
#: 参与者私有上下文卡：这位参与者**自己**的记忆与关系视角。
#: 与 `_participant_card_boundary` 同一套归属思路——多人场里模型只有拿到
#: 「这些事实属于谁」才能不串味（见文件头部 BUG-1/BUG-2 那段）。
_PARTICIPANT_CONTEXT_NAME = "participant_private_context"

_PARTICIPANT_CONTEXT_SCOPE = (
    "以下是这位参与者一个人的私有上下文，只属于他：这些记忆与关系视角都是"
    "他自己知道的事，名单里的其他人并不知道，也没有对他说过这里的内容。"
    "不要让名单里的其他人说出、知道、认领或转述这里的事实；"
    "他本人也不必主动提起，只在话题自然相关时才用，"
    "并且不要把它当成本场群聊里已经公开说过的话。"
)


def _participant_context_name(npc_id: str) -> str:
    """把私有上下文卡的名字归属化，规则与语气样例一致。"""

    return _style_example_name(npc_id).replace(
        _STYLE_EXAMPLE_NAME, _PARTICIPANT_CONTEXT_NAME, 1
    )


def _participant_entry(
    participants: Sequence[GroupParticipant | Mapping[str, object]],
    npc_id: str,
) -> GroupParticipant | Mapping[str, object] | None:
    target = npc_id.casefold()
    for item in participants:
        if str(_participant_value(item, "npc_id", "npcId")).casefold() == target:
            return item
    return None


def _participant_private_context(
    *,
    npc_id: str,
    display_name: str,
    relationship_world: object,
    recent_facts: object,
) -> dict[str, str] | None:
    """这位参与者自己的私有上下文卡；两样都空时返回 None（不插空卡）。"""

    world = (
        relationship_world.model_dump(by_alias=True, exclude_none=True)
        if isinstance(relationship_world, RelationshipWorldContext)
        else relationship_world
    )
    facts = [
        str(item).strip()
        for item in (recent_facts or ())
        if str(item).strip()
    ]
    has_world = bool(world)
    if not has_world and not facts:
        return None

    return {
        "role": "system",
        "name": _participant_context_name(npc_id),
        "content": json.dumps(
            {
                "npcId": npc_id,
                "displayName": display_name,
                "scope": _PARTICIPANT_CONTEXT_SCOPE,
                "relationshipWorld": world if has_world else {},
                "recentFacts": facts,
            },
            ensure_ascii=False,
        ),
    }
```

把 `build_group_messages` 的卡拼接循环（L262-294）改为：

```python
    merge_cards = len(speakers) > 1
    messages: list[dict[str, str]] = []
    for npc_id in speakers:
        block = prompts.get(npc_id.casefold()) or ()
        # 边界卡懒插入：这份卡一条可保留消息都没有时不插，免得出现
        # 一张指向空卡的分隔卡（角色卡取不到时会走到这里）。
        boundary = (
            _participant_card_boundary(
                npc_id, display_name_by_id.get(npc_id.casefold(), "")
            )
            if merge_cards
            else None
        )
        # 每人一份的私有上下文：紧跟边界卡，让归属链连续
        # （边界卡说「这段属于 X」→ 私有上下文说「这些是 X 自己的」→ X 的角色卡）。
        context_card = None
        entry = _participant_entry(participants, npc_id)
        if entry is not None:
            context_card = _participant_private_context(
                npc_id=npc_id,
                display_name=display_name_by_id.get(npc_id.casefold(), ""),
                relationship_world=_participant_value(
                    entry, "relationship_world", "relationshipWorld"
                ),
                recent_facts=_participant_value(
                    entry, "recent_facts", "recentFacts"
                ),
            )
        inserted_context = False
        for message in block:
            if not isinstance(message, Mapping):
                continue
            # 玩家输入由群聊统一追加，角色卡里各自的末条 user 消息要去掉。
            if str(message.get("role")) == "user":
                continue
            rendered = {
                "role": str(message.get("role") or "system"),
                "content": str(message.get("content") or ""),
            }
            name = message.get("name")
            if isinstance(name, str) and name:
                # 语气样例必须标明归属：它和别的参与者的样例在同一个数组里，
                # 而 name 在此前是完全相同的（BUG-1 的成因）。
                if name == _STYLE_EXAMPLE_NAME:
                    name = _style_example_name(npc_id)
                rendered["name"] = name
            if boundary is not None:
                messages.append(boundary)
                boundary = None
            if context_card is not None and not inserted_context:
                messages.append(context_card)
                inserted_context = True
            messages.append(rendered)
        # 角色卡一条可保留消息都没有时（取不到卡），私有上下文仍然要落地：
        # 否则这位参与者在这一轮里完全不可见，比不传更糟。
        if context_card is not None and not inserted_context:
            messages.append(context_card)
```

在文件顶部的 import 里补上 `RelationshipWorldContext`（若尚未导入——L231 已经在用这个名字，可能已导入；**先看该行再决定是否修改**）。

- [ ] **步骤 4：运行测试验证通过**

同任务 1 步骤 2 的命令。预期：`5 passed`。

---

## 任务 3：C# 协议层投出每人一份

**文件：**
- 修改：`smapi/ConversationModels.cs:123-126`
- 修改：`smapi/BridgeClient.cs:592-597`
- 测试：`smapi/tests/GroupDialogueParticipantContextTests.cs`（创建）

- [ ] **步骤 1：编写失败的测试**

创建 `smapi/tests/GroupDialogueParticipantContextTests.cs`：

```csharp
using System.Linq;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupDialogueParticipantContextTests
{
    [Fact]
    public void Participant_CarriesItsOwnRelationshipWorldAndFacts()
    {
        var snapshot = new RelationshipWorldSnapshot(
            "Abigail",
            System.Array.Empty<RelationshipEdgeRecord>(),
            System.Array.Empty<RelationshipViewRecord>(),
            null,
            null);

        var participant = new GroupDialogueParticipant(
            "Abigail",
            "Abigail",
            null,
            snapshot,
            new[] { "玩家上周说要去矿洞" });

        Assert.Same(snapshot, participant.RelationshipWorld);
        Assert.Equal(new[] { "玩家上周说要去矿洞" }, participant.RecentFacts);
    }

    [Fact]
    public void Participant_DefaultsToNoPrivateContext()
    {
        var participant = new GroupDialogueParticipant("Abigail", "Abigail");

        Assert.Null(participant.RelationshipWorld);
        Assert.Null(participant.RecentFacts);
    }
}
```

- [ ] **步骤 2：运行测试验证失败**

```powershell
pwsh -NoProfile -Command "Set-Location 'E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory'; dotnet test smapi\tests\StardewAI.NPC.Tests.csproj -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' --filter 'FullyQualifiedName~GroupDialogueParticipantContextTests'"
```

预期：**编译失败**（`GroupDialogueParticipant` 没有 5 个参数的构造函数）。

- [ ] **步骤 3：编写最少实现代码**

`ConversationModels.cs:123-126` 改为：

```csharp
public sealed record GroupDialogueParticipant(
    [property: JsonPropertyName("npcId")] string NpcId,
    [property: JsonPropertyName("displayName")] string DisplayName,
    [property: JsonPropertyName("gameState")] NpcGameState? GameState = null,
    // 2026-10-05：这位参与者**自己那份**私有上下文。此前群聊只有无归属的单槽位
    // （见 GroupDialogueMenu 里 2026-09-22 的判据），多人场里取谁的都是越界，
    // 所以一直传 null。槽位下移到参与者身上后，Bridge 侧按人渲染成带归属的卡。
    [property: JsonPropertyName("relationshipWorld")]
    RelationshipWorldSnapshot? RelationshipWorld = null,
    [property: JsonPropertyName("recentFacts")]
    IReadOnlyList<string>? RecentFacts = null);
```

`BridgeClient.cs:592-597` 的 `Participants` 绑定改为（截断口径与顶层那份一致）：

```csharp
            Participants = participants
                .Select(item => new GroupDialogueParticipant(
                    item.NpcId.Trim(),
                    Truncate(item.DisplayName?.Trim() ?? item.NpcId.Trim(), 100),
                    item.GameState,
                    item.RelationshipWorld,
                    (item.RecentFacts ?? Array.Empty<string>())
                        .Where(value => !string.IsNullOrWhiteSpace(value))
                        .Take(MaxRecentFactItems)
                        .Select(value => Truncate(value.Trim(), MaxRecentFactLength))
                        .ToArray()))
                .ToArray(),
```

- [ ] **步骤 4：运行测试验证通过**

同步骤 2 的命令。预期：`2 passed`。

---

## 任务 4：群聊菜单为每位参与者收集

**文件：**
- 修改：`smapi/GroupDialogueMenu.cs:681-717`

- [ ] **步骤 1：编写失败的测试**

项目里 `GroupDialogueMenu` 继承 SMAPI 菜单基类，无法直接单测（与 10-04 隐性知识那次同一约束）。因此这一步改为**可测的纯函数 + 一个断言请求形状的测试**：

在 `smapi/tests/GroupDialogueParticipantContextTests.cs` 追加：

```csharp
    [Fact]
    public void Request_KeepsTopLevelContextUnattributed()
    {
        // 顶层字段没有归属，必须保持 null：新 DLL 的私有上下文只在 participants 里。
        var request = new GroupDialogueRequest(
            "你们谁更喜欢夜市？",
            new[]
            {
                new GroupDialogueParticipant(
                    "Abigail",
                    "Abigail",
                    null,
                    new RelationshipWorldSnapshot(
                        "Abigail",
                        System.Array.Empty<RelationshipEdgeRecord>(),
                        System.Array.Empty<RelationshipViewRecord>(),
                        null,
                        null),
                    new[] { "玩家上周说要去矿洞" }),
                new GroupDialogueParticipant("Emily", "Emily"),
            },
            null,
            null,
            System.Array.Empty<GroupDialogueHistoryEntry>(),
            "Abigail");

        Assert.Null(request.RelationshipWorld);
        Assert.Null(request.RecentFacts);
        Assert.NotNull(request.Participants[0].RelationshipWorld);
        Assert.Null(request.Participants[1].RelationshipWorld);
    }
```

- [ ] **步骤 2：运行测试验证失败**

同任务 3 步骤 2 的命令，把 filter 换成 `GroupDialogueParticipantContextTests`。预期：`3 passed`（该测试在任务 3 的字段落地后即成立——**它保护的是「顶层保持 null」这条口径**，删掉 `GroupDialogueMenu` 的改动不会让它变红，所以它只是契约锚点，不是行为测试）。

> ⚠ 诚实标注：`GroupDialogueMenu.SendCurrentAsync` 的行为在项目里**没有**单元测试覆盖（菜单基类不可测）。这一步的「红」来自编译期——把 L693/L716 改成 `null` 后如果忘了补 per-participant 收集，编译仍会通过，所以**没有红灯**。因此实施时以「代码审查 + 在 `LastRequestParticipantIds` 旁新增诊断字段」作为证据，并在任务 5 用穿透测试补上行为证据。

- [ ] **步骤 3：编写最少实现代码**

`GroupDialogueMenu.cs` 中，把 L681-693（recentFacts 注释 + 赋值）与 L695-703（relationshipWorld 注释）整段替换为：

```csharp
        // 每人一份的私有上下文（2026-10-05）—— 取代此前的「只给 active speaker 一份」。
        //
        // 2026-09-22 的决定是**刻意的、不是漏接线**：`RecentMemoryFacts(npcId)` 是按
        // OwnerNpcId 过滤的单 NPC 视角，`RelationshipSnapshotFor(npcId)` 是以该 NPC 为
        // viewer 组织的关系视图；而当时 Bridge 的 `group_scene` 卡里这两个槽位都是
        // **无归属的单槽位**，把三份并排塞进去等于让另外两人读到别人的私事
        // （「把 Alex 的关系网塞给 Shane」）——越界知识，比不传更糟。
        //
        // 现在 Bridge 侧给出了 per-NPC 槽位（`_participant_private_context`，卡名带
        // npcId，卡内声明「只属于他、别人不知道」），归属问题在卡内解决，
        // 与参与者角色卡同构。因此这里改为**每位参与者带自己那一份**。
        //
        // 顶层 recentFacts / relationshipWorld 仍然传 null：它们没有归属，
        // 只会把同一批私事变成无主数据（Bridge 侧保留这两个槽位只为兼容旧 DLL）。
        var participantsWithContext = participantsWithState
            .Select(item => item with
            {
                RelationshipWorld = storyStateStore.RelationshipSnapshotFor(item.NpcId),
                RecentFacts = storyStateStore.RecentMemoryFacts(item.NpcId),
            })
            .ToArray();
```

把 L675-680 的诊断三行改为使用新变量，并补两个证据字段：

```csharp
        // 诊断证据：请求里每个参与者是否带上了各自的状态与私有上下文。
        LastRequestParticipants = participantsWithContext;
        LastRequestParticipantIds = participantsWithContext
            .Select(item => item.NpcId)
            .ToArray();
        LastRequestStateCount = participantsWithContext
            .Count(item => item.GameState is not null);
        LastRequestContextCount = participantsWithContext
            .Count(item => item.RelationshipWorld is not null && item.RecentFacts is not null);
```

在诊断字段声明处（`LastRequestStateCount` 附近，约 L674）补：

```csharp
    /// <summary>
    /// 本轮请求里带上了**自己那份**私有上下文的参与者数（关系快照与记忆都在才算）。
    /// 它是「每人一份」这条口径的现场证据：光看代码无法发现某位参与者的快照取成空。
    /// </summary>
    public int LastRequestContextCount { get; private set; }
```

把 L704-717 的请求构造中 `recentFacts` / `null`（relationshipWorld）两处实参保持为：

```csharp
            null,   // 顶层 recentFacts：无归属，改用 participants 里每人一份
            null,   // 顶层 relationshipWorld：同上
```

并把第一个实参 `participantsWithState` 改为 `participantsWithContext`。

- [ ] **步骤 4：运行测试验证通过**

同任务 3 步骤 2 的命令，filter 用 `GroupDialogueParticipantContextTests`。预期：`3 passed`。

- [ ] **步骤 5：编译整个 SMAPI 工程**

```powershell
pwsh -NoProfile -Command "Set-Location 'E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory'; dotnet build smapi\StardewAI.NPC.csproj -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -c Release"
```

预期：`0 Error(s)`、`0 Warning(s)`（项目把警告当信号看）。

---

## 任务 5：端到端穿透测试（Bridge 侧）

**文件：**
- 测试：`bridge/tests/test_group_participant_context.py`（追加）

项目纪律（`docs/STATE.md` §四 #10/#11）：**卡必须在「无条件下」也能生成**，且要有一条穿透测试横跨「请求模型 → 卡渲染」，否则「字段在传输途中被悄悄吞掉」这类缺陷两个套件全绿也发现不了（10-04 隐性知识那次的实际教训：`_DIALOGUE_FIELDS` 白名单漏一个 key = 提示词永远为空、无任何报错）。

- [ ] **步骤 1：编写失败的测试**

```python
def test_private_context_survives_the_full_request_path() -> None:
    """穿透：请求 JSON → 模型校验 → 群聊卡。字段在途中被吞掉就会红。"""

    from stardew_ai_bridge.group_conversation import GroupConversationService

    request = GroupDialogueRequest.model_validate(
        {
            "message": "你们谁更喜欢夜市？",
            "strategy": "multi_turn",
            "channel": "remote",
            "participants": [
                {
                    "npcId": "Abigail",
                    "displayName": "Abigail",
                    "recentFacts": ["玩家上周说要去矿洞"],
                    "relationshipWorld": {"acceptanceByNpc": {"Abigail": "accepted"}},
                },
                {"npcId": "Emily", "displayName": "Emily"},
            ],
        }
    )

    messages = build_group_messages(
        participants=request.participants,
        active_npc_id="Abigail",
        participant_prompts={},
        strategy="multi_turn",
        player_message=request.message,
    )

    contexts = [
        json.loads(item["content"])
        for item in messages
        if item.get("name", "").startswith("participant_private_context")
    ]
    assert len(contexts) == 1, "只有带了私有上下文的那位才该有卡"
    assert contexts[0]["npcId"] == "Abigail"
    assert contexts[0]["recentFacts"] == ["玩家上周说要去矿洞"]
    assert contexts[0]["relationshipWorld"] == {"acceptanceByNpc": {"Abigail": "accepted"}}
```

- [ ] **步骤 2：运行测试验证失败／通过**

同任务 1 步骤 2 的命令。预期：`6 passed`。若这一条红而任务 2 的绿，说明渲染层读了错误的字段名——不要在渲染层加兼容分支，回去核对 `_participant_value` 的 key／alias。

---

## 任务 6：全量验证

- [ ] **步骤 1：项目一键验证**

```powershell
pwsh -NoProfile -File 'E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\scripts\verify_project.ps1'
```

预期：`SMAPI 测试` PASS、`Bridge 测试` PASS（≥ 4424 passed 基线）、`compileall` PASS、`git diff --check` PASS，退出码 0。

- [ ] **步骤 2：记录证据**

把真实输出（SMAPI 通过数、Bridge passed 数）写进 `story-memory/docs/active-work.md` 末尾，并把 `story-memory/docs/STATE.md` 的 §五 改动清单补上本线的三处文件与新增测试。**不提交 git。**

- [ ] **步骤 3：部署提醒（不属于本计划动作）**

新 DLL **尚未部署**——`ApiModel` 是 `extra="forbid"`，所以游戏侧要生效必须先重启 Bridge 再换 DLL。这一条在向用户汇报时明确写出，不要声称「已实机验证」。

---

## 阶段二（素材）：**先对齐再动手**，不属于本计划

用户选定的顺序是「先地基后素材」。地基落地后，「把已接受的多元关系转成打趣／调侃素材」需要一个**产品级设计决定**，本计划不预设它。已经确定的约束（来自用户原话与既有 spec，实施时不得违反）：

1. **不许改晨间现有 163 条预设的一个字。** 用户 2026-10-04 08:23 的裁定是「不要为了统一这边的东西去改晨间对话，而是 f8f9 的自由聊天、预设群聊改动要适应晨间聊天的存在」。要加只能**新增**条目。用户更早（08:31 前的裁定 ②）说过「把这个作为打趣加入群聊话题和晨间话题」，两句出自不同时间，**晚的那句管着早的那句**。⚠ **2026-10-05 更新：用户裁定晨间侧「不加」，本条第 1 点已作废**（详见 `docs/STATE.md` §其四），打趣素材只进群聊邀约引导。
2. **调解只做一次。** 用户裁定：「只有第一次触发这种情况触发这个机制就行了，后续角色把这个作为**打趣**加入群聊话题和晨间话题」；「只会有一批触发这个机制的角色需要这样的调解，在这之后再发生亲密关系的角色应当默认了解并接受玩家有多个亲密对象的事实」（见 `docs/superpowers/specs/2026-09-05-multi-relationship-world-design.md`）。
3. **邀约卡不得宣告关系结果**（`2026-09-10-in-game-group-dialogue-invitations-design.md` L128）：关系／嫉妒／修复／亲密只作为**公共语境约束**进入，不作为卡片标题或结论。
4. **素材的事实依据已经在地基里。** `RelationshipSnapshotFor(npcId)` 对每位 viewer 都注入了「玩家已婚 X」的公开视图（`CounterpartNpcId`，2026-10-04 婚姻的另一端修复），并带该 NPC 自己的 `mediation`／`jealousy`——所以「打趣」所需的事实是**每人一份且不越界**的，不需要另造数据源。阶段二要做的是**语气与场合**的设计，不是数据管道。
5. 群聊既有校准（2026-09-19）不得回退：不要让一个人把话说完、「两个人里不要只有一个人说话，三个人里也不要只出现一个人」是承重规则。

对齐时要问的那一个问题：**打趣的落点是「群聊邀约话题模板」（`GroupInvitationTemplates` 按 角色组合 × 主题 现场生成）还是「群聊场景卡里新增一类素材段」？** 前者复用现有的主题机制、天然是「当众」场合；后者能带进具体的调解阶段与接受度。两者对「谁在场才打趣」的判据不同。
