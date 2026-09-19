# 线上—线下未完事项闭环设计

日期：2026-09-06

状态：已按既定方案批准，进入实现

## 目标

为线上聊天和面对面聊天增加一条可持久化、可验证的最小故事接力：线上对话明确留下一个未完事项，下一次同一个 NPC 的面对面 AI 对话可以看到并主动接回；只有面对面回复明确表示该事项已经被处理，事项才关闭。

这个机制只保存故事状态，不修改 NPC 日程、路线、位置、好感度、婚姻原版字段或存档中的行为安排。

## 范围与非目标

本次包含：

- C# 故事状态中的 `OpenLoopRecord`、序列化、校验、当前 NPC 视角投影和状态迁移。
- `ConversationService`、`BridgeClient` 和 `ChatInputMenu` 的 `remote` / `face_to_face` 渠道传递。
- Bridge 的 `openLoop` 结构化响应契约、当前 NPC 隔离、Prompt 接入和 API 返回。
- fallback、空回复、ProviderError、非法元数据和跨 NPC 串线的自动化回归。

本次不包含：

- 从普通对白文本用正则或关键词猜测未完事项。
- 要求 Gemini 把普通对白改成 JSON，或强制修改现有 Provider 的输出格式。
- 自动预约、等待、改日程、改路线、移动 NPC 或为玩家分配固定陪伴时间。
- 自动创建关系事件、修改 `spouse` / `datingFarmer` 或改变亲吻逻辑。
- 游戏内实机验证、正式 Mod 部署和正式存档迁移。

当前上游 Provider 只有在响应中提供经过契约校验的顶层 `openLoop` 元数据时，才会产生或关闭事项；没有该元数据时，回复仍按普通对白处理，状态不变。这样可以避免一句普通的「以后再聊」污染故事状态，并为之后单独接入 Gemini 结构化输出留下边界清晰的接口。

## 数据契约

### 持久化记录 `OpenLoopRecord`

```json
{
  "loopId": "wizard:rune-review:Spring-14",
  "npcId": "Wizard",
  "topic": "rune_review",
  "originChannel": "remote",
  "nextChannel": "face_to_face",
  "status": "open",
  "shortSummary": "线上留下了核对符文数据的话题",
  "createdOn": "Spring 14"
}
```

字段约束如下：

| 字段 | 约束 |
| --- | --- |
| `loopId` | 非空、有限长度，由结构化信号提供；同一 NPC 下作为幂等键 |
| `npcId` | 非空，必须等于当前对话 NPC |
| `topic` | 非空、有限长度，描述事项类别而非排期 |
| `originChannel` | 只允许 `remote` |
| `nextChannel` | 只允许 `face_to_face` |
| `status` | `open`、`in_progress`、`resolved`、`cancelled` |
| `shortSummary` | 非空、有限长度，只保存当前事项摘要 |
| `createdOn` | 当前游戏日期；不是未来预约时间 |

记录不含 `time`、`location`、`scheduledAt`、`appointment`、`route` 或时间分配字段。

### Bridge 响应信号 `openLoop`

```json
{
  "action": "open",
  "loopId": "wizard:rune-review:Spring-14",
  "topic": "rune_review",
  "shortSummary": "线上留下了核对符文数据的话题"
}
```

`action` 只允许：

- `open`：仅 `remote` 回复可创建或幂等更新活动事项；需要 `loopId`、`topic` 和 `shortSummary`。
- `continue`：仅 `face_to_face` 回复可将同 NPC 的活动事项标记为 `in_progress`。
- `resolve`：仅 `face_to_face` 回复可将同 NPC 的活动事项标记为 `resolved`。

信号不接受 `npcId`、未来时间、地点或预约字段；NPC 归属由当前 C# 对话状态决定，动作渠道由当前菜单决定。

## 状态迁移

| 当前渠道 | 信号 | 前置条件 | 结果 |
| --- | --- | --- | --- |
| `remote` | `open` | 回复非 fallback 且元数据完整 | 新建 `open`；同 `npcId + loopId` 幂等更新 |
| `remote` | `continue` / `resolve` | 任意 | 忽略 |
| `face_to_face` | `continue` | 存在同 NPC 的活动事项 | 标记 `in_progress` |
| `face_to_face` | `resolve` | 存在同 NPC 的活动事项 | 标记 `resolved` |
| 任意 | 缺失、非法或不匹配信号 | 任意 | 忽略，不改变状态 |
| 任意 | fallback、空回复或生成失败 | 任意 | 不创建、不承接、不关闭 |

已 `resolved` 或 `cancelled` 的事项不会重新注入 Prompt，也不会被同一个 `loopId` 的 `open` 信号重新打开。

## 数据流与隔离

1. 远程 `ChatInputMenu` 发送 `channel=remote`。
2. Bridge 解析 Provider 返回的可选 `openLoop`；非法元数据被丢弃，回复仍可正常返回。
3. C# 只有在回复有效且未 fallback 时调用 `StoryStateStore.ApplyOpenLoopSignal`。
4. 面对面 `ChatInputMenu` 发送 `channel=face_to_face`，并从 `RelationshipSnapshotFor(npcId)` 获得该 NPC 自己的活动事项。
5. Bridge 的 Prompt 投影只包含当前 NPC 的活动事项，要求在当面回复中自然接回；关闭仍必须由匹配的 `resolve` 结构化信号完成。

`StoryStateStore`、`BridgeClient` 和 Python `relationship_world` 投影都按当前 `npcId` 过滤。一个 NPC 不能读取或关闭另一个 NPC 的事项，完整关系表和已解决事项也不进入当前 Prompt。

## 错误处理与兼容性

- `openLoops` 缺失的旧 JSON 按空数组加载，不改变 schema 版本。
- 非法 `OpenLoopRecord` 加载时跳过并写 warning；其它合法状态继续保留。
- Bridge 上游没有 `openLoop` 时返回普通 `DialogueResponse`，字段为 `null`。
- Bridge fallback 或响应守卫触发时清除 `openLoop`，防止兜底文本改变故事状态。
- 结构化信号不参与普通文本的 `reply` 校验，不把元数据错误变成玩家可见的技术对白。

## 测试策略

- C#：状态记录校验、序列化兼容、当前 NPC 隔离、信号迁移、fallback/空回复/失败边界。
- Bridge：Pydantic 字段与额外字段拒绝、Provider 顶层元数据解析、API 返回、关系投影和 Prompt 规则。
- 回归：先运行新增定向测试，再运行 SMAPI 单元全量和 Bridge pytest 全量；构建时关闭部署和压缩。
- 本地自动化结果只能证明代码契约，不替代之后的游戏内跨渠道和真实 Gemini 质量验证。
