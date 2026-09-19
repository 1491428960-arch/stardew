# “反重力反代”路线研究

日期：2026-09-08
研究问题：评估 Google Antigravity 账号通过第三方本地网关转换为 OpenAI/Gemini 兼容接口的技术路线、社区实现、账号风险，以及是否适合当前 story-memory Bridge。
研究范围：公开社区教程、开源项目 README、Google Antigravity 官方附加条款、Google AI Developers Forum 账号封禁案例，以及当前项目已有的官方 Vertex 路线。
排除项：不登录 Google 账号，不获取 OAuth 回调，不启动或安装反代，不读取任何本机凭据，不修改 Bridge 配置，不把第三方反代请求误称为官方 Gemini/Vertex 请求。

## 结论

“反重力反代”技术上可行，但不适合作为当前项目的正式 Gemini/Vertex 质量评测路线。

它的基本链路是：

```text
Antigravity/Google OAuth
        ↓
Antigravity Manager 或 CLIProxyAPI
        ↓ 读取账号会话并调用 Antigravity 内部接口
本机 OpenAI/Anthropic/Gemini 兼容端口
        ↓
story-memory Bridge
```

社区实现确实可以把 Antigravity 的 Gemini/Claude 能力暴露成类似 `/v1/chat/completions` 或 `/v1/messages` 的本地接口，并支持账号轮换、配额监控和协议转换。但这不是 Google 官方 Gemini API，也不是 Vertex AI API。

最重要的阻断是 Google Antigravity 官方条款第 6 条：使用第三方软件、工具或服务访问 Antigravity，例如“使用 OpenClaw with Antigravity OAuth”，被明确列为违反协议，可能导致 Antigravity 和 Gemini CLI 账号被暂停或终止。Google AI Developers Forum 还存在用户报告使用第三方 CLI/OAuth 后出现 `violation of Terms of Service` 禁用的案例。

因此当前项目的路线判断为：

1. 正式评测继续等待并验证官方 Vertex AI/官方 Gemini 路线；
2. 不把 Antigravity 反代接入 5678，不创建新的反代配置，不让它成为 `provider=cloud` 的伪装上游；
3. 反重力反代最多作为独立的技术研究对象，不作为当前项目的真实云端质量证据；
4. 不使用多账号轮换、共享账号、购买账号、公开公网端口或远程部署代理。

## 判断依据

### 来源事实

- [Google Antigravity Additional Terms of Service](https://antigravity.google/terms/) 明确写出：使用第三方软件、工具或服务访问 Service 是协议违反行为，示例包括使用 OpenClaw 与 Antigravity OAuth；该行为可能导致 Antigravity 和/或 Gemini CLI 账号暂停或终止。
- [Google AI Developers Forum：Antigravity account disabled - “violation of Terms of Service”](https://discuss.ai.google.dev/t/antigravity-account-disabled-violation-of-terms-of-service-requesting-support/123014) 中，多名用户描述自己使用 OpenCode、OpenClaw 或类似第三方 CLI/OAuth 后收到 403/服务因违反条款被禁用的提示。这是用户案例，不等于每次封禁的独立官方裁定，但与官方条款方向一致。
- [Deep Router：Antigravity 反向代理指南](https://deeprouter.org/article/antigravity-reverse-proxy-guide) 公开了两种社区路线：带 GUI 的 Antigravity Manager，以及配置文件驱动的 CLIProxyAPI；教程将本地端口、OAuth 登录和第三方客户端配置写成完整步骤。它是第三方教程，不是 Google 官方支持文档。
- [Antigravity-Manager](https://github.com/lbjlaq/Antigravity-Manager) README 宣称提供 OAuth 账号管理、OpenAI/Anthropic/Gemini 协议接口、配额监控、重试和账号调度；其定位是本地 AI 中转站，而非 Google 官方 API 客户端。
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) README 宣称可以将 Antigravity 等 CLI 账号通过本地服务提供 OpenAI/Gemini/Claude/Codex 兼容接口，并支持多个 CLI 账号。它同样是第三方代理层。
- [frieser/antigravity-proxy](https://github.com/frieser/antigravity-proxy) README 直接描述其通过 Google “internal Gemini and Claude APIs” 转换为 OpenAI 兼容接口，并包含账号轮换、健康评分、429 冷却和本地 `antigravity-accounts.json` 凭据文件。这证明了技术路线的形态，也暴露了凭据、账号轮换和内部协议依赖风险。

### 技术观察

| 路线 | 上游身份 | 本地接口 | 对当前项目的含义 | 判断 |
|---|---|---|---|---|
| 官方 Vertex AI | Google Cloud project + ADC/OAuth | 官方 Vertex/兼容接口 | 可记录 provider、usage、延迟和真实错误；符合当前验收口径 | 推荐 |
| Antigravity Manager | Antigravity OAuth 会话 | 常见为本机 OpenAI/Anthropic/Gemini 兼容端口 | 只是第三方本地网关；模型名、usage 和错误语义不等于 Vertex | 不接入正式评测 |
| CLIProxyAPI | Antigravity/其他 CLI OAuth | 本机兼容接口 | 配置灵活，但凭据与内部协议风险更高；多账号功能不应使用 | 不接入 |
| 远程自建反代 | 本地 OAuth 凭据被带到远程主机 | 公网 HTTPS | 扩大密钥暴露面、增加外部服务和账号封禁风险 | 排除 |
| 购买共享账号/共享中转 | 他人付款主体或共享会话 | 外部服务或本地转发 | 无法证明授权、资料归属和请求隐私 | 排除 |

### 与 `gemini-3.7-flash` 的关系

社区项目 README 展示的模型名主要是 Antigravity 自己的模型池命名，例如 Gemini 3/3.1/3.5、Claude 和 sandbox pool 模型。没有证据证明这些模型 ID 等价于官方 `gemini-3.7-flash`，也没有证据证明它们返回官方 Gemini API 的 `usage`、安全字段或模型版本语义。

因此，即使反代返回 HTTP 200，也只能证明“某个第三方网关返回了内容”，不能证明：

- 请求到达了官方 Vertex AI；
- 使用的模型就是 `gemini-3.7-flash`；
- 计费、配额和延迟指标属于 Vertex；
- 返回结构和官方 OpenAI-compatible Gemini API 完全兼容；
- 账号没有触发 Antigravity 条款风险。

## 来源

- [Google Antigravity Additional Terms of Service](https://antigravity.google/terms/) —— 第 6 条关于第三方软件/工具/服务访问和账号暂停/终止的明确条款。
- [Google AI Developers Forum: Antigravity account disabled](https://discuss.ai.google.dev/t/antigravity-account-disabled-violation-of-terms-of-service-requesting-support/123014) —— 第三方 CLI/OAuth 使用后的用户禁用报告。
- [Deep Router: Antigravity 反向代理指南](https://deeprouter.org/article/antigravity-reverse-proxy-guide) —— Antigravity Manager 和 CLIProxyAPI 的完整社区流程与端口配置示例。
- [lbjlaq/Antigravity-Manager](https://github.com/lbjlaq/Antigravity-Manager) —— GUI、本地协议转换、OAuth、配额和账号管理功能说明。
- [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) —— CLIProxyAPI 的兼容协议和 Antigravity 账号接入说明。
- [frieser/antigravity-proxy](https://github.com/frieser/antigravity-proxy) —— 内部 Gemini/Claude 接口转换、账号轮换和本地凭据文件说明。
- 当前项目 [docs/active-work.md](E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/docs/active-work.md) —— 已有 Bridge/官方云端验收边界、`provider` 证据要求和“不把健康检查当成模型成功”的项目记录。

## 证据

- 直接抓取 Google 官方条款页面，条款正文包含：`Using third party software, tools, or services to access the Service ... is a breach of this Agreement`，并说明可能暂停或终止 Antigravity/Gemini CLI 账号。
- 直接读取 Google AI Developers Forum 公开帖子，原帖用户报告错误文案：`This service has been disabled in this account for violation of Terms of Service`，并明确提到此前使用第三方 CLI 与 Antigravity OAuth。
- 直接读取 Deep Router 社区教程，核对到的本地配置示例包括 `http://127.0.0.1:8045/v1`、OAuth 登录、API Key、协议模式和 `./cli-proxy-api --antigravity-login`；这些是社区项目自己的端口和配置，不是当前项目的配置。
- 直接读取 GitHub README，核对到 Antigravity Manager、CLIProxyAPI 和 antigravity-proxy 都把自己描述为本地代理/协议转换层，并且至少一个实现将 OAuth 账号凭据保存为本地 JSON 文件。
- 本轮没有启动这些第三方代理，没有获取 OAuth，没有向 Antigravity 发请求，没有改写 `BRIDGE_CLOUD_URL`，没有启动/重载 5678，也没有对当前评测工件产生请求。

## 建议

1. 当前项目继续保持官方路线：等账号侧解决 Billing/Vertex 资格后，再按已有流程做最小真实请求，要求 `provider=vertex` 或项目约定的官方 provider、`fallback=false`、非空内容、正确 `usage` 和可解释延迟。
2. 如果只是研究反代架构，可在项目外做静态阅读或独立沙盒实验；不要把 Antigravity OAuth 凭据、`antigravity-accounts.json`、CLIProxyAPI 配置或任何回调 URL 放进当前工作树。
3. 不使用账号轮换、共享账号、购买账号、公开公网监听和第三方远程中转。即使本地监听在 `127.0.0.1`，上游仍然是受条款约束的第三方访问方式。
4. 不把反代返回的模型名称改写成 `gemini-3.7-flash`，不把反代请求标记为 `provider=cloud`，不把 `/health=200` 或本地 OpenAI 兼容响应当作官方 Gemini/Vertex 证据。
5. 真正需要稳定生产/质量评测时，优先解决官方 Vertex 付款主体与服务资格；如果官方路线不可用，应明确选择一个有授权、条款允许、可审计的官方 API/云服务，而不是把 Antigravity 内部接口当成 API 产品。

## 限制

- 社区项目更新非常快，版本、端口、模型名和 OAuth 流程可能随时变化；本报告只记录 2026-09-08 访问到的公开内容。
- 没有执行第三方代理，无法证明任何具体账号、端口、模型或请求在当前网络环境中可用；也没有把社区 README 的宣传性描述当成实测成功。
- Google 条款明确针对 Antigravity Service；本报告不把它扩展解释为所有 Google Cloud/Vertex AI 使用方式都禁止第三方客户端。Gemini Enterprise/Google Cloud 条款是否适用，要看实际产品和管理员接受的条款。
- Google AI Developers Forum 的封禁帖子是用户报告，不足以独立证明每个案例的完整因果链；但它与官方条款中的风险方向一致。
- 本轮没有修改 Bridge、Provider、`.env.local` 或现有评测工件，也没有创建 Git commit。
