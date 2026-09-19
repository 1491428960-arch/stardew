# Gemini 正式运行路由切换实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 逐任务实现，按复选框推进，并在每个质量边界保留红灯、绿灯和运行态证据。

**目标：** 将 Bridge 的正式默认路径切换为 Gemini 云端 Provider：默认请求和 `auto` 只调用 Gemini；Gemini 失败、429 或超时时只进入安全 fallback，不静默调用 Qwen。保留显式 `provider=local` 作为 Qwen A/B 与手动回滚入口，不启动游戏、不部署 DLL、不修改正式 Mods、存档或角色资料库。

**架构：** `BridgeSettings` 增加 `cloud_only` 配置；`ProviderRouter` 在 cloud-only 模式下只改变自动候选，不改变显式 `local`、显式 `cloud`、`fake` 和安全 fallback。Dialogue Lab 默认展示 Gemini 正式运行，local 文案明确为手动 A/B/回滚。Key 只从现有本机环境读取，不读取、打印或写入测试/文档。

**技术栈：** Python 3.10、pytest、现有 Bridge Provider/配置/Dialogue Lab；验证使用定向测试、Bridge 全量回归、`compileall`、`git diff --check`，最后做一次脱敏的真实默认请求核对。

---

### 任务 1：先建立 cloud-only 路由契约

**文件：**
- 修改：`bridge/tests/test_providers.py`、`bridge/tests/test_config.py`、`bridge/tests/test_external_dialogue_lab.py`

- [x] **步骤 1：编写失败测试**

  覆盖 `BRIDGE_CLOUD_ONLY` 环境变量读取；`cloud_only=True` 时 `auto` 只返回 cloud candidate；Gemini 失败时不调用 local、只调用安全 fallback；显式 `provider=local` 仍调用 Qwen；显式 `provider=cloud` 仍只调用 Gemini；页面默认 Provider 与文案为 Gemini 正式运行模式；README 的正式默认路由不再写成 local → cloud。

- [x] **步骤 2：运行测试验证失败**

  运行：`$env:PYTHONPATH='bridge\src'; py -3.10 -m pytest bridge/tests/test_config.py bridge/tests/test_providers.py bridge/tests/test_external_dialogue_lab.py -k 'cloud_only or gemini or provider or default or route' -q`

  实际：`8 failed, 30 passed, 75 deselected`；失败集中在缺少 `cloud_only` 参数/字段和新页面文案，证明红灯由待实现契约触发。

---

### 任务 2：实现 Gemini 正式默认路由

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/config.py`
- 修改：`bridge/src/stardew_ai_bridge/providers.py`
- 修改：`.env.local`（仅布尔开关/注释，不读取或改写 Key）

- [x] **步骤 1：最小实现**

  将 `BRIDGE_CLOUD_ONLY` 纳入本地环境允许键和 `BridgeSettings`；把 `cloud_only` 传入 `ProviderRouter`。cloud-only 下 `auto` 只返回 cloud；显式 `local` 仍绕过 cloud-only 直接调用本地 Provider；显式 `cloud` 与 `fake` 保持现有行为；失败后继续只走 fallback。

  在 `.env.local` 中只确保 `BRIDGE_CLOUD_ENABLED=true` 和 `BRIDGE_CLOUD_ONLY=true`，保留现有 Key 内容不动，并不把任何凭据写进仓库跟踪文件以外的文档或输出。

- [x] **步骤 2：运行定向绿灯**

  运行同任务 1 的 pytest 命令；实际 `38 passed, 75 deselected in 1.53s`。

---

### 任务 3：同步 Dialogue Lab、README 和活动记录

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 修改：`README.md`
- 修改：`docs/active-work.md`

- [x] **步骤 1：更新用户可见语义**

  页面将默认选项标为“Gemini 正式运行（默认）”，`auto` 明确为“正式自动（仅 Gemini，失败安全兜底）”，local 明确标为“Qwen 本地（手动 A/B / 回滚）”，提示文本说明中转站波动不会静默切回 Qwen。质量评测和 Fake 入口保持原有用途。

- [x] **步骤 2：更新文档和活动记录**

  README 说明正式默认、显式 local 回滚、显式 cloud 和安全 fallback 的边界；活动记录写入本轮改动和验证证据，不声称已完成游戏内验证。

- [x] **步骤 3：运行页面/文档契约测试**

  页面已加入 Gemini 默认、cloud-only auto、显式 Qwen A/B/回滚文案；相关 API/Provider/页面测试合计 `137 passed`。README 现明确 cloud-only、显式 local 和安全 fallback 边界。

---

### 任务 4：全量验证与运行态核对

- [ ] **步骤 1：定向回归**

  运行配置、Provider、API、Dialogue Lab 相关测试，确认健康检查和显式回滚路径没有回归。

- [ ] **步骤 2：项目验证**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge\src'
  py -3.10 -m pytest bridge/tests -q
  py -3.10 -m compileall -q bridge/src scripts
  git diff --check
  ```

  只报告本轮实际输出；保留前序工作树改动，不清理 `.tmp-pytest`，不创建 Git commit。

- [ ] **步骤 3：Bridge 运行态核对**

  确认 5678 监听进程的 PID/命令行来自当前 worktree，再检查 `/health` 显示 cloud/Gemini；发送一次不含 Key 的真实默认请求，确认结果 `provider=cloud`。用替身失败测试确认 cloud-only 不会静默调用 local。

- [ ] **步骤 4：代码审查和收尾**

  请求一次针对本轮 diff 的代码审查；只修复 Critical/Important 问题。最终汇报代码测试、Bridge 运行态和游戏验证三类证据的边界，并明确用户是否需要操作。
