# Qoder会员与Stardew AI NPC项目接入评估

日期：2026-09-01
研究问题：阿里云渠道获得的 Qoder 一个月会员，能否用于本项目的开发、测试例生成和 Bridge NPC 实时对话链路？
研究范围：公开官方资料、当前工作树 Provider 实现和实时 Bridge 健康状态；不访问账户私密页面，不读取或记录任何 Token、Cookie、API Key。

## 结论

1. **可以用来推进项目开发，但它首先是 Qoder 的 IDE/CLI/Agent/Quest 会员权益。** 最适合用于审查本项目、补测试、修改 Prompt/资料库和运行验证。
2. **不能把 Qoder 会员直接当成百炼 API 余额。** 当前 Bridge 使用的是百炼 OpenAI-compatible endpoint 和 `qwen-plus-character`；Qoder 会员 Credits 不会自动抵扣这条 DashScope 账单。
3. **Qoder 支持在 Qoder 内配置百炼 API Key，但该用量由百炼账户直接结算，不消耗 Qoder Credits。** 这能让 Qoder 调用百炼模型，但不能让 Bridge 获得 Qoder 会员额度。
4. **Qoder Cloud Agents 是理论上的另一条接入路径，但不是当前 Bridge 的直接替换。** 它要求 PAT/SAT、Agent、Environment、Session 和事件流，接口形态不是 `/v1/chat/completions`；为游戏实时 NPC 对话专门接入它，复杂度、延迟和凭证管理成本都不划算。
5. **推荐方案：会员用于代码工程与离线评测辅助，Bridge 继续使用百炼 Qwen；暂不开发 Qoder 适配器。** 如果账户的 Usage 页面确实显示 Qwen3.8-Max 活动次数，可以在 Qoder 端用于额外的高质量开发/评审试验，但不把结果自动写入角色资料库或当作运行时默认模型。

## 判断依据

### 来源事实

- Qoder 个人方案按月订阅并使用 Credits 计量；官方页面列出 Pro、Pro+、Ultra，以及各自的月度 Credits。Credits 用于 Editor、Ask/Agent、Quest、Repo Wiki 等 Qoder 功能。
- Qoder 自定义模型文档明确列出阿里云百炼等第三方供应商，并明确说明：自定义模型费用由供应商 API 账户直接结算，不占用 Qoder Credits。
- Qoder Cloud Agents 文档把 Agent、Environment、Session、Event 作为独立概念，并要求 PAT 或 SAT；Cloud Agents 个人模式使用预付 Credits，企业模式使用服务账号和单独计费。
- Qoder 官方活动页写明 Qwen3.8-Max 活动权益可覆盖 Qoder IDE、CLI、Cloud Agents 等产品，但活动资格、领取入口和有效期以账户实际 Usage 页面为准，不能由“一张一个月会员券”直接推导。

### 项目代码观察

- `bridge/src/stardew_ai_bridge/config.py` 从 `BRIDGE_CLOUD_URL`、`BRIDGE_CLOUD_MODEL`、`BRIDGE_CLOUD_API_KEY` 等配置读取云端 Provider；`api_key` 只存在进程配置对象中，不写入本报告。
- `bridge/src/stardew_ai_bridge/providers.py` 的云端实现向配置的 URL 发送 OpenAI-compatible Chat Completions 请求，并解析 `choices[0].message.content` 与 usage。
- 当前实时 `5678/health` 返回 `{"status":"ok","provider":"cloud"}`；本机配置类型核对为 DashScope Chat Completions URL、模型 `qwen-plus-character`，API Key 已配置但未读取其内容。

## 来源

- [Qoder 个人方案与 Credits](https://docs.qoder.com/zh/account/pricing)：方案、月度 Credits、试用和资源包规则。
- [Qoder Credits 说明](https://docs.qoder.com/zh/Credits)：Credits 的消耗项、典型消耗和用量查看方式。
- [Qoder 自定义模型](https://docs.qoder.com/zh/qoder/custom-models)：第三方模型接入范围及“由供应商 API 账户直接结算”的说明。
- [Qoder Cloud Agents 概览](https://docs.qoder.cn/cloud-agents/overview)：Agent/Environment/Session/Event 工作流和认证入口。
- [Qoder Cloud Agents 快速入门](https://docs.qoder.cn/cloud-agents/quickstart)：创建 Environment、Agent、Session 和发送事件的接口流程。
- [Qoder Cloud Agents CN 计费](https://docs.qoder.cn/cloud-agents/billing)：个人预付 Credits、企业服务账号和沙箱计费边界。
- [Qoder Qwen3.8-Max 活动说明](https://docs.qoder.com/zh/events/qwen-max)：活动次数、适用产品、领取方式和有效期说明；这是公开活动条款，不是对本账户券状态的确认。
- [阿里云百炼 OpenAI 兼容调用说明](https://help.aliyun.com/zh/model-studio/developer-reference/compatibility-of-openai-with-dashscope)：百炼 Chat Completions endpoint、Bearer API Key 和 usage 返回结构。
- [当前项目配置](E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/src/stardew_ai_bridge/config.py)：Bridge 云端配置字段。
- [当前项目 Provider](E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/src/stardew_ai_bridge/providers.py)：OpenAI-compatible 请求实现。

## 证据

- 公开 Qoder 资料于 2026-09-01 重新读取；关键页面均为 Qoder/Qoder CN 或阿里云官方域名。
- 当前工作树只读核对到：`BRIDGE_CLOUD_URL` 为 DashScope `/compatible-mode/v1/chat/completions`，`BRIDGE_CLOUD_MODEL=qwen-plus-character`，API Key 只确认“已配置”而未读取值。
- 实时检查：`GET http://127.0.0.1:5678/health` 返回 `{"status":"ok","provider":"cloud"}`。
- 本次没有调用 Qoder 账户 API、没有创建 Agent/Session、没有向 Qoder 发送项目资料，也没有发起新的付费模型请求。

## 建议

1. 登录 Qoder 后只查看 **Settings → Usage**，确认券实际落成的是哪个方案、剩余 Credits，以及是否有 Qwen3.8-Max 活动次数；不要把页面截图、Cookie 或令牌发给我。
2. 先用会员在 Qoder 中打开当前 `story-memory` 工作树，让它做只读代码审查、测试覆盖检查和离线评测设计；任务提示中要求先读项目 `AGENTS.md` 和 `docs/active-work.md`，保留现有未提交修改。
3. 需要生成 NPC 实际回复时，继续在当前 Dialogue Lab 里使用显式“云端（当前配置）”的百炼 Qwen，并保留每批用量和结果工件；Qoder 里的回复只作为独立对照，不自动混入资料库。
4. 只有当 Qoder 账户明确显示 Cloud Agents 可用额度，并且未来需要批量异步 Agent 任务时，才评估增加独立 Qoder adapter；该 adapter 应与现有实时 Provider 分开，先做契约测试和成本/延迟小样本。

## 限制

- 无法从公开页面确认用户这张具体券的兑换结果、方案档位、剩余 Credits 或活动资格；这些属于账户私密状态。
- Qoder 活动页的条款可能调整，且不同站点/版本可能有差异；当前日期距该页列出的部分活动截止时间很近，应以账户 Usage 面板和端内提示为准。
- 没有实际创建 Qoder PAT、Cloud Agent 或发起 Cloud Agents 请求，因此没有宣称该账户已经具备可用的 Cloud Agents API 权限。
- 本报告只评估接入可行性，没有改变 Bridge Provider、模型默认值、游戏 DLL 或游戏存档。
