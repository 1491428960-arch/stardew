# Bridge 索引上下文检索实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 TDD 实现本计划。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 让 Bridge 在索引文件存在时，把当前 NPC 相关的少量对白风格证据和剧情候选安全地加入上下文；索引缺失或损坏时保持现有对话行为。

**架构：** `ProfileIndexStore` 只读加载 `profile-index.json`，按 NPC ID 和来源 Mod 筛选并限制条数；`ContextBuilder` 通过依赖注入接收它，只有检索到内容时才增加可选上下文字段。`PromptBuilder` 将可选证据放入独立系统消息，绝不把索引全部内容或来源绝对路径发送给模型。

**技术栈：** Python 3.12、现有 Bridge、pytest。

---

## 文件职责

- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`
  - 增加只读 `ProfileIndexStore`，负责损坏降级、来源匹配和数量上限。
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
  - 注入索引存储；在有证据时扩展上下文和 Prompt，保持无索引时旧契约不变。
- 修改：`bridge/src/stardew_ai_bridge/app.py`
  - 从项目默认 `data/generated/profile-index.json` 初始化可选存储。
- 创建：`bridge/tests/test_profile_context.py`
  - 覆盖来源匹配、上限、损坏索引、Prompt 隔离和旧上下文兼容。
- 修改：`README.md`
  - 说明生成索引后 Bridge 会自动按 NPC 检索，缺失时安全跳过。
- 修改：`docs/handoff-2026-08-23.md`
  - 记录索引检索已接入，运行时事件仍未接入。

### 任务 1：检索存储测试

- [x] **步骤 1：编写失败测试**

测试要求：当前 NPC 只得到匹配 NPC 和来源 Mod 的样本；最多返回 8 条；坏 JSON 返回空结果；来源路径不会进入返回内容。

- [x] **步骤 2：运行测试确认失败**

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q bridge/tests/test_profile_context.py -p no:cacheprovider
```

预期：`ProfileIndexStore` 尚未定义。

- [x] **步骤 3：实现最小检索存储并通过定向测试**

公开接口：

```python
class ProfileIndexStore:
    def __init__(self, index_path: str | Path) -> None: ...
    def style_samples(self, npc_id: str, source_mods: Iterable[str], limit: int = 8) -> list[dict[str, Any]]: ...
    def story_events(self, npc_id: str, source_mods: Iterable[str], limit: int = 8) -> list[dict[str, Any]]: ...
```

- [x] **步骤 4：Commit**

```powershell
git add bridge/src/stardew_ai_bridge/profile_index.py bridge/tests/test_profile_context.py
git commit -m "feat(上下文): 添加资料索引检索存储"
```

### 任务 2：上下文与 Prompt 接入

- [x] **步骤 1：编写失败测试**

覆盖：有样本时上下文增加 `styleSamples`/`storyEvents`；无样本时上下文键集合保持原样；Prompt 使用 `style_evidence` 和 `story_facts` 独立消息，并限制每条文本长度。

- [x] **步骤 2：实现最小接入**

`ContextBuilder` 接收可选 `ProfileIndexStore`；`PromptBuilder` 只读取可选字段，不改变旧字段顺序和安全清理逻辑。

- [x] **步骤 3：运行 Bridge 全量测试**

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q -p no:cacheprovider
```

- [x] **步骤 4：Commit**

```powershell
git add bridge/src/stardew_ai_bridge/prompts.py bridge/src/stardew_ai_bridge/app.py bridge/tests/test_profile_context.py
git commit -m "feat(上下文): 接入资料索引检索"
```

### 任务 3：文档与验证

- [x] **步骤 1：更新 README 和交接**

明确索引缺失不阻断 Bridge，事件/好感/婚姻状态仍需下一层 SMAPI 采集。

- [x] **步骤 2：运行 Bridge、SMAPI C# 和 `git diff --check`**

- [x] **步骤 3：Commit**

```powershell
git add README.md docs/handoff-2026-08-23.md docs/superpowers/plans/2026-08-23-context-index-retrieval.md
git commit -m "docs(交接): 记录索引上下文接入"
```

## 计划自检

- 无索引时不改变已有上下文键和 Prompt 顺序。
- 检索只按当前 NPC、来源和上限筛选，不把全量资料发送给模型。
- 索引损坏只降级为空结果，不阻断对话。
- 本计划不接触存档、事件旗标、好感度写入和 UI。
