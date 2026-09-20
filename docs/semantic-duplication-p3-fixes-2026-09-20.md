# P3 结构风险（审计第 32～44 条）等价重构记录（2026-09-20）

> 对应 `docs/semantic-duplication-audit-2026-09-20.md` 的 **P3** 表。
> 原则：**只提取单一实现，不改变行为**；一切改动以单元测试锁住，
> 涉及渲染/点击坐标/视觉表现的改动不做（无法单测覆盖）。
> 本轮不改 `bridge/`（并行线在改），只动 `smapi/`。

## 逐条

| # | 结论 | 说明 |
|---|---|---|
| 32 | **不改（待真机验证）** | 设计文档写明官方建议按 `uiViewport`，当前 `ChatInputMenu`/`InventoryItemPicker` 用 `Game1.viewport`。切视口会改变渲染与点击坐标，单测无法覆盖 → 只记录。 |
| 33 | 已修 | `KissInteractionRules.CanTriggerKiss` 成为唯一点；`NpcKissAnimationController.TryStart` 删掉被前者的 8 项重复条件，只留 4 项运行时前置。 |
| 34 | 已修 | 新增 `FaceToFaceGate`（7 项）+ `FaceToFaceConversationCoordinator.CaptureGate`，续聊/亲吻共用同一批取值与同一判定。 |
| 35 | 只做等价抽取 | 2.5 格抽成 `FaceToFaceStateRules.RepeatChatNearbyDistanceInTiles`；两侧能聊到的 NPC 集合要不要一致属产品决策（B26），未动。 |
| 36 | 大部分已修 | `ChatLayoutRules.VisibleMessages` 由死规则变成唯一过滤实现（新增无上限重载）；群聊窗口抽成 `GroupDialogueLayoutRules.MaxVisibleMessages`。群聊的空内容不过滤（过滤会改变渲染）。 |
| 37 | 已修 | 新增 `GroupInvitationActionLayoutRules`：按钮矩形、命中区、pointerX 判定同源，draw / 点击 / 视觉测试三处共用。 |
| 38 | 已修 | 新增 `MenuPanelRules`（`SafeMargin` + `CenteredInViewport`），四个菜单共用；`48` 字面量统一为 `SafeMargin * 2`。 |
| 39 | 成员表已收敛，口径差异保留 | 新增 `RelationshipTypeRules`（单一成员表 + `IsSupported`/`IsRomantic`）；把口径统一成一种会改变行为（校验变宽或亲吻变严），留待产品决策，测试钉住差异。 |
| 40 | 已修 | `FriendshipDataAccessor.ReadData`/`HasRecord`；`ModEntry`、`VanillaGiftHandler` 改为引用，`ModEntry.ReadMember` 一并删除。 |
| 41 | 等价抽取 | 新增 `VisualTestHarnessRules.IsGameReadyFromGameState()`，视觉测试入口与 harness 共用同一批 Game1 取值；生产路径的 `Context.IsWorldReady` 未动。 |
| 42 | 已修 | 新增 `ResidentialDoorGateRules`：`600/2600/null/-1` 与 `"600"/"2600"/""/"0"` 两种形态一份定义，两条路径共用。 |
| 43 | 已修 | 重大阶段白名单下沉到 `RelationshipStageRules.IsMajorStage`，删掉域内不存在的死条目「订婚/结婚」；域内 7 个阶段名的 `RequiredSessions` 不变。 |
| 44 | 已修 | 新增 `MemoryRules`（上限 200/240、`Truncate` 含代理对保护、`BuildId` SHA256 前 24 位），单聊/群聊共用。**唯一非逐字等价点**：群聊截断现在也保护代理对（边界修正）。 |

## 附带修掉的范围外问题

- 构建的实际基线是 **2 个 nullable 警告**（都在 `GroupDialogueMenu.draw` 的提示行分支附近），与「0 警告」的记录不符。改用 `TryGetValue` 后归零；`SpeakerId` 为 null（模型声明非空，实际不会发生）时由「抛异常」退化为「空字符串」。
- `DoorActionParser.RelaxResidentialGate` 放行后把居民 token 清空，导致改写过 action 再也 `TryParse` 不通过——**改动前就如此**，已加测试记录，避免以后被当成回归。
- 群聊消息区是「按条数取最近 10 条」，私聊是「按高度取窗口 + 滚动」，两套语义不同；统一属视觉/产品决策。

## 待用户确认 / 跨语言协调

1. **#32 视口**：真机验证后决定是否把两个私聊菜单切到 `MenuViewportRules.PreferUiViewport`。
2. ~~**#39 口径**：`relationType` 的大小写口径要不要统一（需先确认 Bridge 侧发出的值大小写；并行线也在处理同类白名单）。~~ **跨语言风险已由父代理排除（2026-09-20，只读实测）**：SMAPI **发出的值全是小写**（`StoryStateStore.cs:197/350` 的 `RelationType = "married"`），Bridge 侧读到的与自身产出的也都是小写（`group_conversation_cases.py:90` 的 `"dating"`、`relationship_world.py:119/130/189` 的 `"married"`），且两侧的比较都用大小写敏感口径（C# `Ordinal`／Python `==`）。所以「`"Dating"` 校验拒绝、亲吻接受」这个差异**只可能由外部手工构造的状态触发**，不在跨语言链路上——**不需要跨语言协调**。剩下的只是「要不要统一内部口径」这个结构清理问题，优先级可降。
3. **#35 / B26**：F8 与交互键「能聊到的 NPC 集合」是否要一致。
4. **#41**：生产 `Context.IsWorldReady` 与 harness 的就绪判定是否需要收敛（需真机）。
5. **#33 约束**：亲吻门槛现只判一次，若将来出现第二个调用 `NpcKissAnimationController.TryStart` 的地方，必须先过 `KissInteractionRules.CanTriggerKiss`（注释已写明）。
