# Google 官方 Gemini API 区域限制与 Vertex AI 路线研究

日期：2026-09-07
研究目标：解释当前 `gemini-3.7-flash` 官方请求为何返回区域错误，并确定在不使用旧 OpenAI 地址、不使用中转站的前提下，怎样恢复 Bridge 的真实云端请求和质量评测。
研究范围：Google 官方 Gemini API / Google Cloud Vertex AI 文档、当前项目 Bridge 配置与 Provider 实现、已完成的本地回归和一次官方最小请求。
排除项：不登录 Google 账号、不创建 Cloud 项目、不启用计费、不读取或展示任何密钥，不启动 Stardew Valley/SMAPI，不运行批量质量评测。

## 结论

1. 当前阻塞点已经定位到 Google 官方服务的区域/请求来源条件。使用新 Key 后，官方 endpoint 返回的是 `HTTP 400`、`FAILED_PRECONDITION`、`User location is not supported for the API use.`；这说明请求已经到达 Google 并被识别为该 API 的请求，不是 Bridge 的 `/health`、URL 拼接、`choices` 解析或模型回复格式问题。
2. 继续更换 Gemini API key、重试、增大超时、修改 Prompt 或运行批量评测，都不能解决这个错误。Google 官方支持区域页还说明：如果当前不在列出的国家/地区，应尝试 Gemini Enterprise Agent Platform（原 Vertex AI）路线；不能把换 Key 当作区域授权修复。
3. 推荐的正式解决路线是先评估 Vertex AI 的官方 OpenAI-compatible endpoint。它支持 Chat Completions 和 streaming，官方文档列出了 `Gemini 3.7 Flash`；但它不是“把 URL 换一下”就能完成：需要 Google Cloud project、启用 billing、启用 Agent Platform API，并使用 Google Cloud Auth/ADC 取得 OAuth access token。当前 Bridge 只支持从 `BRIDGE_CLOUD_API_KEY` 读取静态 Bearer 凭据，因此需要一次小范围的认证适配后才能接入。
4. 在 Vertex 账号、项目和认证条件准备好并通过最小真实请求之前，不能继续 5 案例/15 轮冒烟，也不能运行五套完整评测。现有测试通过和 `/health=200` 只证明 Bridge 本地链路正常，不能证明 Gemini 成功。

## 已验证的本地事实

### 配置与回归

- 当前工作树为 `codex/story-memory`，原有未提交修改已保留；本报告是本轮新增文件，没有重置、清理、删除或提交。
- 根目录 `.env.local` 中已完成脱敏核验：`BRIDGE_CLOUD_API_KEY` 非空，长度 `53`；没有输出实际内容。`BRIDGE_CLOUD_MODEL=gemini-3.7-flash`、`BRIDGE_CLOUD_ENABLED=true`、`BRIDGE_CLOUD_ONLY=true`、`BRIDGE_CLOUD_TIMEOUT=45` 均有效，URL 使用 Google 官方 OpenAI-compatible endpoint。
- 使用项目规定的 Python 3.10 完成 Bridge 全量回归：`1130 passed in 19.40s`。
- Bridge 重载期间确认 5678 的监听进程命令行指向本工作树；`/health` 返回 `status=ok, provider=cloud`，关系案例接口返回 `20` 个案例，首个案例为 `3` 轮。该进程随后已停止。

证据文件：

- [项目活动记录](active-work.md)
- [Bridge 配置](../bridge/src/stardew_ai_bridge/config.py)
- [Bridge Provider 实现](../bridge/src/stardew_ai_bridge/providers.py)
- [Bridge 测试目录](../bridge/tests/)

### 官方请求与 Bridge 请求的区别

一次通过当前 Bridge 的最小真实请求返回了 HTTP 层的成功响应，但结果是：

```text
provider=fallback
fallback=true
usage=null
```

这不是 Gemini 成功证据。随后使用同一份脱敏后的 URL、模型和 Key 对 Google 官方 endpoint 做了最小直连诊断，实际结果为：

```text
HTTP 400
status=FAILED_PRECONDITION
message=User location is not supported for the API use.
```

响应没有 `choices[0].message.content`，也没有可用 `usage`。因此 Bridge 的 fallback 是对上游失败的安全处理，而不是云端回复。

## 官方事实

### 1. Gemini API / AI Studio 有地区列表

Google 官方页面 [Available regions for Google AI Studio and Gemini API](https://ai.google.dev/gemini-api/docs/available-regions) 写明：

- 页面列出 Gemini API 和 Google AI Studio 可用的国家和地区；
- 页面明确说，如果不在这些国家或地区，应尝试 Gemini Enterprise Agent Platform；
- 页面还特别说明，Colab 的限制按 Colab 实例所在地区判断，而不是按用户所在地区判断。这说明请求来源/出口位置是实际判定因素之一。

本次按页面当前可见的支持列表解析到 `222` 个条目。列表中可见 `Japan`、`Singapore`、`South Korea`、`Taiwan`、`United Kingdom` 和 `United States`；没有找到 `China`、`Hong Kong`、`Macao` 或 `Macau`。这里的“没有找到”是对 2026-09-07 页面内容的当前记录，不把它扩大解释成 Google 对所有网络路径、账号类型或 Cloud 产品的永久结论。

官方页面还列出其他可能原因，例如年龄和账号验证；但本项目已经得到明确的 `User location is not supported for the API use.`，因此当前首要问题仍是区域/请求来源，而不是继续猜测年龄或 Prompt。

### 2. Google 官方 OpenAI-compatible Gemini API

Google 官方 [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai) 页面给出的 AI Studio/Gemini API 兼容入口是：

```text
https://generativelanguage.googleapis.com/v1beta/openai/
```

Chat Completions endpoint 是该 base URL 下的 `chat/completions`。页面说明使用 Gemini API key 作为 Bearer 凭据，并支持 OpenAI-compatible Chat Completions 和 streaming。当前项目使用的 URL 形状和模型名与这条官方路线一致；新 Key 产生的错误已经从旧 Key 的 `INVALID_ARGUMENT / Please pass a valid API key` 变为区域限制，因此“Key 未被读取”不再是当前主因。

### 3. Vertex AI 的官方位置与 `gemini-3.7-flash`

Google Cloud 官方 [Vertex AI locations](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations) 页面说明：

- Vertex 提供 regional endpoint 和 global endpoint；global endpoint 用于提高整体可用性和可靠性；
- global endpoint 不保证数据驻留，也不能控制请求实际在哪个区域处理；
- 页面当前的 global 模型表中包含 `Gemini 3.7 Flash`，模型 ID 为 `gemini-3.7-flash`；
- 页面当前的区域表中也列出包括 Hong Kong、Taiwan、Tokyo、Seoul、Singapore 等位置，但“存在 Cloud 区域”不等于某个用户或项目已经获得使用授权，也不等于可以绕过 Gemini API 的区域政策。

因此，Vertex 是官方产品路线，但不能仅凭出现了某个区域就断言当前账号一定能调用成功；仍需真实项目和认证下做一次最小验证。

### 4. Vertex AI 的认证、项目和计费前置条件

Google Cloud 官方 [Configure application default credentials](https://cloud.google.com/vertex-ai/generative-ai/docs/start/gcp-auth) 页面写明：

- 可使用 Google Cloud API key 或 Application Default Credentials（ADC）；
- 官方建议 API key 用于测试，生产使用 ADC；
- 开始前需要选择或创建 Google Cloud project、确认 billing 已启用、启用 Agent Platform API，并安装/登录 gcloud CLI；
- 本地 shell 可用 `gcloud auth application-default login` 创建本地用户 ADC。

本项目当前不具备在本轮自动完成这些账号/Cloud 侧步骤的授权：它们会改变外部账号或计费状态，且本任务明确限制在项目工作树和 localhost。报告只记录官方要求，不执行这些操作。

### 5. Vertex AI 的 OpenAI-compatible endpoint

Google Cloud 官方 [OpenAI compatibility](https://cloud.google.com/vertex-ai/generative-ai/docs/start/openai) 页面说明：

- Gemini models 可以通过 OpenAI libraries 和 REST API 访问；
- 使用 OpenAI library 的 Vertex 路线只支持 Google Cloud Auth；
- 官方示例通过 ADC 刷新 `cloud-platform` scope 的 access token，然后把 token 放入 `api_key`；
- base URL 形状为：

```text
https://aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/openapi
```

- 官方示例模型写成 `google/gemini-3.5-flash`，并展示 `chat.completions.create(...)` 和 `stream=True`；
- 对本项目的 `gemini-3.7-flash`，使用 `google/gemini-3.7-flash` 是基于 Vertex 官方模型表和该页面命名规则的合理推断，必须在准备好的 Cloud project 中用一次最小请求确认，不能只凭字符串拼接视为已验证。

## 社区经验与可复用结论

以下是公开社区、GitHub issue 和 Stack Overflow 的经验汇总。它们不是 Google 的正式保证；我只把有明确复现条件的内容作为诊断线索，不把社区回复中的代理/绕过教程当作本项目方案。

### 1. 出口 IP、VPS 归属和 IPv6 可能造成误判

- Google AI Developers Forum 的 [172717 讨论](https://discuss.ai.google.dev/t/gemini-api-suddenly-returns-user-location-is-not-supported-after-enabling-billing-and-ai-studio-cannot-list-projects/172717) 中，用户报告美国 VPN/VPS IP 显示为洛杉矶，但 Gemini API 和 AI Studio 在一段时间后同时出现区域错误；回复建议检查 IP、换网络或 IP、切换 IPv4/IPv6，并通过 Google 的 [Report IP problems](https://support.google.com/websearch/workflow/9308722) 反馈。
- `googleapis/python-genai` 的 [Issue #693](https://github.com/googleapis/python-genai/issues/693) 中，同一国家的本机请求成功、Hetzner/Docker 服务失败；后续评论把问题缩小到 SDK 使用 IPv6 与 Docker 默认 IPv6 配置的差异，同时指出关闭服务器出站 IPv6 后也可能仍失败。这个案例说明 IPv4/IPv6 和服务商网段值得检查，但没有证明某个固定切换一定有效。
- `babaohuang/GeminiProChat` 的 [Issue #162](https://github.com/babaohuang/GeminiProChat/issues/162) 记录了“美国服务器开始能用、后来突然不能用”的现象，讨论没有形成稳定修复，反而支持 IP 分类或上游策略可能随时间变化的判断。

**可复用判断：** 如果一个账号在官方支持地区、同一个 API key 在另一条合规网络上能成功，而当前出口失败，那么“换出口 IP / 修正 IPv6 路径 / 提交 IP 归属反馈”值得做一次受控 A/B；如果实际所在地或请求出口本来不在支持范围内，这些动作不是合规的解决方案，也不应通过代理伪装位置。

### 2. “网页能用”不等于 API endpoint 能用

`google-antigravity/antigravity-cli` 的 [Issue #219](https://github.com/google-antigravity/antigravity-cli/issues/219) 报告了同一个 Google 账号、同一网络可以使用 Gemini 网页端，但 CLI 的 Gemini 请求仍返回同样的 `FAILED_PRECONDITION`。后续报告还对比了 Mac 与 VPS、不同网络路径，显示相同账号/模型在不同出口上的结果可能不同。

**可复用判断：** 买一个“网页能用”的账号不能证明 AI Studio API 或当前 Bridge endpoint 可用；网页、Gemini API、Vertex、CLI/Cloud Code 可能采用不同的后端资格和 IP 评估。当前项目应该以官方 endpoint 的最小真实请求为唯一验收证据。

### 3. Vertex regional endpoint 是社区反复提到的正式替代方向

- Stack Overflow 的 [77659552](https://stackoverflow.com/questions/77659552/google-generative-ai-api-error-user-location-is-not-supported-for-the-api-use) 中，原提问者最终确认自己的国家不在官方支持列表；回答建议检查 available regions，其他回答建议迁移到可指定 location 的 Vertex AI。
- `galaxyproject/loom` 的 [Issue #184](https://github.com/galaxyproject/loom/issues/184) 将同类错误归纳为消费级 Generative Language API 的地区限制，并把 Vertex regional endpoint 作为替代方向；该 issue 没有证明某个具体 Cloud 项目已经成功。
- Stack Overflow 的 [78488514](https://stackoverflow.com/questions/78488514/user-location-is-not-supported-for-the-api-use-without-a-billing-account-linked) 里有 2024 年关于某些地区免费层和 billing 的经验，但它是旧版本、旧政策下的个案，不能直接推导当前 `gemini-3.7-flash` 必须买账号或必须绑定某种 billing。

**可复用判断：** 社区能稳定复现的“结构性”路线仍是 Vertex AI；它与本项目研究到的官方文档一致，但必须使用自己的 Cloud project 和 Google Cloud Auth，不能购买他人的项目或凭据。

### 4. 没有发现“买账号”能稳定解决的证据

检索到的社区案例里，问题会随出口 IP、VPS 网段、IPv4/IPv6、具体后端 endpoint 和账号地区关联变化；没有可信的案例能证明“买一个支持地区账号”本身可以解决 `User location is not supported for the API use.`。相反，账号能否使用 API 仍需要在实际请求来源和具体 endpoint 上验证。

因此，下列做法不作为当前项目方案：

- 购买共享 Gmail、AI Studio 或 Gemini 成品账号；
- 购买共享 API key、service account 或 Cloud project；
- 新增第三方反向代理、中转站或依赖不明的“解锁服务”；
- 把 VPN、TUN、Smart DNS 或代理教程当成地区授权修复；
- 只凭网页端成功、`/health=200` 或模型列表可见就宣称 API 已成功。

## 与当前 Bridge 的差异

当前 [OpenAICompatibleProvider](../bridge/src/stardew_ai_bridge/providers.py) 已经具备可复用的协议骨架：

- 将 `model`、`messages`、`stream=true` 和 `max_tokens` 发送到一个可配置 URL；
- 解析 OpenAI-compatible streaming 的 `choices[0].delta.content`，也兼容非流式 `message.content`；
- 记录 provider、fallback、延迟、warnings 和 usage；
- 所有上游异常均收敛为不泄露凭据的 `ProviderError`。

但 Vertex 还需要补齐三个边界：

1. **认证来源**：不能把 ADC access token 当作长期 API key 写进 `.env.local`；Bridge 应在进程内通过受控的 Google Cloud Auth 取得/刷新短期 token，或由明确的本机运行环境注入短期 token，并且日志中不得打印 token。
2. **地址与项目参数**：当前 `ProviderSettings.url` 是直接 POST 的完整 URL；Vertex 官方示例以 project/location 拼接 base URL，工程上需要确定是新增 `BRIDGE_CLOUD_VERTEX_PROJECT` / `BRIDGE_CLOUD_VERTEX_LOCATION` 后由 Provider 拼接，还是让受控配置传入完整 `/chat/completions` URL。两种方案都属于官方 Vertex 配置，不是中转站，但应先写配置和请求边界测试再实现。
3. **模型命名**：AI Studio 兼容入口使用 `gemini-3.7-flash`；Vertex OpenAI-compatible 示例使用 `google/gemini-3.5-flash`。目标模型在 Vertex 上应先验证 `google/gemini-3.7-flash`，成功后再进入质量评测。

## 可行路线比较

| 路线 | 能否保持官方 | 需要什么 | 当前判断 |
|---|---|---|---|
| A. 继续 AI Studio/Gemini API | 是 | 请求来源和账号满足官方支持地区/服务条件，现有 Gemini API key | 代码改动最少；但当前 400 不能靠本地代码解决，换 Key 也不保证改变区域判定 |
| B. Vertex AI OpenAI-compatible | 是 | Cloud project、billing、Agent Platform API、Google Cloud Auth/ADC、project/location；Bridge 增加 ADC/token 适配 | 推荐作为项目长期路线；官方支持 Chat Completions、streaming，并列出 Gemini 3.7 Flash；需要一次认证适配和 Cloud 侧准备 |
| C. 旧 OpenAI/中转站/绕过区域 | 不符合本任务边界 | 额外服务、旧地址或规避区域条件 | 不采用 |

## 推荐的后续执行顺序

### 先在账号侧完成的步骤

这些步骤必须由用户在 Google Cloud 账号侧确认后才能进行，当前没有自动执行：

1. 准备一个允许使用 Vertex AI / Gemini Enterprise Agent Platform 的 Google Cloud project。
2. 确认 billing 已启用，并启用 Agent Platform API。
3. 在受控的本机开发环境配置 ADC，或准备等价的 Google Cloud Auth 运行身份；不要把长期服务账号 JSON、access token 或 API key 放入 Git 或聊天。
4. 确定第一轮只使用 `global` location，还是使用某个官方列出的 regional location。若没有数据驻留要求，`global` 更接近官方提高可用性的建议；这只是配置建议，不是当前账号一定成功的保证。

### 然后在项目内做的最小改造

只有账号侧前置条件具备后，才建议在本工作树中按 TDD 实施：

1. 为 Google Cloud Auth 增加独立认证模式和脱敏配置校验，不改变当前 AI Studio API-key 模式。
2. 为 Vertex URL 拼接、`google/gemini-3.7-flash` 模型名、Bearer access token 注入、streaming `choices[0].delta.content`、401/403/429 和 token 刷新失败分别增加测试。
3. 保持 `BRIDGE_CLOUD_ONLY=true` 的语义：Vertex 失败仍只进入安全 fallback，不静默切换 Qwen。
4. 用一个最小真实请求确认 HTTP 状态、`choices[0].message.content`、provider、fallback、延迟和 usage；只有 `provider=cloud` 且 `fallback=false` 才算官方云端成功。
5. 按既定流程重新运行 5 案例/15 轮质量冒烟；通过后分别运行新的 `default`、`conversation-lead`、`topic-start-intimacy`、`topic-start-adaptive`、`affection-pacing` 工件目录。任何 401/403/429/区域错误都先停止，不把 fallback 结果计入 Gemini 质量结论。

## 当前未解决问题与限制

- 尚未验证一个真实的 Vertex Cloud project、Google Cloud Auth 身份和计费状态；因此不能声称 Vertex 路线当前账号已经可用。
- 尚未验证 `google/gemini-3.7-flash` 在目标 project/location 下的实际返回；官方模型表支持它，但项目级权限、配额和账号条件仍需实测。
- 未测量 Vertex 的当前价格、配额和延迟；这些应在账号条件明确后查对应官方 pricing/quota 页面，不能用历史中转站数据代替。
- 当前 AI Studio/Gemini API 直连的区域错误不应通过代理、旧 OpenAI 地址或新的中转站绕过。本报告没有执行任何这类操作。
- 本轮没有新增质量评测工件，也没有把 Bridge fallback、Fake 或历史批次当作新的 Gemini 质量证据。

## 官方来源

- [Available regions for Google AI Studio and Gemini API](https://ai.google.dev/gemini-api/docs/available-regions)
- [OpenAI compatibility — Gemini API](https://ai.google.dev/gemini-api/docs/openai)
- [Troubleshooting guide — Gemini API](https://ai.google.dev/gemini-api/docs/troubleshooting)
- [Vertex AI locations](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations)
- [Configure application default credentials](https://cloud.google.com/vertex-ai/generative-ai/docs/start/gcp-auth)
- [OpenAI compatibility — Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/start/openai)
