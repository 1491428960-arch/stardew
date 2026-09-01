# 多轮角色质量评测设计

## 目标

把五个代表角色的固定质量评测从“每个案例一次请求”升级为“每个案例三轮连续对话”，让后续请求携带前面实际生成的玩家/NPC消息，并在测试例浏览页展示完整 transcript、每轮评分、延迟和真实 API 用量。

本轮只改游戏外 Bridge 评测与浏览器展示，不修改 SMAPI 游戏内历史持久化，不改变 `/test/chat` 的单次手动聊天语义。

## 方案

### 1. 评测数据结构

新增不可变的 `CharacterQualityTurn`，包含 `turnId`、`message`、`expectedTerms`、`forbiddenTerms` 和人工复核用的 `evaluationFocus`。`CharacterQualityCase` 保留现有 `message`、`history`、期望词字段作为旧接口兼容，并通过 `dialogue_turns()` 为没有显式 turns 的旧案例生成单轮。

默认 15 个案例各定义 3 个 turn。第一轮使用案例预置 history；第二、三轮把前面每轮实际发送的玩家输入和实际 NPC 回复追加到请求消息中。每个 turn 独立评分，案例结果同时保存轮次列表与汇总信息。

### 2. Provider 用量

`ProviderResult` 增加可选的 `usage`，字段为 `inputTokens`、`outputTokens`、`totalTokens`。OpenAI-compatible Provider 读取 API 返回的 `usage.prompt_tokens`、`completion_tokens`、`total_tokens`；兼容接受已经是 `input_tokens`/`output_tokens` 的网关字段。Ollama 在没有标准 usage 时读取其明确返回的 `prompt_eval_count`、`eval_count`，无法取得时保留 `usage=null`，不以字符数猜测 token。

### 3. 脱敏工件与成本

结果工件升级为 schema version 2，保存每轮的玩家输入、NPC 回复、Provider、fallback、延迟、warnings、usage 和评分，不保存完整 prompt、API key、Token 或原始 request payload。summary 汇总请求数、成功轮数、通过轮数、延迟和 token；输入/输出单价通过 CLI 或环境变量配置，未配置单价时保留 token 统计并明确费用未配置。

读取器同时支持旧的单轮结果，把它包装为一轮以便浏览器继续查看历史批次。

### 4. 浏览器展示

测试例浏览页的列表显示三轮、成功轮数和 Provider。详情页将预置 history 与每一轮按顺序展示为完整 transcript，每轮显示玩家话语、NPC 回复、Provider、延迟、token 和评分标签；右侧增加案例级请求数、总 token、用量返回情况和费用估算。展示内容全部来自脱敏案例目录/结果接口，不展示 prompt 或凭据。

页面保持当前三栏工作区和 `/test/chat` 独立路径；初始化无结果、旧单轮结果、某一轮失败和 usage 缺失都必须有明确状态，不阻塞其他轮次展示。

## 数据流

```text
固定案例 + 预置 history
        ↓
turn 1: prompt builder → Provider → reply + usage
        ↓ 追加真实 user/reply
turn 2: prompt builder → Provider → reply + usage
        ↓ 追加真实 user/reply
turn 3: prompt builder → Provider → reply + usage
        ↓
脱敏 results.jsonl + summary.json
        ↓
/api/quality/results → 测试例浏览器完整 transcript
```

## 错误处理与安全边界

- 单轮 Provider 异常只标记该轮失败，继续执行后续轮次时使用已经成功生成的上下文；若当前轮失败，不伪造 NPC 回复，后续轮次从已有真实上下文继续或明确标记无法连续。
- 格式噪声重试计入请求数和 usage，但只保留最终结果与累计用量，避免把内部 prompt 暴露给浏览器。
- usage 字段只接受非负整数；非法值按缺失处理。
- 成本只有在输入/输出单价均为非负数且已配置时计算；币种和单价写入 summary，默认不假定价格。
- 仍由 `sanitize_quality_artifact` 处理所有落盘内容，并新增测试确认敏感字段不会出现在工件和 HTTP 响应中。

## 验证范围

- Python 单元测试：三轮结构、顺序调用、真实上下文承接、Provider usage 解析、结果汇总、旧工件兼容、脱敏。
- 页面契约测试：多轮 transcript、每轮 usage/费用、案例级汇总、无 prompt/key/token。
- 完整 Bridge 回归测试。
- 使用当前百炼 Qwen 配置运行 15 × 3 轮新工件，核对 45 次请求的成功/fallback/provider、每轮和总 token。
- 检查运行中的 5678 `/health` 和 `/test`，并在浏览器中确认新批次的多轮 transcript 可见。此轮不宣称游戏或 DLL 已验证。
