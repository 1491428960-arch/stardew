# 角色质量案例编号与多轮推进实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 在当前 worktree 逐任务实现，并保留文档中的测试与验证记录。

**目标：** 为固定质量案例增加稳定编号、真实的多轮推进检查和更自然的婚后亲密场景，并在网页中同时呈现单轮与完整案例结果。

**架构：** 案例编号由 `quality_case_catalog()` 和评测结果按默认顺序派生；多轮推进由 `character_quality_eval.py` 的纯函数检查，脚本在生成完一整个案例后回写脱敏标签；`PromptBuilder` 只增加历史存在时的推进约束。案例浏览器沿用现有 API 和三栏工作台，结果读取器保留旧工件兼容。

**技术栈：** Python、pytest、现有 `PromptBuilder`、内嵌 HTML/CSS/JavaScript、Node `--check`。

---

### 任务 1：为编号、推进和婚后案例编写失败测试

**文件：**
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/tests/test_external_dialogue_lab.py`
- 修改：`bridge/tests/test_quality_results.py`（若现有文件已覆盖结果读取）

- [ ] **步骤 1：增加编号和序列评分断言**

在 `test_character_quality_eval.py` 增加以下行为断言：

```python
def test_quality_case_catalog_exposes_stable_one_based_numbers() -> None:
    cases = quality_case_catalog()
    assert [case["caseNumber"] for case in cases] == list(range(1, len(cases) + 1))
    assert cases[16]["caseId"] == "sebastian-married-life"


def test_progression_flags_adjacent_replies_that_only_repeat_previous_content() -> None:
    case = case_by_id("wizard-married-evening")
    scores = score_dialogue_progression(
        ["今晚先放下记录，陪我一会儿。", "今晚先放下记录，陪我一会儿。", "今晚先放下记录，陪我一会儿。"],
        case.dialogue_turns(),
    )
    assert scores[1]["repeated"] is True
    assert "repeated_turn_content" in scores[1]["tags"]


def test_progression_accepts_new_detail_and_explicit_shane_closing() -> None:
    case = case_by_id("shane-dating-boundary")
    scores = score_dialogue_progression(
        ["别逼我说这种话，今天真的没心情。", "行了，我先睡了。", "明天再说。"],
        case.dialogue_turns(),
    )
    assert all(score["repeated"] is False for score in scores)
```

- [ ] **步骤 2：增加婚后玩家输入质量断言**

断言五个婚后案例的三轮玩家输入不重复、至少分别包含陪伴/靠近/具体场景推进词，并且每个案例仍有双方自愿关系说明。

- [ ] **步骤 3：增加 Prompt 和页面契约断言**

Prompt 测试断言存在 `progression_guard` 且位于 `conversation_history` 之后；页面测试断言存在 `caseNumber`、`repeated_turn_content`、`passedTurns`、`passedCases` 和 `case-position`。

- [ ] **步骤 4：运行红灯测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py bridge/tests/test_prompts.py bridge/tests/test_external_dialogue_lab.py bridge/tests/test_quality_results.py
```

预期：新增编号、序列、Prompt 或页面断言至少有一项因功能缺失失败；若结果测试文件不存在，则只运行实际存在的三个文件并记录该事实。

### 任务 2：实现编号、推进纯函数和婚后案例定义

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 修改：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：实现稳定编号输出**

在 `quality_case_catalog()` 中使用 `enumerate(DEFAULT_CASES, start=1)` 输出 `caseNumber`；不在 dataclass 中手工保存编号。对外只输出脱敏案例字段。

- [ ] **步骤 2：实现相邻回复推进检查**

新增 `score_dialogue_progression(replies, turns)`，返回每轮 `repeated`、`novelExpectedTerms`、`overlap` 和 `tags`。规范化中文标点后用长度至少 2 的字符 n-gram 计算相邻重合；只有当前回复和上一回复明显重合且当前轮没有新 expected term 时打 `repeated_turn_content`，首轮或空/失败轮不打标签。将明确收口视为正常差异，不以回复长度判失败。

- [ ] **步骤 3：重写五个婚后案例的三轮文本**

只修改 `_BASE_CASES` 与 `_FOLLOW_UP_TURNS` 中对应案例的测试输入、关系说明、剧情说明、expected/forbidden terms；保持 `caseId`、角色 ID、来源 Mod、三轮结构、成人同意边界不变。保证 #17、#25、#27、#30、#32 的玩家输入从意图到行动再到靠近/收口有明显递进。

- [ ] **步骤 4：运行定向测试确认通过**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py
```

预期：案例编号、推进纯函数和婚后输入断言全部通过。

### 任务 3：接入序列评分和单轮/完整案例统计

**文件：**
- 修改：`scripts/run_character_quality_eval.py`
- 修改：`bridge/src/stardew_ai_bridge/quality_results.py`
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`bridge/tests/test_external_dialogue_lab.py`

- [ ] **步骤 1：在生成完每个案例后应用推进标签**

收集 `turn_records` 中成功回复，调用 `score_dialogue_progression`，把标签并入对应轮次的 `score.tags`，更新对应轮次 `score.passed=False`，并写入 `progression`。为案例写入 `caseNumber`、`passedTurnCount`、`failedTurnCount`、`casePassed`，不把 Provider 失败伪装成通过。

- [ ] **步骤 2：扩展摘要并保持旧字段**

摘要继续保留 `passed` 作为完整案例通过数，同时增加 `passedCases`、`passedTurns`、`turnPassRate`、`casePassRate`。比例在总数为零时为 `0.0`，不使用 NaN 或无穷值。

- [ ] **步骤 3：扩展脱敏结果读取**

`quality_results.py` 只保留编号、非负统计、布尔标志和短标签；旧工件没有新增字段时照常返回，不透传 prompt、API key、Token 字符串字段以外的敏感内容。

- [ ] **步骤 4：运行结果与评测定向测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py bridge/tests/test_external_dialogue_lab.py bridge/tests/test_quality_results.py
```

预期：新增统计被保留且所有敏感字段断言通过。

### 任务 4：增加历史推进 Prompt 约束

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`bridge/tests/test_prompts.py`

- [ ] **步骤 1：实现 `progression_guard` 卡**

仅在存在 assistant 历史时添加 system 消息，内容明确要求当前续聊新增一个具体进展或明确收口，禁止同义改写；不复制完整历史，不新增角色事实。

- [ ] **步骤 2：运行 Prompt 定向回归**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py
```

预期：Prompt 顺序和阶段约束测试全部通过。

### 任务 5：更新案例浏览器并做静态验证

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 修改：`bridge/src/stardew_ai_bridge/quality_results.py`
- 修改：`bridge/tests/test_external_dialogue_lab.py`

- [ ] **步骤 1：显示案例编号**

列表、详情标题、共享上下文栏和定位工具条显示 `#caseNumber`；定位栏在筛选后仍显示“当前筛选中的第几条 / 总数”，不把筛选位置当全局编号。

- [ ] **步骤 2：显示序列质量和统计**

详情每轮显示推进标签；批次卡和覆盖面板同时显示单轮通过数/比例、完整案例通过数/比例。旧批次缺字段时显示“未检测”，不能显示为通过。

- [ ] **步骤 3：运行页面契约与 JavaScript 语法检查**

运行页面定向测试，并从 HTML 提取所有脚本执行 `node --check`；随后运行 `git diff --check`。

### 任务 6：完整回归、重启 Bridge、生成独立批次并浏览器核对

**文件：**
- 修改：`docs/active-work.md`
- 创建：`artifacts/character-quality-eval/20260901-case-number-progression-cloud/`（运行生成，不覆盖旧目录）

- [ ] **步骤 1：运行 Bridge 完整测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests
```

预期：0 failed，记录实际通过数和警告数。

- [ ] **步骤 2：重启并确认当前 worktree Bridge**

只操作当前 worktree 对应的 Bridge；按 PID 检查 PowerShell 包装器和真正监听 5678 的 Python 子进程命令行都指向 `story-memory`。检查 `/health`、`/test`、`/api/quality/cases`、`/api/quality/results`，不打印任何 key。

- [ ] **步骤 3：用当前默认云端 Qwen 生成独立批次**

使用项目现有 `.env.local` 和默认 `cloud` 评测入口，输出到新目录；记录实际案例数、轮数、请求数和输入/输出/合计 Token。若云端失败，保留错误工件并如实报告，不改用其他模型冒充本批次。

- [ ] **步骤 4：浏览器查看重点案例**

打开 `/test?case=...`，检查 #17、#25、#27、#30、#32 的三轮完整 transcript、玩家输入、NPC 回复、序列标签和统计；需要截图时同时检查实际渲染，不把 HTTP 200 当作视觉验证。

- [ ] **步骤 5：更新活动记录并汇报边界**

追加实际验证数字、批次 ID、Bridge 健康状态、浏览器检查范围和当前未做的游戏验证。明确本轮只验证网页/Bridge 质量评测，不声明游戏加载新 DLL。
