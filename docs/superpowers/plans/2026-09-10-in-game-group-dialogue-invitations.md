# 游戏内线上多人对话邀约实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现。每完成一个任务运行对应检查点；本项目禁止创建 Git commit，计划中不安排提交步骤。

**目标：** 在不改变 F8 单 NPC 当面聊天的前提下，增加 F9 线上多人对话中心、周期性本地邀约卡、自由参与者选择和已有 `/api/dialogue/group` 的 `turn_based` 游戏端接线。

**架构：** SMAPI 端新增独立的邀约模型、确定性本地生成器、故事状态存储扩展、F9 菜单和多人会话菜单；`ModEntry` 只负责按键与游戏事件转发。Bridge 端扩展已有多人请求以接收受控的邀约主题/引导；游戏端 `BridgeClient` 复用现有 loopback HTTP 客户端，单人历史与多人公开历史分开管理。

**技术栈：** C#、.NET 6 SMAPI Mod、xUnit/.NET 8 测试、System.Text.Json、现有 FastAPI/Pydantic Bridge、Python 3.10 pytest。

---

## 文件职责总览

| 文件 | 职责 |
|---|---|
| `smapi/ModConfig.cs` | 新增并规范化默认 F9 多人入口键 |
| `smapi/GroupDialogueModels.cs` | 邀约、参与者、Bridge 多人请求/响应和会话记录模型 |
| `smapi/GroupInvitationRules.cs` | 纯函数形式的数量、间隔、过期、去重和状态转移规则 |
| `smapi/GroupInvitationTemplates.cs` | 本地无网络的中性/角色主题模板白名单 |
| `smapi/GroupInvitationGenerator.cs` | 根据游戏状态候选和模板生成最多一张新邀约 |
| `smapi/GroupInvitationStore.cs` | 从 `StoryStateStore` 读取、更新、清理和持久化邀约 |
| `smapi/StoryStateModels.cs` | 在故事状态信封中加入可选邀约列表 |
| `smapi/StoryStateValidation.cs` | 校验邀约 ID、参与者、日期、模板和状态 |
| `smapi/StoryStateSerializer.cs` | 序列化邀约、加载旧存档、跳过非法记录并保留警告 |
| `smapi/BridgeClient.cs` | POST `/api/dialogue/group`、脱敏错误和响应白名单校验 |
| `smapi/GroupDialogueSessionRules.cs` | 多人会话轮次、历史和失败重试的纯规则 |
| `smapi/GroupDialogueHubMenu.cs` | F9 入口、邀约列表、自由发起按钮 |
| `smapi/GroupParticipantMenu.cs` | 选择 2～3 名已认识 NPC |
| `smapi/GroupDialogueMenu.cs` | 输入消息、逐条渲染 NPC 回复、继续/结束/重试 |
| `smapi/GroupDialogueLayoutRules.cs` | 多人菜单的纯布局和可见消息规则 |
| `smapi/GroupDialogueCoordinator.cs` | 连接日开始、F9 入口、菜单生命周期和生成器 |
| `smapi/KnownNpcResolver.cs` | 从玩家 friendship 数据得到可联系 NPC，不依赖 NPC 在当前地图 |
| `smapi/ModEntry.cs` | 注册协调器、转发事件，不承载邀约业务逻辑 |
| `bridge/src/stardew_ai_bridge/models.py` | 扩展多人请求的邀约上下文字段 |
| `bridge/src/stardew_ai_bridge/group_conversation.py` | 把邀约上下文作为受控公开场景加入多人 Prompt |
| `bridge/tests/test_group_conversation.py` | Bridge 邀约上下文和接口回归 |
| `smapi/tests/*` | C# 规则、持久化、HTTP 契约和配置测试 |

## 任务 1：建立 F9 配置与邀约数据契约

**文件：**

- 修改：`smapi/ModConfig.cs`
- 创建：`smapi/GroupDialogueModels.cs`
- 修改：`smapi/StoryStateModels.cs`
- 测试：`smapi/tests/ModConfigTests.cs`
- 测试：`smapi/tests/GroupInvitationRulesTests.cs`

- [ ] **步骤 1：先写失败测试**

在 `ModConfigTests.cs` 增加：

```csharp
[Fact]
public void Default_group_dialogue_key_is_F9()
{
    var config = new ModConfig();

    Assert.Equal(SButton.F9, config.GroupDialogueKey.Keybinds.Single().Buttons.Single());
}

[Fact]
public void Group_dialogue_key_cannot_share_the_single_dialogue_key()
{
    var config = new ModConfig
    {
        DialogueKey = KeybindList.Parse("F9"),
        GroupDialogueKey = KeybindList.Parse("F9"),
    };

    var normalized = config.Normalize();

    Assert.Equal(SButton.F8, normalized.DialogueKey.Keybinds.Single().Buttons.Single());
    Assert.Equal(SButton.F9, normalized.GroupDialogueKey.Keybinds.Single().Buttons.Single());
}
```

在 `GroupInvitationRulesTests.cs` 先声明期望的模型行为：

```csharp
[Fact]
public void Invitation_requires_two_to_three_unique_participants()
{
    Assert.True(GroupInvitationRules.IsValidParticipantCount(2));
    Assert.True(GroupInvitationRules.IsValidParticipantCount(3));
    Assert.False(GroupInvitationRules.IsValidParticipantCount(1));
    Assert.False(GroupInvitationRules.IsValidParticipantCount(4));
}

[Fact]
public void Invitation_key_is_order_independent_for_duplicate_detection()
{
    var first = GroupInvitationRules.BuildPairKey(new[] { "Abigail", "Emily" });
    var second = GroupInvitationRules.BuildPairKey(new[] { "Emily", "Abigail" });

    Assert.Equal(first, second);
}
```

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~ModConfigTests|FullyQualifiedName~GroupInvitationRulesTests"
```

预期：因 `GroupDialogueKey`、`GroupInvitationRules` 和邀约模型尚不存在而失败；若出现项目引用或 `GamePath` 错误，先修正测试环境，不把环境错误当成行为红灯。

- [ ] **步骤 3：写最小数据模型**

在 `ModConfig` 增加：

```csharp
public KeybindList GroupDialogueKey { get; set; } = new(SButton.F9);
```

`Normalize()` 保留有效自定义键；无效键回退 F9；若与 `DialogueKey` 完全相同，则保留用户显式设置的单人键，把多人键移到另一个安全默认键（F9 冲突时使用 F10，其余冲突使用 F9），保证两个入口始终可区分。

在 `GroupDialogueModels.cs` 定义：

```csharp
public enum GroupInvitationStatus
{
    Unread,
    Deferred,
    Accepted,
    Dismissed,
    Completed,
    Expired,
}

public sealed record GroupDialogueInvitationRecord
{
    public string InvitationId { get; init; } = string.Empty;
    public string TemplateId { get; init; } = string.Empty;
    public IReadOnlyList<string> Participants { get; init; } = Array.Empty<string>();
    public IReadOnlyList<string> ParticipantDisplayNames { get; init; } = Array.Empty<string>();
    public string Title { get; init; } = string.Empty;
    public string Topic { get; init; } = string.Empty;
    public string Guidance { get; init; } = string.Empty;
    public string CreatedOn { get; init; } = string.Empty;
    public string ExpiresOn { get; init; } = string.Empty;
    public int CreatedTotalDays { get; init; }
    public int ExpiresTotalDays { get; init; }
    public string Source { get; init; } = "periodic";
    public GroupInvitationStatus Status { get; init; } = GroupInvitationStatus.Unread;
}

public sealed record GroupParticipantCandidate(
    string NpcId,
    string DisplayName,
    bool HasFriendshipRecord);

public sealed record GroupDialogueHistoryEntry(
    string SpeakerType,
    string SpeakerId,
    string Content);
```

在 `StoryStateEnvelope` 增加 `GroupDialogueInvitations` 可选列表，旧 JSON 缺失时按空列表加载。字段使用现有 `JsonPropertyName` 规则，状态使用 `JsonStringEnumConverter`，不保存 Authorization、Provider payload 或 API 错误正文。

- [ ] **步骤 4：运行绿灯测试**

运行同一条 `dotnet test` 命令，预期配置和模型规则测试通过；随后运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~ModConfigTests"
```

预期：现有 F8 配置测试和新增 F9 测试全部通过。

## 任务 2：实现邀约校验、状态转移和故事状态兼容

**文件：**

- 创建：`smapi/GroupInvitationRules.cs`
- 创建：`smapi/GroupInvitationStore.cs`
- 修改：`smapi/StoryStateValidation.cs`
- 修改：`smapi/StoryStateSerializer.cs`
- 修改：`smapi/StoryStateStore.cs`
- 测试：`smapi/tests/GroupInvitationRulesTests.cs`
- 测试：`smapi/tests/StoryStateSerializerTests.cs`
- 测试：`smapi/tests/StoryStateStoreTests.cs`

- [ ] **步骤 1：写失败的规则测试**

覆盖以下行为：

```csharp
[Fact]
public void New_invitation_is_allowed_only_every_two_total_days_when_pending_limit_is_not_reached()
{
    Assert.True(GroupInvitationRules.ShouldGenerate(20, 18, pendingCount: 0));
    Assert.False(GroupInvitationRules.ShouldGenerate(19, 18, pendingCount: 0));
    Assert.False(GroupInvitationRules.ShouldGenerate(20, 18, pendingCount: 3));
}

[Fact]
public void Invitation_expires_after_seven_total_days()
{
    Assert.False(GroupInvitationRules.IsExpired(26, createdTotalDays: 20, expiresTotalDays: 27));
    Assert.True(GroupInvitationRules.IsExpired(27, createdTotalDays: 20, expiresTotalDays: 27));
}

[Fact]
public void Failed_request_does_not_complete_invitation()
{
    var accepted = new GroupDialogueInvitationRecord
    {
        InvitationId = "invite-1",
        Participants = new[] { "Abigail", "Emily" },
        Status = GroupInvitationStatus.Accepted,
    };

    var next = GroupInvitationRules.AfterConversationResult(accepted, usableReply: false);

    Assert.Equal(GroupInvitationStatus.Accepted, next.Status);
}
```

在 `StoryStateSerializerTests.cs` 增加：

- 缺少 `groupDialogueInvitations` 的旧 JSON 仍然正常加载；
- 一个合法邀约和一个非法邀约混合时只保留合法邀约并产生警告；
- 序列化结果不包含 `authorization`、`apiKey`、`providerPayload` 或完整错误响应字段。

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~GroupInvitationRulesTests|FullyQualifiedName~StoryStateSerializerTests|FullyQualifiedName~StoryStateStoreTests"
```

预期：新增规则、验证和状态字段相关测试失败，旧状态兼容测试保持可运行。

- [ ] **步骤 3：实现最小规则和状态层**

`GroupInvitationRules` 固定常量：

```csharp
public const int GenerationIntervalDays = 2;
public const int MaxPendingInvitations = 3;
public const int ExpirationDays = 7;
```

实现以下纯方法：

```csharp
public static bool ShouldGenerate(int currentTotalDays, int? lastCreatedTotalDays, int pendingCount);
public static bool IsExpired(int currentTotalDays, int createdTotalDays, int expiresTotalDays);
public static string BuildPairKey(IEnumerable<string> npcIds);
public static string BuildDuplicateKey(GroupDialogueInvitationRecord invitation);
public static GroupDialogueInvitationRecord SetStatus(
    GroupDialogueInvitationRecord invitation,
    GroupInvitationStatus status);
public static GroupDialogueInvitationRecord AfterConversationResult(
    GroupDialogueInvitationRecord invitation,
    bool usableReply);
```

`GroupInvitationStore` 提供：

```csharp
public IReadOnlyList<GroupDialogueInvitationRecord> Active(int currentTotalDays);
public void ReplaceAll(IEnumerable<GroupDialogueInvitationRecord> invitations);
public bool TrySetStatus(string invitationId, GroupInvitationStatus status);
public void Expire(int currentTotalDays);
```

`StoryStateStore` 只负责把邀约列表放进/取出 `StoryStateEnvelope`，所有更新必须走 `StoryStateSerializer.Serialize` 的统一验证。`StoryStateSerializer.Load` 遇到非法邀约时跳过该条并将 `group invitation <invitationId> skipped: <reason>` 加入 warnings，不因一条坏卡丢弃整个存档。

- [ ] **步骤 4：运行持久化定向测试**

运行同一条 `dotnet test` 命令，预期全部通过；再运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~StoryStateSerializerTests|FullyQualifiedName~StoryStateStoreTests"
```

## 任务 3：实现确定性的本地邀约模板和生成器

**文件：**

- 创建：`smapi/GroupInvitationTemplates.cs`
- 创建：`smapi/GroupInvitationGenerator.cs`
- 测试：`smapi/tests/GroupInvitationGeneratorTests.cs`

- [ ] **步骤 1：写失败测试**

`GroupInvitationGeneratorTests.cs` 使用纯数据，不创建 `Game1`：

```csharp
[Fact]
public void Generator_creates_one_neutral_invitation_for_two_known_npcs()
{
    var generator = new GroupInvitationGenerator(GroupInvitationTemplates.All);
    var result = generator.Generate(new GroupInvitationGenerationContext(
        CurrentTotalDays: 20,
        CurrentDateLabel: "Spring 20",
        KnownParticipants: new[]
        {
            new GroupParticipantCandidate("Abigail", "Abigail", true),
            new GroupParticipantCandidate("Emily", "Emily", true),
        },
        ExistingInvitations: Array.Empty<GroupDialogueInvitationRecord>(),
        RecentTopicKeys: Array.Empty<string>(),
        LastCreatedTotalDays: 18));

    var invitation = Assert.Single(result);
    Assert.Equal(new[] { "Abigail", "Emily" }, invitation.Participants);
    Assert.Equal(GroupInvitationStatus.Unread, invitation.Status);
    Assert.Equal(27, invitation.ExpiresTotalDays);
}

[Fact]
public void Generator_does_not_repeat_recent_template_and_pair()
{
    var existing = new GroupDialogueInvitationRecord
    {
        InvitationId = "old",
        TemplateId = "neutral-public-topic",
        Participants = new[] { "Abigail", "Emily" },
        CreatedTotalDays = 14,
        ExpiresTotalDays = 21,
        Status = GroupInvitationStatus.Completed,
    };

    var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
        new GroupInvitationGenerationContext(
            20,
            "Spring 20",
            new[]
            {
                new GroupParticipantCandidate("Abigail", "Abigail", true),
                new GroupParticipantCandidate("Emily", "Emily", true),
            },
            new[] { existing },
            Array.Empty<string>(),
            18));

    Assert.DoesNotContain(result, item => item.TemplateId == existing.TemplateId &&
        GroupInvitationRules.BuildPairKey(item.Participants) ==
        GroupInvitationRules.BuildPairKey(existing.Participants));
}
```

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~GroupInvitationGeneratorTests"
```

预期：因模板目录、生成上下文和生成器不存在而失败。

- [ ] **步骤 3：实现白名单模板和生成器**

定义：

```csharp
public sealed record GroupInvitationTemplate(
    string TemplateId,
    string Title,
    string Topic,
    string Guidance,
    string Source);

public sealed record GroupInvitationGenerationContext(
    int CurrentTotalDays,
    string CurrentDateLabel,
    IReadOnlyList<GroupParticipantCandidate> KnownParticipants,
    IReadOnlyList<GroupDialogueInvitationRecord> ExistingInvitations,
    IReadOnlyList<string> RecentTopicKeys,
    int? LastCreatedTotalDays);
```

`GroupInvitationTemplates.All` 至少包含：

- `neutral-public-topic`：任何两个已认识角色都可用，主题是最近的公共小事，不写未来约定；
- `mineral-and-mystery`：Abigail + Emily 可用，主题是矿石/矿洞传闻；
- `research-follow-up`：Wizard + Sophia 可用，主题是研究观察；
- `social-perspective`：Alex + Sebastian 可用，主题是玩家与他人相处时的不同看法。

模板文本都是中性玩家引导，不使用 NPC 第一人称，不把未发生事件写成事实。生成器按以下顺序选候选：先选符合角色白名单的专属模板，再选 `neutral-public-topic`；NPC 按 `NpcId` 忽略大小写排序，组合选择由 `CurrentTotalDays` 对候选索引取模，保证同一输入可复现；模板+参与者最近 7 天重复则跳过。生成成功后设置 `CreatedTotalDays=current`、`ExpiresTotalDays=current+7`、状态 `Unread`、来源为模板来源。

- [ ] **步骤 4：运行生成器测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~GroupInvitationGeneratorTests"
```

预期：新增生成器测试全部通过，并确认生成器没有任何网络依赖。

## 任务 4：扩展 Bridge 多人上下文契约

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/models.py`
- 修改：`bridge/src/stardew_ai_bridge/group_conversation.py`
- 测试：`bridge/tests/test_group_conversation.py`

- [ ] **步骤 1：写失败测试**

增加：

```python
def test_group_request_accepts_invitation_context() -> None:
    request = GroupDialogueRequest.model_validate(
        {
            "message": "你们怎么看？",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "remote",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "invitationTopic": "奇怪的矿石",
            "invitationGuidance": "只把它当作讨论方向，不把它当作已经确认的事实。",
        }
    )

    assert request.invitation_topic == "奇怪的矿石"
    assert "讨论方向" in request.invitation_guidance


def test_group_prompt_marks_invitation_as_non_canonical_guidance() -> None:
    request = GroupDialogueRequest.model_validate(
        {
            "message": "你们怎么看？",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "remote",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "invitationTopic": "奇怪的矿石",
            "invitationGuidance": "这是玩家选择的话题方向，不是 NPC 已确认的事实。",
        }
    )

    prompt = build_group_prompt(
        active_npc_id="Abigail",
        participants=request.participants,
        shared_game_state=request.game_state,
        relationship_world=request.relationship_world,
        recent_facts=request.recent_facts,
        public_history=[item.model_dump(by_alias=True) for item in request.history],
        player_message=request.message,
        strategy=request.strategy,
        invitation_topic=request.invitation_topic,
        invitation_guidance=request.invitation_guidance,
    )
    rendered = json.dumps(prompt, ensure_ascii=False)

    assert "奇怪的矿石" in rendered
    assert "不是 NPC 已确认的事实" in rendered
```

若现有测试辅助不适合暴露 Prompt，新增一个只读的模块函数参数检查，不向生产 API 添加测试专用网络入口。

- [ ] **步骤 2：运行 Bridge 红灯测试**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_group_conversation.py -k 'invitation'
```

预期：因请求字段和 Prompt 上下文不存在而失败。

- [ ] **步骤 3：实现最小 Bridge 扩展**

在 `GroupDialogueRequest` 增加：

```python
invitation_topic: str | None = Field(
    default=None,
    alias="invitationTopic",
    max_length=240,
)
invitation_guidance: str | None = Field(
    default=None,
    alias="invitationGuidance",
    max_length=500,
)
```

在 `build_group_prompt` 的受控 JSON 上下文中加入 `invitation` 对象，并明确它是玩家选择的方向，不是 canonical 事实、NPC 记忆或未来承诺。云端和 Fake Provider 都继续使用同一 Prompt 构造；不记录完整请求或敏感配置。

- [ ] **步骤 4：运行 Bridge 定向与全量测试**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_group_conversation.py
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests
```

预期：多人定向测试和 Bridge 全量测试均无失败；这里只验证离线契约，不发起 Gemini 或中转站请求。

## 任务 5：实现 C# Bridge 多人客户端和响应门控

**文件：**

- 修改：`smapi/BridgeClient.cs`
- 修改：`smapi/ConversationModels.cs`
- 测试：`smapi/tests/BridgeClientTests.cs`

- [ ] **步骤 1：写失败的 HTTP 契约测试**

使用现有 `HttpMessageHandler` 测试辅助，增加：

```csharp
[Fact]
public async Task SendGroupAsync_posts_remote_turn_based_request_and_parses_turns()
{
    var handler = new RecordingHandler("""
    {
      "strategy":"turn_based",
      "channel":"remote",
      "provider":"fake",
      "fallback":false,
      "turns":[{"speakerNpcId":"Abigail","content":"我有点想知道。"}],
      "providerCalls":1,
      "providerErrors":[],
      "fallbackCount":0,
      "latencyMs":12
    }
    """);
    using var client = new BridgeClient(
        new HttpClient(handler), new Uri("http://127.0.0.1:5678"));

    var response = await client.SendGroupAsync(
        new GroupDialogueRequest(
            "你们怎么看？",
            new[] { new GroupDialogueParticipant("Abigail", "Abigail"), new("Emily", "Emily") },
            "奇怪的矿石",
            "只作为讨论方向。",
            Array.Empty<GroupDialogueHistoryEntry>()));

    Assert.Equal("/api/dialogue/group", handler.LastRequest!.RequestUri!.AbsolutePath);
    Assert.Equal("Abigail", Assert.Single(response.Turns).SpeakerNpcId);
    Assert.Contains("invitationTopic", handler.LastBody, StringComparison.Ordinal);
}

[Fact]
public async Task SendGroupAsync_rejects_unknown_speaker_without_exposing_content()
{
    var handler = new RecordingHandler("""
    {"strategy":"turn_based","channel":"remote","provider":"cloud","fallback":false,
     "turns":[{"speakerNpcId":"Lewis","content":"越界文本"}],"providerCalls":1,
     "providerErrors":[],"fallbackCount":0,"latencyMs":1}
    """);
    using var client = new BridgeClient(new HttpClient(handler));

    var response = await client.SendGroupAsync(
        TestGroupRequest(new[] { "Abigail", "Emily" }));

    Assert.True(response.Fallback);
    Assert.Empty(response.Turns);
    Assert.DoesNotContain("越界文本", response.Warnings);
}
```

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~BridgeClientTests"
```

预期：因多人请求模型、端点和 `SendGroupAsync` 尚不存在而失败。

- [ ] **步骤 3：实现请求和响应**

在 `ConversationModels.cs` 定义 `GroupDialogueParticipant`、`GroupDialogueRequest`、`GroupDialogueHistoryEntry`，在 `BridgeClient.cs` 定义带 `JsonPropertyName` 的 `BridgeGroupDialogueRequest`、`BridgeGroupDialogueResponse` 和 `BridgeGroupTurn`。请求字段固定为：

```text
message
provider
strategy=turn_based
channel=remote
participants
activeSpeakerNpcId
history
invitationTopic
invitationGuidance
gameState
recentFacts
relationshipWorld
```

`BridgeClient` 构造 `/api/dialogue/group` endpoint，并实现：

```csharp
public async Task<BridgeGroupDialogueResponse> SendGroupAsync(
    GroupDialogueRequest request,
    CancellationToken cancellationToken = default);
```

方法要求：

- 只接受 2～3 个唯一参与者；
- 强制 `remote` 和 `turn_based`，不接受游戏端把本地频道送到此方法；
- 限制消息、主题、引导、历史长度，避免把完整存档发送到 Bridge；
- HTTP 非 2xx、超时、JSON 结构错误、空 `turns` 和未知 `speakerNpcId` 返回 `Fallback=true` 的安全对象；
- 失败对象只保存短诊断标签，不保存 Provider 原始 body、Authorization 或 Key；
- 可用回复只保留参与者白名单内、非空的 `BridgeGroupTurn`。

- [ ] **步骤 4：运行 Bridge 客户端测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~BridgeClientTests"
```

预期：现有单人 HTTP 测试和新增多人请求/响应门控测试全部通过。

## 任务 6：实现邀约生成与存档连接

**文件：**

- 创建：`smapi/KnownNpcResolver.cs`
- 修改：`smapi/FriendshipDataAccessor.cs`
- 创建：`smapi/GroupDialogueCoordinator.cs`
- 修改：`smapi/ModEntry.cs`
- 测试：`smapi/tests/FriendshipDataAccessorTests.cs`
- 测试：`smapi/tests/GroupDialogueCoordinatorTests.cs`

- [ ] **步骤 1：写失败测试**

增加纯规则测试：

```csharp
[Fact]
public void KnownNpcResolver_keeps_only_friendship_keys_with_loaded_characters()
{
    var result = KnownNpcResolver.Resolve(
        new[] { "Abigail", "UnknownNpc", "player" },
        npcId => npcId == "Abigail"
            ? new KnownNpc("Abigail", "Abigail")
            : null);

    var npc = Assert.Single(result);
    Assert.Equal("Abigail", npc.NpcId);
}

[Fact]
public void Coordinator_generates_at_most_one_invitation_on_a_due_day()
{
    var store = new StoryStateStore();
    var generator = new GroupInvitationGenerator(GroupInvitationTemplates.All);
    var candidates = new[]
    {
        new GroupParticipantCandidate("Abigail", "Abigail", true),
        new GroupParticipantCandidate("Emily", "Emily", true),
    };
    var coordinator = new GroupDialogueCoordinator(
        store,
        generator,
        () => candidates,
        () => 20,
        () => "Spring 20");

    coordinator.OnDayStarted();
    var first = store.State.GroupDialogueInvitations
        .Where(item => item.Status is GroupInvitationStatus.Unread or GroupInvitationStatus.Deferred)
        .ToArray();
    coordinator.OnDayStarted();
    var second = store.State.GroupDialogueInvitations
        .Where(item => item.Status is GroupInvitationStatus.Unread or GroupInvitationStatus.Deferred)
        .ToArray();

    Assert.Single(first);
    Assert.Empty(second);
}
```

如 `ModEntry` 依赖过重，测试不直接 new `ModEntry`，而是测试 coordinator 的纯输入/输出构造；游戏事件只在集成接线阶段编译验证。

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~FriendshipDataAccessorTests|FullyQualifiedName~GroupDialogueCoordinatorTests"
```

预期：因枚举 friendship keys、已知 NPC 解析和协调器尚不存在而失败。

- [ ] **步骤 3：实现已知 NPC 解析和协调器**

为 `FriendshipDataAccessor` 增加只读 `Keys(object? data)`，兼容 `IDictionary`、带 `Keys` 属性的字典和可枚举 key/value 项；遇到无法读取的数据返回空列表，不抛出到游戏主循环。

`KnownNpcResolver` 接收 friendship keys 和 `Func<string, KnownNpc?>`，过滤空值、`player`、内部测试 NPC、无法通过 `Game1.getCharacterFromName` 解析的角色；不要求 NPC 当前在地图上。

`GroupDialogueCoordinator` 构造函数接收 `StoryStateStore`、`GroupInvitationGenerator`、`Func<IReadOnlyList<GroupParticipantCandidate>>`、`Func<int>` 当前总天数提供器和 `Func<string>` 当前日期标签提供器，公开：

```csharp
public void OnDayStarted();
public bool TryOpen();
public void CloseIfOpen();
```

`OnDayStarted()` 使用 `Game1.Date.TotalDays`、`Game1.currentSeason`、`Game1.dayOfMonth`，先过期已有邀约，再按规则最多生成一张；没有合适角色或事件状态不适合时不生成。它不调用 HTTP。

在 `ModEntry`：

- `Entry` 创建 coordinator，并注册到现有 `DayStarted`、`SaveLoaded`、`ReturnedToTitle` 事件；
- `OnDayStarted` 只转发，不把模板和筛选逻辑写进 `ModEntry`；
- `OnReturnedToTitle` 关闭多人菜单并清理临时会话；
- 现有 `OnSaving` 的 `StoryStateStore.Serialize()` 自动包含邀约；
- 现有 F8、face-to-face、测试 NPC 生命周期保持原样。

- [ ] **步骤 4：运行接线定向测试和构建**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~GroupDialogueCoordinatorTests|FullyQualifiedName~FriendshipDataAccessorTests"
dotnet build smapi/StardewAI.NPC.csproj --no-restore -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：定向测试通过，Mod 编译为 0 warning、0 error；不启动 Stardew Valley 或 SMAPI。

## 任务 7：先实现纯会话规则，再接入三个菜单

**文件：**

- 创建：`smapi/GroupDialogueSessionRules.cs`
- 创建：`smapi/GroupDialogueLayoutRules.cs`
- 创建：`smapi/GroupDialogueHubMenu.cs`
- 创建：`smapi/GroupParticipantMenu.cs`
- 创建：`smapi/GroupDialogueMenu.cs`
- 测试：`smapi/tests/GroupDialogueSessionRulesTests.cs`
- 测试：`smapi/tests/GroupDialogueLayoutRulesTests.cs`

- [ ] **步骤 1：写失败的会话和布局测试**

覆盖：

```csharp
[Fact]
public void Successful_first_turn_completes_accepted_invitation()
{
    var invitation = AcceptedInvitation();

    var next = GroupDialogueSessionRules.ApplyResult(
        invitation,
        new[] { new BridgeGroupTurn("Abigail", "我有点想知道。") },
        fallback: false);

    Assert.Equal(GroupInvitationStatus.Completed, next.Status);
}

[Fact]
public void Failed_turn_keeps_invitation_retryable_and_drops_history()
{
    var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

    var result = GroupDialogueSessionRules.ApplyResult(
        session,
        Array.Empty<BridgeGroupTurn>(),
        fallback: true);

    Assert.Empty(result.PublicHistory);
    Assert.True(result.CanRetry);
    Assert.Equal(GroupInvitationStatus.Accepted, result.Invitation.Status);
}

[Fact]
public void Layout_rejects_non_positive_viewport()
{
    Assert.Throws<ArgumentOutOfRangeException>(() => GroupDialogueLayoutRules.Calculate(0, 720));
}
```

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~GroupDialogueSessionRulesTests|FullyQualifiedName~GroupDialogueLayoutRulesTests"
```

预期：因会话状态模型、轮次校验和多人布局规则不存在而失败。

- [ ] **步骤 3：实现纯会话层**

`GroupDialogueSessionRules` 定义：

```csharp
public sealed record GroupDialogueSession(
    GroupDialogueInvitationRecord Invitation,
    IReadOnlyList<GroupDialogueHistoryEntry> PublicHistory,
    bool CanRetry);

public static GroupDialogueSession Create(GroupDialogueInvitationRecord invitation);
public static GroupDialogueInvitationRecord ApplyResult(
    GroupDialogueInvitationRecord invitation,
    IReadOnlyList<BridgeGroupTurn> turns,
    bool fallback);
public static GroupDialogueSession ApplyResult(
    GroupDialogueSession session,
    IReadOnlyList<BridgeGroupTurn> turns,
    bool fallback);
public static bool IsValidTurn(
    BridgeGroupTurn turn,
    IReadOnlySet<string> participantIds);
```

规则：首次成功且至少有一条合法回复时邀约变为 `Completed`；失败、fallback、空回复、未知 speaker 时保留 `Accepted`、清空本次新增历史并允许重试；历史只追加合法的 `speakerNpcId/content`，不追加错误文本。服务端返回的 `addressedTo` 只作展示辅助，不用来改变参与者。

`GroupDialogueLayoutRules` 提供与 `ChatLayoutRules` 同样风格的矩形计算、可见消息上限和底部按钮区域，至少包含群聊标题、参与者标签、消息区域、输入框、发送、重试和关闭按钮。

- [ ] **步骤 4：实现 Hub 和参与者菜单**

`GroupDialogueHubMenu`：

- 标题显示“线上多人对话”；
- 显示未过期邀约的标题、参与者、主题、剩余天数和状态；
- 接受邀约进入 `GroupDialogueMenu`；
- 稍后改为 `Deferred`，忽略改为 `Dismissed`；
- “自由发起”进入 `GroupParticipantMenu`；
- 没有可用 Bridge 时仍可浏览邀约，但接受后错误只在菜单内显示。

`GroupParticipantMenu`：

- 显示 friendship keys 中已认识且有资料的 NPC；
- 选择 2～3 人才启用开始按钮；
- 不要求 NPC 在当前地图；
- 不允许 `player`、内部测试 NPC、重复 NPC 或空选择；
- 开始时创建一个没有 invitationId 的自由会话。

- [ ] **步骤 5：实现多人聊天菜单**

`GroupDialogueMenu` 持有：

- `BridgeClient`；
- 当前参与者；
- 受控邀约主题和引导；
- `GroupDialogueSession`；
- `CancellationTokenSource`；
- 公开历史和待处理 HTTP 请求。

发送时将当前玩家消息和公开历史传给 `SendGroupAsync`，固定 `strategy=turn_based`、`channel=remote`。响应到达后按 `speakerNpcId` 查找头像/显示名，一次显示一条或一轮中的连续条目；未知角色和 fallback 不进入历史。关闭时取消请求并释放键盘订阅，不更改 NPC 位置或日程。

- [ ] **步骤 6：运行菜单规则测试和构建**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~GroupDialogueSessionRulesTests|FullyQualifiedName~GroupDialogueLayoutRulesTests"
dotnet build smapi/StardewAI.NPC.csproj --no-restore -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：规则测试通过，项目构建为 0 warning、0 error；不进行游戏内操作。

## 任务 8：接入 F9 入口并保持 F8/线下边界

**文件：**

- 修改：`smapi/ModEntry.cs`
- 修改：`smapi/DialogueEntryRules.cs`
- 修改：`smapi/GroupDialogueCoordinator.cs`
- 测试：`smapi/tests/ModConfigTests.cs`
- 测试：`smapi/tests/DialogueEntryRulesTests.cs`
- 测试：`smapi/tests/GroupDialogueCoordinatorTests.cs`

- [ ] **步骤 1：写失败测试**

覆盖：

```csharp
[Fact]
public void Group_entry_is_blocked_when_any_menu_is_open()
{
    Assert.False(DialogueEntryRules.CanOpenGroup(
        enabled: true,
        worldReady: true,
        hasMenu: true,
        hasBridgeClient: true));
}

[Fact]
public void Group_entry_does_not_require_npc_in_current_location()
{
    Assert.True(DialogueEntryRules.CanOpenGroup(
        enabled: true,
        worldReady: true,
        hasMenu: false,
        hasBridgeClient: true));
}
```

- [ ] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~DialogueEntryRulesTests|FullyQualifiedName~GroupDialogueCoordinatorTests"
```

预期：因群聊入口规则和 F9 按键接线尚不存在而失败。

- [ ] **步骤 3：实现入口接线**

新增 `DialogueEntryRules.CanOpenGroup`，条件为：启用、世界已加载、没有 active menu、BridgeClient 存在。`ModEntry.OnButtonPressed` 按以下顺序处理：

1. 保留现有动作键、接吻和重复聊天逻辑；
2. 识别 `GroupDialogueKey.JustPressed()`，通过 `CanOpenGroup` 后调用 `groupDialogueCoordinator.TryOpen()`；
3. 识别原有 `DialogueKey.JustPressed()`，继续走现有 `ResolveFriendshipTarget` + `FaceToFaceConversationCoordinator.TryOpenChat`；
4. F9 不读取鼠标目标、不检查 NPC 是否在当前地点、不调用 `ResolveFriendshipTarget`。

`ApplyConfig` 同时更新 `dialogueKey` 和 `groupDialogueKey`；重载配置时关闭多人会话并释放已有 BridgeClient 的逻辑与单人服务保持一致。启动日志说明 F8/F9 的分工，但不输出 endpoint 中的任何密钥或环境内容。

- [ ] **步骤 4：运行入口回归**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter "FullyQualifiedName~ModConfigTests|FullyQualifiedName~DialogueEntryRulesTests|FullyQualifiedName~GroupDialogueCoordinatorTests"
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore
```

预期：入口定向测试和 C# 全量测试均通过；确认 F8 相关测试没有变化导致的回归。

## 任务 9：统一离线验证和文档记录

**文件：**

- 修改：`docs/active-work.md`
- 修改：`docs/test-cases.md`
- 视测试结果修改：上述 C#/Python 实现和测试文件

- [ ] **步骤 1：运行 Bridge 定向和全量测试**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_group_conversation.py
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests
```

预期：多人请求上下文测试和 Bridge 全量测试均通过；不启动 Bridge，不发起 Gemini、中转站或 Qwen 请求。

- [ ] **步骤 2：运行 C# 全量测试和构建**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore
dotnet build smapi/StardewAI.NPC.csproj --no-restore -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：C# 全量测试通过，Mod 构建为 0 warning、0 error；`EnableModDeploy=false` 和 `EnableModZip=false` 保持不部署 DLL、不生成正式 Mod 压缩包。

- [ ] **步骤 3：运行静态和空白检查**

运行：

```powershell
py -3.10 -B -m compileall -q bridge/src scripts
git diff --check
```

预期：Python 编译和 diff 空白检查退出码均为 `0`。检查结果中出现的既有 LF/CRLF 提示单独记录，不覆盖或格式化用户现有修改。

- [ ] **步骤 4：更新活动记录**

在 `docs/active-work.md` 顶部新增一条事实记录，写明：

- F9 入口、周期邀约和多人客户端是否完成；
- C# 定向/全量测试、Bridge 定向/全量测试、构建和静态检查的真实输出；
- 没有启动 Stardew/SMAPI、没有部署 DLL、没有发起真实云端请求；
- 游戏内视觉和真实多人交互仍需隔离测试存档验证，不能用编译成功或 Bridge `/health` 代替。

## 计划自检

- 每个规格章节都有对应任务：入口在任务 8，邀约模型/生成/存储在任务 1～3，Bridge 上下文与客户端在任务 4～5，菜单和失败重试在任务 7，测试与边界记录在任务 9。
- 所有生产代码变更都有先写失败测试、运行红灯、最小实现、运行绿灯的顺序。
- Bridge 只新增受控邀约字段，不改变已有单 NPC API；游戏端多人固定 `remote + turn_based`。
- 失败、fallback、空回复和未知 speaker 不进入公开历史，不把邀约标为 completed。
- 生成器完全本地确定性运行，不因新的一天自动请求云端。
- F8 单人、face-to-face、SMAPI 游戏、正式 Mods、存档和角色资料库均保持边界。
- 计划中没有删除、reset、clean、checkout 或提交步骤；所有改动继续保留在当前 dirty worktree。
