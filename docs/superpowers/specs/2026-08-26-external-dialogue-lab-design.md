# 外部 NPC 对话实验室设计

日期：2026-08-26  
状态：已获用户确认，待实现前复核

## 目标

在本机 Bridge 上提供一个浏览器对话实验室，用来在不启动星露谷的情况下评估 NPC 的角色一致性、上下文承接和 Provider 表现。第一版优先复用现有 `/api/dialogue/test`、`/api/context/preview` 和 `/api/npcs`，不新增公网服务，不改变游戏内聊天流程。

## 用户场景

1. 选择 `Wizard` / `Rasmodia` 等已有 NPC，修改关系阶段、日期、天气、地点和好感度。
2. 连续发送多轮消息，看到完整的玩家/NPC transcript，并观察回复是否承接历史。
3. 在自动路由、Fake 演示和本地模型之间切换（没有上游配置时自动模式安全回退）。
4. 看到本轮 Provider、延迟、fallback 和警告；需要时展开当前上下文摘要，确认资料是否进入请求。
5. 清空当前会话或导出 JSON，便于人工比较和后续评测；会话可在刷新或重启 Bridge 后恢复，但默认不写入存档、不上传数据。

## 方案边界

- 页面继续挂在 Bridge 的 `GET /test`，与 `127.0.0.1:5678` 同源，避免 CORS 和额外服务进程。
- 会话通过同源 Bridge API 保存到本机 JSON 文件，默认路径为 `%TEMP%\\StardewAI.NPC\\dialogue-lab-session.json`，可由 `BRIDGE_DIALOGUE_SESSION_PATH` 覆盖；仅持久化 `version`、`messages`、`history` 和脱敏后的 `lastDiagnostics`。不使用浏览器 `localStorage`，不写游戏存档，也不保存 API key、Token、完整 prompt、`lastPayload` 或其他敏感请求内容。
- 页面初始化先调用 `loadSession()` 再进行初始渲染；成功回复后调用 `saveSession()`；`clearSession()` 调用本地 API 删除保存的会话。版本不匹配、损坏 JSON 或本地 API 暂不可用时恢复为空会话，不阻塞页面加载；损坏文件由 Bridge 备份为 `.corrupt*`。
- “自动”模式通过省略 `provider` 字段触发现有本地→云端→fallback 路由；“Fake 演示”才显式发送 `provider: "fake"`。界面不把 Fake 描述成真实 AI。
- 场景编辑只生成现有 `NpcGameState` 支持的字段。关系阶段用合法的 `friendshipHearts`、`relationship`、`marriageStatus`、`childrenCount` 组合映射，不向请求注入未知字段。
- 仍遵守 Bridge 的请求校验、上下文脱敏和回复 guard；前端不接触 API key、Cookie 或绝对路径。

## 页面布局

采用宽屏三栏布局；内置浏览器的窄窗口也保持紧凑三栏，避免快捷角色按钮被纵向布局压出可视区：

- 顶栏：工具名、Bridge 健康状态、当前 Provider、清空会话、导出会话。
- 左栏“场景”：NPC、来源 Mod、关系阶段、日期/季节、天气、时间、地点、好感度；提供“恢复 Rasmodia 默认场景”。
- 中栏“对话”：可滚动完整 transcript；用户消息和 NPC 消息视觉区分；底部多行输入框、发送按钮、主动找话题按钮；请求期间保留输入内容并禁用重复发送。
- 右栏“诊断”：最近一轮的 Provider/延迟/fallback/警告、上下文摘要折叠区和可选原始请求预览（仅显示已脱敏字段）。

默认配色使用低饱和的暖色和高对比文字，信息卡与对话区明确分层；不复刻游戏像素素材，避免把测试工具误认为游戏 UI。

## 前端状态

```text
session = {
  npcId,
  displayName,
  sourceMods[],
  gameState,
  messages: [{ role: "user"|"npc", text, createdAt }],
  history: [{ role, content, name? }],
  lastDiagnostics,
}
```

- 页面加载时调用 `/api/npcs` 填充 NPC；默认选 `Rasmodia`（不存在时回退第一个）。
- 每次发送将当前输入加入请求的 `history`（最多 50 条），收到回复后再加入 `messages/history`。
- 会话恢复只来自 Bridge 的本机 JSON API，不会把本地保存的 `lastPayload` 或敏感请求字段重新带回页面。
- 请求失败时不丢弃用户输入，并在诊断区显示可读错误；不会伪造 NPC 回复。
- Enter 发送，Shift+Enter 换行；鼠标和键盘都能操作。

## 请求映射

普通聊天请求：

```json
{
  "npcId": "Rasmodia",
  "displayName": "Rasmodia",
  "sourceMods": ["Romanceable Rasmodius", "SVE"],
  "message": "你好，今天过得怎么样？",
  "history": [],
  "gameState": {
    "season": "春",
    "date": "春 1 日",
    "weather": "晴天",
    "time": 800,
    "location": "法师塔",
    "friendshipHearts": 6,
    "relationship": "朋友"
  }
}
```

主动找话题复用同一接口，仅把 `intent` 设为 `topic`，`message` 使用固定的本地提示。回复仍走同一 guard 和 fallback 链路。

## 可观测性

- 健康状态从 `/health` 获取，页面显示 `provider` 和不可用状态。
- 每轮显示返回的 `provider`、`latencyMs`、`fallback` 和 warnings。
- 上下文摘要通过 `/api/context/preview` 请求生成，只呈现 NPC 身份、关系阶段、已选来源、事实数量、风格证据数量和故事事件数量；不展示敏感字段和本机绝对路径。
- 原始请求预览默认关闭，打开时也只显示前端实际构造且已经过本地脱敏的 JSON。

## 测试策略（先测试后实现）

1. API 页面契约测试：`GET /test` 包含三栏容器、连续记录、场景字段、诊断字段、发送/找话题/导出/清空控件；不再出现“发送 Fake 对话”作为唯一入口。
2. 前端静态契约测试：页面脚本包含 `/api/npcs`、`/api/dialogue/test`、`/api/context/preview`、`history`、`gameState`、自动/Fake 模式切换和失败保留输入逻辑。
3. 回归现有 Bridge API、Provider、上下文脱敏和全部 Python 测试。
4. 运行本机 Bridge 后，用 HTTP 客户端实际请求 `/health`、`/test`、`/api/npcs` 和至少一轮 `/api/dialogue/test`，确认页面与接口同源可用。
5. 用浏览器打开 `/test` 做一次视觉检查：宽屏三栏、长对话滚动、中文输入、错误状态和诊断信息可读。
6. 在同一浏览器中发送多轮消息并刷新页面，确认消息和诊断恢复；重启 Bridge 后再次确认会话仍在；点击清空后刷新，确认本地会话被删除；向本地会话文件写入损坏 JSON 时页面仍能加载，Bridge 会备份损坏文件并恢复空会话。

## 明确不做

- 不在此工具里替代 F8 游戏内入口。
- 不把 FakeProvider 改成真实模型，也不隐藏“本地演示·非真实 AI”标记。
- 不新增远程部署、账号系统或自动上传。
- 不在第一版加入复杂的资料编辑器、向量数据库或全量评测报表；先把可反复手测对话质量的闭环做稳。
