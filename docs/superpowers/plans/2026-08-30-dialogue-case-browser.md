# 测试例浏览器实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现，并用 `update_plan` 跟踪状态。

**目标：** 将 `/test` 默认改为以查看质量测试例为中心的浏览器，同时保留现有真实单次聊天页面。

**架构：** 新增只读 `/api/quality/cases`，从现有 `character_quality_eval.DEFAULT_CASES` 生成脱敏案例目录；`/test` 返回案例浏览页，`/test/chat` 返回现有聊天页。案例页只展示测试输入、关系阶段、渠道、历史、期望词和禁止词，不生成或保存模型请求。

**技术栈：** FastAPI、现有 Python dataclass、内嵌 HTML/CSS/JavaScript、pytest 页面契约测试。

---

### 任务 1：提供脱敏质量测试例接口

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 测试：`bridge/tests/test_external_dialogue_lab.py`

- [x] **步骤 1：编写失败的接口与页面契约测试**

已添加 `/api/quality/cases`、案例页标记和 `/test/chat` 路由测试。

- [x] **步骤 2：运行测试验证失败**

运行：
`Python310 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py::test_default_external_lab_prioritizes_case_browser ...`

实际结果：`4 failed`，失败原因分别是默认页没有案例浏览器标记、聊天兼容路由 404、案例渲染函数不存在、案例接口 404。

- [x] **步骤 3：实现案例序列化和接口**

新增 `quality_case_catalog()`，只输出 `caseId`、角色身份、来源 Mod、关系阶段、渠道、历史、玩家输入、期望词和禁止词；`/api/quality/cases` 返回 `schemaVersion=1` 与来源标识。

- [x] **步骤 4：运行接口测试确认通过**

运行：
`Python310 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py::test_quality_cases_endpoint_exposes_sanitized_existing_cases`

预期：通过，并确认响应不包含 `prompt`、`apiKey` 或 `token`。

### 任务 2：实现案例浏览页并保留聊天入口

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 修改：`bridge/tests/test_external_dialogue_lab.py`
- 修改：`bridge/tests/test_api.py`

- [x] **步骤 1：新增案例浏览 HTML**

页面默认展示左侧案例导航、中间当前案例详情和右侧覆盖情况；案例详情由 `/api/quality/cases` 加载，前端按类型筛选并展开历史、期望词和禁止词。

- [x] **步骤 2：接入路由与导航**

`GET /test` 返回案例浏览页，`GET /test/chat` 返回原有 `DIALOGUE_LAB_HTML`；案例页提供返回聊天页和原始对白参照入口。

- [x] **步骤 3：运行页面定向测试**

运行：
`Python310 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py bridge/tests/test_api.py`

预期：现有聊天页面契约和新增案例页面契约全部通过。

### 任务 3：回归与浏览器验证

**文件：**
- 修改：无新增生产文件

- [x] **步骤 1：运行完整 Bridge 测试**

运行：
`$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'; $env:PYTHONDONTWRITEBYTECODE='1'; Python310 -B -m pytest -q -p no:cacheprovider bridge/tests`

- [x] **步骤 2：检查 HTML 与接口实际响应**

请求 `/health`、`/test`、`/test/chat` 和 `/api/quality/cases`，确认状态码、案例数量和敏感字段过滤。

- [ ] **步骤 3：重启目标 Bridge 并打开 `/test`**

只重启目标 worktree 的 Bridge；确认包装进程和实际监听 5678 的子进程均为新进程，再用浏览器渲染读取检查案例目录、当前案例和覆盖面板。

当前状态：Bridge 重启、健康接口、案例接口和页面 HTML 已实际验证；已请求把 `/test` 打开到当前 Codex 面板，但内置浏览器自动控制因运行时内核资产路径异常未完成点击、渲染读取和截图验证，因此本步骤保留未勾选。
