# 离线资料索引基础实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 TDD 实现本计划。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 建立一个只读、可追溯的离线资料索引器，把现有人设覆盖层和可选 Content Patcher 角色对白资产整理为稳定的 `NpcProfile`、风格证据和剧情候选记录。

**架构：** `profile_index.py` 只负责读取输入目录、提取来源键和生成内存索引；它不修改游戏文件、不解析存档、不把原始 Mod 全文写进 Prompt。Content Patcher 的注释和尾逗号由本地宽松 JSON 读取器处理，对白值保留 `{{i18n:...}}` 引用而不强行解析翻译。CLI 负责路径参数和输出文件，Bridge 现有 `PersonaStore` 保持原行为，后续再接入索引检索。

**技术栈：** Python 3.12、标准库 `json`/`argparse`/`pathlib`、现有 pytest。

---

## 文件职责

- 创建：`bridge/src/stardew_ai_bridge/profile_index.py`
  - 定义 `ProfileIndexBuilder`、宽松 JSON 读取、稳定索引 schema 和警告记录。
- 创建：`bridge/tests/test_profile_index.py`
  - 覆盖人设来源合并、Content Patcher 对白引用、坏文件跳过和路径归一化。
- 创建：`scripts/build_profile_index.py`
  - 提供 `--persona-dir`、重复 `--mod-root` 和 `--output` 参数，调用索引器并写入 JSON。
- 修改：`README.md`
  - 记录索引器用途、只读边界和最小运行命令。
- 修改：`docs/handoff-2026-08-23.md`
  - 记录资料索引基础层已完成，明确尚未接入运行时事件和 Prompt 检索。

### 任务 1：索引契约测试

**文件：**
- 创建：`bridge/tests/test_profile_index.py`

- [x] **步骤 1：编写失败测试**

测试必须证明：

1. 两份 persona JSON 会保留 `npcId`、来源 Mod、显示名覆盖和来源文件名。
2. Content Patcher `Changes[].Entries` 会生成风格样本候选，`text` 保留 i18n 引用，记录 `sourceKey` 和 `sourcePath`。
3. 单个坏 JSON 只生成 warning，不阻断其他文件。
4. 输出中的路径只保留相对输入根的 POSIX 路径，不写入用户绝对路径。

示例断言接口：

```python
index = ProfileIndexBuilder(persona_dir).build([mod_root])

assert index["schemaVersion"] == 1
assert index["profiles"]["Sophia"]["sourceMods"] == ["SVE"]
assert index["styleSamples"][0]["text"] == "{{i18n:Sophia.CharacterDialogue.001}}"
assert index["styleSamples"][0]["sourceKey"] == "Introduction"
assert "C:\\Users" not in json.dumps(index, ensure_ascii=False)
assert any("invalid JSON" in warning for warning in index["warnings"])
```

- [x] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q bridge/tests/test_profile_index.py -p no:cacheprovider
```

预期：因 `ProfileIndexBuilder` 尚未定义而失败。

### 任务 2：实现索引器

**文件：**
- 创建：`bridge/src/stardew_ai_bridge/profile_index.py`

- [x] **步骤 1：实现最小 API**

公开接口固定为：

```python
class ProfileIndexBuilder:
    def __init__(self, persona_dir: str | Path) -> None: ...

    def build(self, mod_roots: Iterable[str | Path] = ()) -> dict[str, object]: ...

    @staticmethod
    def write(index: Mapping[str, object], output_path: str | Path) -> None: ...
```

索引固定包含：`schemaVersion`、`profiles`、`styleSamples`、`storyEvents`、`sources`、`warnings`。无有效资产时返回空集合，不抛出路径或 JSON 错误。

- [x] **步骤 2：运行定向测试确认通过**

使用任务 1 的命令，预期所有索引契约测试通过。

- [x] **步骤 3：Commit**

```powershell
git add bridge/src/stardew_ai_bridge/profile_index.py bridge/tests/test_profile_index.py
git commit -m "feat(资料索引): 添加人设与对白候选索引"
```

### 任务 3：添加命令行入口

**文件：**
- 创建：`scripts/build_profile_index.py`

- [x] **步骤 1：编写 CLI 测试**

测试通过 `subprocess.run` 调用脚本，传入临时 persona 目录、一个 Mod 根目录和临时输出文件，断言退出码为 0、输出 JSON 可解析且包含 schema 版本；输入目录不存在时断言退出码非 0，并且不创建输出文件。

- [x] **步骤 2：实现参数和安全写出**

命令格式：

```powershell
python scripts/build_profile_index.py `
  --persona-dir data/personas `
  --mod-root <已安装Mod目录> `
  --output data/generated/profile-index.json
```

脚本只写用户明确指定的输出路径，父目录不存在时创建；不复制或修改输入 Mod 文件。

- [x] **步骤 3：运行 CLI 与全量 Bridge 测试**

运行 CLI 的临时目录测试，然后运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q -p no:cacheprovider
```

预期：Bridge 全部通过；第三方弃用警告可以保留，但不能出现索引器异常。

- [x] **步骤 4：Commit**

```powershell
git add scripts/build_profile_index.py bridge/tests/test_profile_index.py
git commit -m "feat(资料索引): 添加离线构建命令"
```

### 任务 4：文档与交接

**文件：**
- 修改：`README.md`
- 修改：`docs/handoff-2026-08-23.md`

- [x] **步骤 1：记录运行方式与边界**

文档必须明确：索引是派生文件、来源键可回溯、i18n 文本不会自动变成已确认剧情事实，索引器尚未连接 SMAPI 存档生命周期和 Prompt 检索。

- [x] **步骤 2：运行最终验证并 Commit**

运行 Bridge 全量测试、CLI 临时目录测试和 `git diff --check`，然后提交：

```powershell
git add README.md docs/handoff-2026-08-23.md
git commit -m "docs(交接): 记录离线资料索引基础层"
```

## 计划自检

- 范围只覆盖离线资料索引，不混入运行时事件、存档写入、UI 或关系数值。
- 所有输入错误均降级为 warning 或非零 CLI 退出，不修改原始 Mod 资产。
- 风格证据和剧情候选使用不同集合，避免把对白文本误当作已确认事实。
- 输出路径只保留相对路径，避免把本机用户目录写入派生索引。
