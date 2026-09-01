# Dialogue Lab UI 统一实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现，并用 `update_plan` 跟踪状态。

**目标：** 统一 `/test`、`/test/chat` 和 `/raw` 的视觉主题、顶部导航和通用控件，同时不改变页面业务行为。

**架构：** 在现有内嵌 HTML 页面模块中增加一套共享 CSS 注入函数，统一主题变量、工作台顶栏、导航标签、按钮和健康状态；三个页面保留各自的主体布局。通过页面契约测试锁定三个路由的共同壳层。

**技术栈：** FastAPI、内嵌 HTML/CSS/JavaScript、pytest、Node `--check`。

---

### 任务 1：建立三页共享 UI 契约

**文件：**
- 修改：`bridge/tests/test_external_dialogue_lab.py`
- 参考：`docs/superpowers/specs/2026-08-30-dialogue-lab-ui-unification-design.md`

- [x] **步骤 1：编写失败测试**

添加测试，分别请求 `/test`、`/test/chat`、`/raw`，要求每页包含：

```python
data-ui-shell="v1"
class="workspace-nav"
href="/test"
href="/test/chat"
href="/raw"
aria-current="page"
--ui-shell-version: 1;
```

同时保留各页现有的主体标记。

- [x] **步骤 2：运行测试确认当前实现失败**

运行：
`Python310 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py -k shared_ui`

预期：失败，因为 `/test/chat` 和 `/raw` 当前没有共享导航和版本化主题标记。

### 任务 2：注入共享主题并统一导航

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 测试：`bridge/tests/test_external_dialogue_lab.py`

- [x] **步骤 1：实现共享主题注入**

添加 `DIALOGUE_LAB_SHARED_UI_CSS` 和 `_with_shared_ui(html)`，在每个页面的第一段 `</style>` 前注入；统一主题变量、`workspace-topbar`、`workspace-nav`、`workspace-tab`、按钮和健康状态样式。

- [x] **步骤 2：给三页接入相同导航**

让三个页面的顶栏都包含以下三条链接，并只给当前页面添加 `aria-current="page"`：

```html
<nav class="workspace-nav" aria-label="工作台导航">
  <a class="workspace-tab" href="/test">测试例浏览</a>
  <a class="workspace-tab" href="/test/chat">单次聊天</a>
  <a class="workspace-tab" href="/raw">原始对白</a>
</nav>
```

顶栏保留原页面的标题、健康状态和操作按钮。

- [x] **步骤 3：运行契约测试确认通过**

运行：
`Python310 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py -k shared_ui`

预期：共享 UI 契约全部通过。

### 任务 3：完整回归与运行时检查

**文件：**
- 修改：`docs/active-work.md`
- 修改：`docs/superpowers/plans/2026-08-30-dialogue-lab-ui-unification.md`

- [x] **步骤 1：运行页面/API 定向测试**

运行：
`Python310 -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py bridge/tests/test_api.py`

- [x] **步骤 2：运行 Bridge 全量测试和嵌入脚本语法检查**

运行完整 `bridge/tests`，并从 `dialogue_lab_page.py` 提取三段 `<script>`，分别执行 `node --check --input-type=commonjs`。

- [x] **步骤 3：重启 Bridge 并检查三个路由**

确认包装器和 5678 实际监听子进程均为本轮新进程，检查 `/health`、`/test`、`/test/chat`、`/raw` 返回 200 且健康状态为 `provider=local`。

- [x] **步骤 4：在浏览器核对统一 UI**

打开 `http://127.0.0.1:5678/test`，检查三页导航、当前页高亮、主题颜色、顶栏、按钮和主体内容没有被破坏；已完成路由和 HTML 壳层检查。内置浏览器自动控制因运行时内核资产路径异常不可用，已记录为环境限制，没有把 HTTP 检查冒充截图级验证。
