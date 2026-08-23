# 剧情与常态记忆基础实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 TDD 逐任务实现本计划。步骤使用复选框跟踪进度。

**目标：** 在不改变现有 UI 和原版剧情的前提下，建立可验证的版本化故事状态、NPC 记忆记录和有效互动阶段门槛。

**架构：** 状态模型和规则放在 SMAPI Mod 的纯 C# 层，使用 `System.Text.Json` 做版本化序列化。第一里程碑不直接接入存档事件或 Bridge；先让模型、校验、损坏数据降级和互动门槛可以独立测试，后续再由 `ModEntry` 接入 SMAPI 的存档生命周期。

**技术栈：** .NET 6 Mod、.NET 8 xUnit 测试、`System.Text.Json`、现有 `StardewAI.NPC` 项目。

---

## 文件职责

- 创建：`smapi/StoryStateModels.cs`
  - 定义 `StoryStateEnvelope`、`StoryEventRecord`、`MemoryRecord`、`KnowledgeRecord`、`RelationshipEdgeRecord`、`InteractionProgress` 及相关枚举。
- 创建：`smapi/StoryStateValidation.cs`
  - 校验必填字段、置信度、重要性、参与者和知识范围；不依赖 SMAPI 或游戏对象。
- 创建：`smapi/StoryStateSerializer.cs`
  - 负责 `stardew-ai-npc/story-state/v1` 的 JSON 序列化、反序列化、版本检查和坏记录跳过。
- 创建：`smapi/InteractionProgressRules.cs`
  - 实现有效互动判定、每日计数限制和普通/重大阶段的默认门槛。
- 创建：`smapi/tests/StoryStateValidationTests.cs`
  - 覆盖记忆字段完整性和数值边界。
- 创建：`smapi/tests/StoryStateSerializerTests.cs`
  - 覆盖版本化 JSON、无效记录跳过和未知版本降级。
- 创建：`smapi/tests/InteractionProgressRulesTests.cs`
  - 覆盖空消息、fallback、重复消息、每日上限和 4/5 次阶段门槛。

本计划不修改 `ModEntry.cs`、`BridgeClient.cs`、`DialogueMenu.cs` 或现有角色资料，避免把尚未完成的 UI 和运行时事件采集混入基础数据契约。

### 任务 1：记忆和故事状态模型

**文件：**
- 创建：`smapi/StoryStateModels.cs`
- 测试：`smapi/tests/StoryStateValidationTests.cs`

- [ ] **步骤 1：编写失败的字段校验测试**

```csharp
[Fact]
public void Memory_requires_source_confidence_date_participants_and_scope()
{
    var memory = new MemoryRecord
    {
        MemoryId = "memory-1",
        OwnerNpcId = "Sophia",
        Content = "玩家帮助我完成了葡萄园工作。",
        Source = MemorySource.PlayerChat,
        Confidence = 0.9,
        GameDate = "Spring 14",
        Participants = new[] { "Sophia", "player" },
        KnowledgeScope = MemoryKnowledgeScope.Participants,
    };

    var errors = StoryStateValidation.Validate(memory);

    Assert.Empty(errors);
}
```

- [ ] **步骤 2：运行测试确认因类型不存在而失败**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~StoryStateValidationTests
```

预期：编译失败，提示 `MemoryRecord` 或 `StoryStateValidation` 尚未定义。

- [ ] **步骤 3：实现最小模型和校验**

在 `StoryStateModels.cs` 中定义以下可序列化字段：

```csharp
public enum MemorySource
{
    VanillaEvent,
    ModEvent,
    Gift,
    ScheduleObservation,
    PlayerChat,
    NpcNpcEvent,
    SystemInference,
}

public enum MemoryKnowledgeScope
{
    Private,
    Participants,
    NpcGroup,
    Public,
    PlayerOnly,
}

public enum MemoryStatus
{
    Active,
    Corrected,
    Superseded,
    Forgotten,
}

public sealed class StoryEventRecord
{
    public string EventId { get; init; } = "";
    public string SourceMod { get; init; } = "";
    public string SourceKey { get; init; } = "";
    public IReadOnlyList<string> Participants { get; init; } = Array.Empty<string>();
    public string Status { get; init; } = "unknown";
    public string GameDate { get; init; } = "";
    public bool Canonical { get; init; }
    public string Summary { get; init; } = "";
}

public sealed class KnowledgeRecord
{
    public string MemoryId { get; init; } = "";
    public string OwnerNpcId { get; init; } = "";
    public MemoryKnowledgeScope KnowledgeScope { get; init; }
    public IReadOnlyList<string> KnownBy { get; init; } = Array.Empty<string>();
}

public sealed class RelationshipEdgeRecord
{
    public string FromNpcId { get; init; } = "";
    public string ToNpcId { get; init; } = "";
    public string RelationType { get; init; } = "";
    public double Strength { get; init; }
    public double Tension { get; init; }
    public string Source { get; init; } = "";
    public bool Canonical { get; init; }
    public string UpdatedOn { get; init; } = "";
}

public sealed class InteractionProgress
{
    public string NpcId { get; init; } = "";
    public string Stage { get; init; } = "";
    public int EffectiveSessions { get; init; }
    public int RequiredSessions { get; init; }
    public string? LastCountedGameDate { get; init; }
    public string? LastInteractionFingerprint { get; init; }

    public static InteractionProgress Create(string npcId, string stage);
}

public sealed record ConversationAttempt(
    string GameDate,
    string PlayerMessage,
    string NpcReply,
    bool UsedFallback);

public sealed class MemoryRecord
{
    public string MemoryId { get; init; } = "";
    public string OwnerNpcId { get; init; } = "";
    public string Kind { get; init; } = "fact";
    public string Content { get; init; } = "";
    public MemorySource Source { get; init; }
    public double Confidence { get; init; }
    public string GameDate { get; init; } = "";
    public IReadOnlyList<string> Participants { get; init; } = Array.Empty<string>();
    public MemoryKnowledgeScope KnowledgeScope { get; init; }
    public IReadOnlyList<string> KnownBy { get; init; } = Array.Empty<string>();
    public int Importance { get; init; }
    public bool Canonical { get; init; }
    public string? ExpiresOn { get; init; }
    public MemoryStatus Status { get; init; } = MemoryStatus.Active;
    public string Evidence { get; init; } = "";
}
```

`StoryStateValidation.Validate` 必须返回错误列表：空字符串字段、空参与者、置信度不在 `[0, 1]`、重要性不在 `[0, 3]` 都是错误；合法记录返回空列表。

- [ ] **步骤 4：运行测试确认字段校验通过**

运行同一步骤 2 的命令，预期：字段完整性、空参与者、置信度越界和重要性越界测试全部通过。

- [ ] **步骤 5：Commit**

```powershell
git add smapi/StoryStateModels.cs smapi/StoryStateValidation.cs smapi/tests/StoryStateValidationTests.cs
git commit -m "feat(记忆模型): 添加故事状态与记忆字段校验"
```

### 任务 2：版本化状态序列化

**文件：**
- 创建：`smapi/StoryStateSerializer.cs`
- 测试：`smapi/tests/StoryStateSerializerTests.cs`

- [ ] **步骤 1：编写失败的序列化测试**

```csharp
[Fact]
public void Serialize_and_load_preserves_schema_version_and_memory_provenance()
{
    var state = StoryStateEnvelope.Empty with
    {
        Memories = new[] { ValidMemory() },
    };

    var json = StoryStateSerializer.Serialize(state);
    var loaded = StoryStateSerializer.Load(json);

    Assert.Equal(1, loaded.State.SchemaVersion);
    Assert.Single(loaded.State.Memories);
    Assert.Equal(MemorySource.PlayerChat, loaded.State.Memories[0].Source);
    Assert.Empty(loaded.Warnings);
}
```

- [ ] **步骤 2：运行测试确认因序列化器不存在而失败**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~StoryStateSerializerTests
```

预期：编译失败，提示 `StoryStateEnvelope` 或 `StoryStateSerializer` 尚未定义。

- [ ] **步骤 3：实现版本化序列化和降级**

`StoryStateEnvelope` 固定 `SchemaVersion = 1`，包含 memories、story events、knowledge、relationships 和 interaction progress。`StoryStateSerializer.Load` 遵循以下规则：

1. JSON 无法解析时返回空状态和一条 warning，不抛出异常。
2. `schemaVersion` 大于当前版本时返回空状态和一条 warning。
3. 单条记录校验失败时跳过该记录，其余合法记录继续加载。
4. 序列化前拒绝包含非法字段的状态，错误信息不包含完整玩家消息或密钥。

模型和序列化器使用以下明确接口：

```csharp
public sealed record StoryStateEnvelope
{
    public int SchemaVersion { get; init; } = 1;
    public IReadOnlyList<MemoryRecord> Memories { get; init; } = Array.Empty<MemoryRecord>();
    public IReadOnlyList<StoryEventRecord> StoryEvents { get; init; } = Array.Empty<StoryEventRecord>();
    public IReadOnlyList<KnowledgeRecord> Knowledge { get; init; } = Array.Empty<KnowledgeRecord>();
    public IReadOnlyList<RelationshipEdgeRecord> Relationships { get; init; } = Array.Empty<RelationshipEdgeRecord>();
    public IReadOnlyList<InteractionProgress> InteractionProgresses { get; init; } = Array.Empty<InteractionProgress>();

    public static StoryStateEnvelope Empty => new();
}

public sealed record StoryStateLoadResult(
    StoryStateEnvelope State,
    IReadOnlyList<string> Warnings);

public static class StoryStateSerializer
{
    public static string Serialize(StoryStateEnvelope state);
    public static StoryStateLoadResult Load(string? json);
}
```

测试文件中的 `ValidMemory()` 是一个只返回完整合法记录的私有辅助函数，内容固定为 `Sophia`、`player`、`Spring 14` 和 `MemorySource.PlayerChat`，不读取外部文件。

- [ ] **步骤 4：运行测试确认序列化、坏记录和未知版本通过**

运行同一步骤 2 的命令，预期：所有测试通过，覆盖 JSON 损坏、未知版本和单条坏记忆跳过。

- [ ] **步骤 5：Commit**

```powershell
git add smapi/StoryStateSerializer.cs smapi/tests/StoryStateSerializerTests.cs
git commit -m "feat(持久化): 添加版本化故事状态序列化"
```

### 任务 3：有效互动和阶段门槛

**文件：**
- 创建：`smapi/InteractionProgressRules.cs`
- 测试：`smapi/tests/InteractionProgressRulesTests.cs`

- [ ] **步骤 1：编写失败的互动门槛测试**

```csharp
[Fact]
public void Ordinary_stage_requires_four_effective_sessions()
{
    var progress = InteractionProgress.Create("Sophia", "朋友");

    Assert.Equal(4, progress.RequiredSessions);
}

[Fact]
public void Fallback_empty_duplicate_and_second_session_same_day_do_not_count()
{
    var progress = InteractionProgress.Create("Sophia", "朋友");

    progress = InteractionProgressRules.Record(progress, Attempt("Spring 14", "葡萄园最近怎么样？", fallback: false));
    progress = InteractionProgressRules.Record(progress, Attempt("Spring 14", "你好", fallback: true));
    progress = InteractionProgressRules.Record(progress, Attempt("Spring 14", "葡萄园最近怎么样？", fallback: false));

    Assert.Equal(1, progress.EffectiveSessions);
}

private static ConversationAttempt Attempt(
    string gameDate,
    string playerMessage,
    bool fallback) =>
    new(
        gameDate,
        playerMessage,
        "NPC 回复",
        fallback);
```

- [ ] **步骤 2：运行测试确认因规则类不存在而失败**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~InteractionProgressRulesTests
```

预期：编译失败，提示互动规则类型尚未定义。

- [ ] **步骤 3：实现最小互动规则**

`ConversationAttempt` 必须包含游戏日期、玩家消息、NPC 回复和 `UsedFallback`。`InteractionProgressRules.Record` 只在以下条件全部满足时增加一次计数：消息和回复非空、未使用 fallback、当天尚未计数、消息指纹不同于上一次有效会话。普通阶段默认需要 4 次有效互动；恋爱、订婚/结婚、婚后和育儿阶段默认需要 5 次。

公开接口固定为：

```csharp
public static class InteractionProgressRules
{
    public static InteractionProgress Record(
        InteractionProgress progress,
        ConversationAttempt attempt);
}
```

`InteractionProgress.Create` 根据阶段名称设置门槛：`恋爱`、`订婚/结婚`、`婚后`、`育儿` 为 5，其余阶段为 4；初始计数为 0，最近日期和消息指纹为空。

- [ ] **步骤 4：运行测试确认规则通过**

运行同一步骤 2 的命令，预期：无效会话不计数、同日最多计数 1 次、普通阶段门槛为 4、重大阶段门槛为 5。

- [ ] **步骤 5：Commit**

```powershell
git add smapi/InteractionProgressRules.cs smapi/tests/InteractionProgressRulesTests.cs
git commit -m "feat(关系阶段): 添加有效互动计数门槛"
```

### 任务 4：基础回归与交接

**文件：**
- 修改：`docs/handoff-2026-08-23.md`
- 修改：`README.md`

- [ ] **步骤 1：运行完整自动化测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley"
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q -p no:cacheprovider
```

预期：C# 和 Bridge 测试均退出码为 0；若环境无法写入项目 `obj`，必须改用已批准的提升权限重新运行，不能把权限错误当作测试通过。

- [ ] **步骤 2：补充交接记录**

在交接文档中记录基础模型、序列化格式、测试命令和当前尚未接入游戏生命周期的边界；明确本里程碑不包含 UI、日程修改和真实存档回归。

- [ ] **步骤 3：Commit**

```powershell
git add docs/handoff-2026-08-23.md README.md
git commit -m "docs(交接): 记录故事状态基础里程碑"
```

## 计划自检

- 规格覆盖：本里程碑覆盖规格中的模型、记忆完整性、版本化持久化和有效互动门槛；事件采集、关系投影、NPC-NPC 日结和 UI 留在后续独立里程碑。
- 完整性扫描：每个步骤都给出了目标文件、明确接口、运行命令和预期结果。
- 类型一致性：所有任务统一使用 `StoryStateEnvelope`、`MemoryRecord`、`InteractionProgress`、`StoryStateSerializer` 和 `InteractionProgressRules`。
- 范围检查：本计划只修改纯状态基础层和文档，不接入当前暂停的 UI 分支。
