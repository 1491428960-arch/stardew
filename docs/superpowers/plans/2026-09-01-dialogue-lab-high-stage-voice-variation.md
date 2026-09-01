# 高好感案例与角色表达变化实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 在当前 worktree 逐任务实现，并保留每个任务的测试与验证记录。

**目标：** 让高好感案例容易找到，并为模型增加可验证的角色表达变化约束与质量提示。

**架构：** 复用现有案例对象和 `dialogue_lab_page.py` 单页工作台，在前端增加阶段筛选和覆盖指标；在 Bridge 增加独立的纯函数表达质量检查，并由 `PromptBuilder` 生成小型表达变化卡。质量检查只产生标签，不修改生成文本。

**技术栈：** Python、pytest、现有 PromptBuilder、内嵌 HTML/CSS/JavaScript、Node `--check`。

---

### 任务 1：为高好感筛选和表达质量检查编写失败测试

**文件：**
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/tests/test_external_dialogue_lab.py`
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/tests/test_prompts.py`
- 创建：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/tests/test_dialogue_style_quality.py`

- [ ] **步骤 1：增加页面契约断言**

在 `test_external_dialogue_lab.py` 增加断言，要求 `/test` HTML 同时包含：

```python
for marker in (
    'data-filter="high_affinity"',
    'data-filter="close"',
    'id="filter-high-affinity-count"',
    'id="coverage-high-affinity"',
    'relationshipStageLabel',
    'friendshipHearts',
    'repeated_speech_particle',
):
    assert marker in html
```

- [ ] **步骤 2：增加 Prompt 契约断言**

在 `test_prompts.py` 增加一个包含历史语气词的上下文，断言 `voice_variation` 消息位于 `conversation_history` 之后、`player_input` 之前，并包含“不必使用”“同一语气词不能连续重复”等约束。

- [ ] **步骤 3：增加质量检查的红灯测试**

在新测试文件中写入以下行为测试，先引用尚不存在的函数：

```python
from stardew_ai_bridge.dialogue_style_quality import analyze_dialogue_style


def test_detects_repeated_speech_particle_in_one_reply() -> None:
    result = analyze_dialogue_style("嗯，今天还行。嗯，没别的事。")

    assert result["tags"] == ["repeated_speech_particle"]
    assert result["speechParticleCounts"]["嗯"] == 2


def test_detects_particle_repeated_from_recent_turns() -> None:
    result = analyze_dialogue_style(
        "嗯，先这样吧。",
        history=[{"role": "assistant", "content": "嗯，今天挺忙。"}],
    )

    assert "repeated_speech_particle" in result["tags"]


def test_keeps_different_particles_and_plain_reply_clean() -> None:
    assert analyze_dialogue_style("今天挺忙，晚点再说。")["tags"] == []
    assert analyze_dialogue_style("嗯，今天挺忙。啊，明天再看。")["tags"] == []
```

- [ ] **步骤 4：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py bridge/tests/test_prompts.py bridge/tests/test_dialogue_style_quality.py
```

预期：新页面标记、Prompt 标记和 `dialogue_style_quality` 导入失败，证明测试捕获的是功能缺口。

### 任务 2：实现纯函数表达质量检查

**文件：**
- 创建：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/src/stardew_ai_bridge/dialogue_style_quality.py`
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/tests/test_dialogue_style_quality.py`

- [ ] **步骤 1：定义稳定的颗粒与开场识别**

实现 `analyze_dialogue_style(reply: str, history: object = None) -> dict[str, object]`，只识别短口语颗粒 `嗯、哦、啊、唔、呃、嘿、好吧、行吧`，并按中文标点切分短句。返回：

```python
{
    "tags": list[str],
    "speechParticleCounts": dict[str, int],
    "opening": str,
}
```

同一回复某颗粒出现至少两次，或本轮开头颗粒与最近 assistant 回复开头相同，加入 `repeated_speech_particle`；短颗粒总数超过 1 且集中在同一个回复时加入 `too_many_speech_particles` 仅在确实重复时使用。不得返回原始 prompt、配置或凭据。

- [ ] **步骤 2：运行定向测试确认通过**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_dialogue_style_quality.py
```

预期：`3 passed` 或测试文件实际包含的全部测试通过。

### 任务 3：把表达变化卡接入 PromptBuilder

**文件：**
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/tests/test_prompts.py`

- [ ] **步骤 1：增加失败断言**

先运行任务 1 的 Prompt 定向测试，确认 `voice_variation` 消息不存在或缺少约束。

- [ ] **步骤 2：实现最小 Prompt 投影**

从现有 `voiceCard.speechParticleHints`、当前阶段和 `_history_speech_particles` 生成一个独立 system message：

```python
{
    "role": "system",
    "name": "voice_variation",
    "content": "...语气词是可选项；同一颗粒不能连续重复；先回答内容，再决定是否加停顿...",
}
```

只传短颗粒、阶段和近期已用颗粒，不复制完整历史台词，不增加新的事实来源。消息顺序固定为 `conversation_history` 之后、`current_topic_anchor` 或 `player_input` 之前。

- [ ] **步骤 3：运行 Prompt 定向回归**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py
```

预期：现有 Prompt 测试和新增表达变化测试全部通过。

### 任务 4：实现高好感案例浏览改版

**文件：**
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/tests/test_external_dialogue_lab.py`

- [ ] **步骤 1：增加前端阶段模型**

保留现有 `state.filter` 兼容结构，增加：

```javascript
const stageLabels = { stranger:"初识", acquaintance:"熟悉", friend:"朋友", close:"亲近", dating:"恋爱", married:"婚后", parent:"育儿" };
const highAffinityStages = new Set(["close", "dating", "married", "parent"]);
function matchesFilter(item) {
  if (state.filter === "high_affinity") return highAffinityStages.has(item.relationshipStage);
  if (stageLabels[state.filter]) return item.relationshipStage === state.filter;
  return state.filter === "all" || categoryOf(item) === state.filter;
}
```

`renderFilterCounts()` 为高好感和每个阶段分别计算数量；`renderCaseList()` 使用同一筛选函数，不复制案例数组。

- [ ] **步骤 2：调整列表与覆盖面板信息**

每个 `.case-row` 增加阶段、`friendshipHearts`、渠道和预置历史标签；覆盖面板增加 `id="coverage-high-affinity"`。高好感筛选下无结果时保留解释性空状态。

- [ ] **步骤 3：加入质量标签展示**

页面读取已存在的 `result.score.tags` 和新 `result.styleQuality.tags`，在详情结果卡中显示“重复语气词”“重复开场”等提示；没有字段时显示“未检测”，不把缺字段当成通过。

- [ ] **步骤 4：运行页面契约与脚本检查**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py
```

预期：页面契约通过，内嵌 JavaScript 语法检查全部通过。

### 任务 5：接入结果展示、回归与运行时验证

**文件：**
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/src/stardew_ai_bridge/quality_results.py`
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/bridge/tests/test_quality_results.py`
- 修改：`E:/workspace/projects/stardew-ai-npc.worktrees/story-memory/docs/active-work.md`

- [ ] **步骤 1：为脱敏结果保留质量标签**

若 `styleQuality` 存在，只保留 `tags`、非负计数和 `opening` 的短文本，过滤 prompt、token、apiKey 等敏感字段；旧结果继续按现有 schema 返回。

- [ ] **步骤 2：运行结果模块定向测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_quality_results.py bridge/tests/test_dialogue_style_quality.py
```

预期：全部通过，且序列化结果不含敏感字段。

- [ ] **步骤 3：运行 Bridge 完整回归**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests
```

预期：所有 Bridge 测试通过，数量以实际输出为准；不生成云端评测。

- [ ] **步骤 4：重启并验证当前 Bridge**

只重启当前 `story-memory` worktree 的 Bridge，确认包装器和实际 5678 Python 子进程都来自该 worktree，然后检查：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5678/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5678/test
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5678/api/quality/cases
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5678/api/quality/results
```

确认 `/health` 为 200，页面为 `data-ui-shell="v4"`，案例接口仍包含 `close` 与 `married`，结果接口不返回 prompt/API key。

- [ ] **步骤 5：记录活动状态**

在 `docs/active-work.md` 追加实际测试数量、Bridge 健康状态、当前批次 ID 和“本轮未发起云端生成”的边界；不写入密钥、完整请求或浏览器个人数据。

