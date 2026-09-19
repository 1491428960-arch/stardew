# Gemini 中转站 cloud-only 运行计划

> **面向 AI 代理的工作者：** 本计划在当前 `story-memory` 工作树内内联执行；不创建 Git commit，不覆盖已有未提交修改。

**目标：** 在暂不具备 Vertex 条件期间，复用项目已有 Gemini 中转配置作为唯一自动生成来源，禁止 Qwen 自动降级输出，并用新的最小冒烟和质量工件确认中转响应完整可用。

**架构：** 不改变官方 `.env.local`，只在本轮 Bridge/评测子进程中加载已有 `.env.gemini.local`。保持 `BRIDGE_CLOUD_ENABLED=true`、`BRIDGE_CLOUD_ONLY=true`，使自动路由只尝试 Gemini；中转失败只进入现有安全兜底，不调用本地 Qwen。显式 `provider=local` 继续保留为手动离线 A/B，不作为生产自动回退。

**技术栈：** PowerShell 进程级环境覆盖、Python 3.10、现有 `ProviderRouter`、pytest、项目 `scripts/start_bridge.ps1`、现有质量评测脚本。

---

### 任务 1：确认 cloud-only 路由门控

**文件：**

- 检查：`bridge/src/stardew_ai_bridge/providers.py`
- 检查：`bridge/tests/test_providers.py`

- [x] **步骤 1：确认现有行为测试**

已确认现有测试覆盖：cloud-only 自动候选只有 cloud、Gemini 失败不调用 local、显式 local 仍可手动 A/B。

- [x] **步骤 2：运行定向测试**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_providers.py bridge/tests/test_config.py
```

预期：全部通过；不发起网络请求。

---

### 任务 2：使用已有中转配置执行最小真实请求

**文件：**

- 读取：`.env.gemini.local`
- 不修改：`.env.local`
- 不输出：`BRIDGE_CLOUD_API_KEY`

- [ ] **步骤 1：在当前 PowerShell 进程内加载中转变量**

逐行读取已有 `.env.gemini.local`，将 URL、模型、API key、timeout 和 cloud 开关注入当前进程；只输出配置键名和脱敏状态，不打印值。

- [ ] **步骤 2：发送一个最小 cloud 请求**

使用现有 `OpenAICompatibleProvider`/评测入口，显式 `--provider cloud`，只请求一个固定短句；记录 HTTP 状态、provider、fallback、非空内容、延迟、usage、warnings 和响应是否被 `finish_reason=length` 截断。

- [ ] **步骤 3：执行门控**

只有 HTTP 2xx、非空完整内容、`provider=cloud-relay`、`fallback=false` 且没有截断时，才进入 Bridge 和 5 案例/15 轮；遇到 401、403、429、超时、空内容、SSE 截断或格式异常立即停止。

---

### 任务 3：隔离重载 Bridge 并验证运行态

**文件：**

- 使用：`scripts/start_bridge.ps1`
- 不修改：项目源代码和 `.env.local`

- [ ] **步骤 1：停止旧的项目 Bridge（若存在）**

只处理监听 `127.0.0.1:5678` 且命令行指向当前 `story-memory` 工作树的进程；不操作其他目录或服务。

- [ ] **步骤 2：以中转配置启动 Bridge**

通过当前进程环境覆盖 relay URL/model/key，并保持 `BRIDGE_CLOUD_ONLY=true`；如脚本被执行策略阻止，只使用进程级 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`。

- [ ] **步骤 3：核验运行态**

检查 5678 监听 PID 和命令行、`/health`、关系案例接口，以及一次明确 `provider=cloud` 的最小真实请求。`/health=200` 只能作为服务证据，不能作为 Gemini 成功证据。

---

### 任务 4：运行新的小批量质量冒烟

**文件：**

- 使用：`scripts/run_character_quality_eval.py`
- 创建：`artifacts/character-quality-eval/20260909-gemini37-flash-relay-smoke-v1/`

- [ ] **步骤 1：执行 5 案例、15 轮**

显式传入 `--provider cloud`，使用唯一的新工件目录，不覆盖任何历史结果；不启用 `provider=local`，不允许 Qwen 自动回退。

- [ ] **步骤 2：核对统计和对白边界**

记录案例数、轮数、ProviderError、fallback、重试、Token、延迟、自动评分和预算停止原因；额外检查玩家忠诚、嫉妒表达、NPC 不代替其他 NPC 发言、无未来排期承诺、女性化角色名/id/代词、关系修复和亲吻语义边界。

- [ ] **步骤 3：决定是否继续完整评测**

只有小批量真实中转请求全部完整且没有 ProviderError/fallback/截断，才考虑五套独立完整评测；否则保留新工件并报告中转站响应层问题。

---

### 验证清单

- [ ] 官方 `.env.local` 未被修改
- [ ] 中转 API Key 只在当前进程变量中使用，未打印、复制、提交或写入工件
- [ ] 自动路由没有调用 Qwen
- [ ] 中转最小请求满足完整响应门控
- [ ] Bridge PID 指向当前工作树
- [ ] `/health` 未被误报为模型成功
- [ ] 小批量使用唯一工件目录
- [ ] 未启动 Stardew Valley、SMAPI，未部署 DLL，未修改正式 Mods、存档或角色资料库
- [ ] 未创建 Git commit
