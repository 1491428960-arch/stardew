# 质量评测查看器恢复实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现；保留当前工作树所有既有修改，不创建 Git 提交。

**目标：** 修复历史质量评测页面，使 Guard 重试和批次覆盖关系在人类可读的 transcript 中可见。

**架构：** 保持现有脱敏结果 API 和案例目录不变，只补齐前端历史 transcript 的警告渲染，并在批次摘要中加入覆盖关系提示。通过现有 FastAPI TestClient 和浏览器工作台验证，不触发新的模型请求。

**技术栈：** Python、FastAPI、内嵌 JavaScript/HTML、pytest、Codex in-app browser。

---

### 任务 1：为历史 Guard 警告建立失败回归

**文件：**
- 修改：`bridge/tests/test_external_dialogue_lab.py`

- [ ] **步骤 1：添加断言**

为已有 `renderCaseTranscript` 页面测试增加断言：函数体读取 `turn.warnings`，包含警告格式化逻辑和“Guard 重试”可读标签；批次摘要包含结果数与案例目录覆盖信息。

- [ ] **步骤 2：运行定向测试确认失败**

运行：`py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py -k "multiturn_transcript or quality_results"`

预期：新增断言因当前页面没有读取 `turn.warnings` 而失败。

### 任务 2：实现最小历史警告与覆盖提示渲染

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`

- [ ] **步骤 1：渲染每轮 Guard 警告**

在 `renderCaseTranscript` 中读取 `turn.warnings`，过滤字符串并限制显示数量，生成独立的 `.result-warning` 节点；保留原评分标签渲染不变。

- [ ] **步骤 2：渲染批次覆盖提示**

在批次摘要中计算案例目录总数与实际结果数，显示“结果覆盖 X / Y；其余案例未生成”，同时保留原有通过率和 Token 信息。

- [ ] **步骤 3：运行定向测试确认通过**

运行：`py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py bridge/tests/test_quality_results.py`

预期：定向测试通过。

### 任务 3：HTTP 与浏览器验收

**文件：**
- 不新增项目文件。

- [ ] **步骤 1：重载现有查看器**

只重载 `127.0.0.1:5678` 的现有查看器入口，继续使用当前对齐批次，不运行其他服务。

- [ ] **步骤 2：验证接口和页面**

检查 `/health`、`/api/quality/results` 和目标 `/test` 的状态码、Content-Type、批次标识、警告文本和覆盖提示。

- [ ] **步骤 3：浏览器工作台视觉检查**

在目标页面确认三轮实际对白、每轮 Guard 重试、评分标签和覆盖提示均可见；确认工作树没有额外非预期修改。
