# 外部 NPC 对话实验室实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）按任务顺序实现，并保留每个任务的测试检查点。

**目标：** 将 Bridge 的 `/test` 从单轮 Fake 表单升级为可连续试聊、可编辑场景、可查看诊断并可导出会话的本地浏览器对话实验室。

**架构：** 继续由 FastAPI 在 `127.0.0.1:5678` 同源提供内联 HTML/JavaScript；前端调用 `/api/npcs`、`/api/context/preview`、`/api/dialogue/test` 和本地会话 API `/api/dialogue/session`，会话状态保存在本机 JSON 文件 `%TEMP%\\StardewAI.NPC\\dialogue-lab-session.json`。自动 Provider 通过省略 `provider` 字段触发现有路由，Fake 通过显式 `provider: "fake"` 保持清晰标记。

**技术栈：** FastAPI、TestClient、pytest、原生 HTML/CSS/JavaScript，无新增前端依赖。

---

### 任务 1：建立外部实验室页面契约测试

**文件：**
- 创建：`bridge/tests/test_external_dialogue_lab.py`
- 参考：`bridge/tests/test_api.py`

- [x] **步骤 1：编写失败的测试**

```python
from fastapi.testclient import TestClient

from stardew_ai_bridge.app import app


def test_external_lab_exposes_three_panel_controls() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        'id="scene-panel"',
        'id="transcript"',
        'id="diagnostics-panel"',
        'id="provider-mode"',
        'id="send"',
        'id="topic"',
        'id="clear-session"',
        'id="export-session"',
    ):
        assert marker in html


def test_external_lab_script_builds_contextual_multi_turn_requests() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "/api/npcs",
        "/api/context/preview",
        "/api/dialogue/test",
        "history",
        "gameState",
        "friendshipHearts",
        "shiftKey",
        "messages",
        "provider-mode",
    ):
        assert marker in html
    assert "发送 Fake 对话" not in html


def test_external_lab_keeps_input_on_request_failure() -> None:
    html = TestClient(app).get("/test").text

    assert "messageInput.value" in html
    assert "finally" in html
    assert "正在保留" in html or "保留输入" in html
```

- [x] **步骤 2：运行测试验证失败**

运行：

```powershell
Set-Location bridge
..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dialogue_lab.py -p no:cacheprovider
```

预期：失败；当前页面缺少三栏控件、连续请求脚本和失败保留输入文案。

### 任务 2：实现本地浏览器对话实验室

**文件：**
- 创建：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 修改：`bridge/src/stardew_ai_bridge/app.py:19,80`（仅切换 `/test` 页面常量）
- 保留：`bridge/src/stardew_ai_bridge/test_page.py` 作为旧页面常量，避免覆盖已有未提交工作
- 不修改：`app.py` 的现有对话路由和游戏内 C# 代码

- [x] **步骤 1：用最少页面结构满足契约**

在新页面常量中加入 `scene-panel`、`transcript`、`diagnostics-panel`、Provider 模式、场景字段、发送/找话题/清空/导出控件；保留 `npc-select` 与 `reply` 兼容旧测试。

- [x] **步骤 2：实现会话状态和请求构造**

前端维护 `messages` 与最多 50 条 `history`，发送时构造合法 `gameState`；自动模式不带 `provider`，Fake 模式才发送 `provider: "fake"`。关系阶段只映射为现有字段：

```javascript
const stageState = {
  stranger: { friendshipHearts: 0, relationship: "未婚" },
  acquaintance: { friendshipHearts: 3, relationship: "未婚" },
  friend: { friendshipHearts: 6, relationship: "朋友" },
  close: { friendshipHearts: 8, relationship: "朋友" },
  dating: { friendshipHearts: 8, relationship: "dating" },
  married: { friendshipHearts: 10, relationship: "married", marriageStatus: "married" },
  parent: { friendshipHearts: 10, relationship: "married", marriageStatus: "married", childrenCount: 1 },
};
```

- [x] **步骤 3：实现渲染和诊断**

把每轮用户/NPC消息追加到可滚动 transcript；显示 Provider、延迟、fallback、warnings；调用 `/api/context/preview` 更新上下文摘要；失败时在诊断区显示错误并保留输入文本。

- [x] **步骤 4：实现交互边界**

Enter 发送、Shift+Enter 换行；请求期间禁用操作按钮；主动找话题使用 `intent: "topic"`；清空当前会话并调用本地会话 API 删除 JSON 文件；导出下载脱敏会话 JSON；不访问 Token 或保存完整请求 payload。

- [x] **步骤 5：运行页面契约测试确认通过**

运行：

```powershell
..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dialogue_lab.py -p no:cacheprovider
```

预期：3 个页面契约测试通过。

### 任务 3：回归 Bridge、更新入口说明并做真实 HTTP 验证

**文件：**
- 修改：`README.md`（补充实验室操作入口和自动/Fake 语义）
- 修改：`docs/active-work.md`（记录测试和 HTTP 验证证据）

- [x] **步骤 1：运行 Bridge 全量 Python 测试**

运行：

```powershell
Set-Location bridge
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

预期：全部测试通过，包含新增页面契约测试。

- [x] **步骤 2：确认本机 Bridge 实例和页面接口**

使用现有 `127.0.0.1:5678` Bridge，依次请求 `/health`、`/test`、`/api/npcs` 和一轮 `/api/dialogue/test`；确认响应状态为 200、HTML 包含实验室控件、对话响应有 `provider`/`latencyMs`/`warnings`。

- [x] **步骤 3：做浏览器视觉检查**

打开 `http://127.0.0.1:5678/test`，检查宽屏三栏、中文输入、多轮滚动、诊断卡片和错误提示；截图保存到临时路径，检查后删除临时文件。

- [x] **步骤 4：记录证据并清理**

在 `docs/active-work.md` 追加实际测试数量、HTTP 状态和视觉检查结果；确认没有新增 Token、Cookie、绝对路径或运行时数据进入 Git 变更。
