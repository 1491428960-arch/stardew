# Rasmodia/Wizard 角色语料与说话风格实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ] `）语法来跟踪进度。

**目标：** 建立原版 Wizard、SVE Wizard 和 Rasmodia 的本地语料、来源优先级、背景事实与说话风格检索链路，并用测试证明未确认剧情不会进入确定事实回复。

**架构：** 在现有 `ProfileIndexBuilder` 前增加可追溯的语料记录与确定性语气分析层；索引同时保留旧版 `styleSamples`/`storyEvents`，并增加带来源的 `speechEvidence`、`voiceCards`、`knowledgeFacts`。`ContextBuilder` 只投影当前关系阶段和当前场景需要的少量证据，`PromptBuilder` 将它们放入独立的安全消息。

**技术栈：** Python 3.12、标准库 `json`/`pathlib`/`collections`、pytest、现有 FastAPI Bridge；原版 XNB 先由外部工具解包为 JSON，仓库脚本只读取解包后的本地资源和 Content Patcher JSON。

---

## 文件职责锁定

### 创建

- `bridge/src/stardew_ai_bridge/corpus.py`：解析 Content Patcher 和解包后的原版对白，生成统一语料记录、条件标签和来源 warning。
- `bridge/src/stardew_ai_bridge/speech.py`：对语料记录做确定性语气特征统计，生成受限 `voiceCard`。
- `bridge/tests/test_corpus.py`：语料解析、来源、条件和路径隔离测试。
- `bridge/tests/test_speech.py`：语气特征统计和样本上限测试。
- `bridge/tests/test_rasmodia_evaluation.py`：Wizard/Rasmodia 的关系阶段、知识边界和 Prompt 回归场景。
- `scripts/export_dialogue_corpus.py`：从解包后的 vanilla 根目录和 Mod 根目录导出本地 `data/generated/rasmodia-corpus.json`。

### 修改

- `bridge/src/stardew_ai_bridge/profile_index.py`：接入统一语料记录，扩展索引 schema 和只读检索，保留旧字段兼容性。
- `bridge/src/stardew_ai_bridge/prompts.py`：投影 `voiceCard`、`speechEvidence`、`knowledgeFacts`，限制数量并保留知识边界。
- `scripts/build_profile_index.py`：增加 `--corpus` 和 `--vanilla-root` 参数，输出新索引统计。
- `data/personas/rasmodia.json`：补充审阅后的背景时间线、知识事实和语气证据引用；保留 `Wizard` 与 `Rasmodia` 两个兼容 ID。
- `bridge/tests/test_profile_index.py`：补充 schema v2、来源优先级和事实检索测试。
- `bridge/tests/test_profile_context.py`：补充上下文投影字段和数量上限测试。
- `bridge/tests/test_prompts.py`：补充独立 Prompt 消息和未知事实保护测试。
- `.gitignore`：确认 `data/generated/rasmodia-corpus.json`、本地解包目录和中间文件不会进入 Git。

### 不修改

- `smapi/`：本计划只改变 Bridge 资料和 Prompt 投影，不改变游戏状态、NPC 位置或房屋入口逻辑。
- `data/generated/` 中已有本机索引：实现完成后由命令重新生成，不手工编辑，也不加入提交。

---

### 任务 1：建立统一语料记录和 Content Patcher 解析器

**文件：**
- 创建：`bridge/src/stardew_ai_bridge/corpus.py`
- 创建：`bridge/tests/test_corpus.py`
- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`

- [ ] **步骤 1：编写失败测试，锁定记录字段和条件标签**

在 `bridge/tests/test_corpus.py` 写入：

~~~python
from stardew_ai_bridge.corpus import extract_content_patcher_dialogue


def test_extract_dialogue_keeps_provenance_and_stage() -> None:
    payload = {
        "Changes": [
            {
                "Action": "EditData",
                "Target": "Characters/Dialogue/MarriageDialogueRasmodia",
                "Entries": {
                    "Rain": "雨天适合留在塔里。",
                },
            },
        ],
    }

    records, warnings = extract_content_patcher_dialogue(
        payload,
        source_mod="Dacar.SeasRomRasmodia",
        source_path="assets/Dialogue.json",
    )

    assert warnings == []
    assert records == [
        {
            "sampleId": "Dacar.SeasRomRasmodia:assets/Dialogue.json:Rain",
            "npcId": "Rasmodia",
            "sourceMod": "Dacar.SeasRomRasmodia",
            "sourcePath": "assets/Dialogue.json",
            "sourceKey": "Rain",
            "text": "雨天适合留在塔里。",
            "evidenceKind": "marriage_dialogue",
            "conditions": {"relationshipStage": "married"},
        },
    ]
~~~

- [ ] **步骤 2：运行测试确认失败**

运行：

~~~powershell
$env:PYTHONPATH = "$PWD/bridge/src"
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_corpus.py::test_extract_dialogue_keeps_provenance_and_stage -q -p no:cacheprovider
~~~

预期：FAIL，报错为 `ModuleNotFoundError: No module named 'stardew_ai_bridge.corpus'`。

- [ ] **步骤 3：实现最小解析器**

在 `corpus.py` 定义以下公开函数，并让它们只返回相对来源路径：

~~~python
def extract_content_patcher_dialogue(
    payload: Mapping[str, Any],
    *,
    source_mod: str,
    source_path: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """提取 EditData/Characters/Dialogue/*，保留 sourceKey 和条件。"""


def classify_dialogue_target(target: str) -> tuple[str, str]:
    """返回 (npc_id, evidence_kind)，无法识别时返回 ("", "")。"""


def infer_dialogue_conditions(target: str, source_key: str) -> dict[str, str]:
    """从 MarriageDialogue、RoommateDialogue 和 key 前缀提取稳定条件。"""
~~~

解析规则固定为：

- 只接受 `Action == "EditData"`；
- 只处理 `Characters/Dialogue/` 前缀；
- `MarriageDialogueX` 和 `RoommateDialogueX` 去掉前缀后得到 `X`；
- 空文本和非字符串值跳过；
- i18n 引用保留原文，不展开、不翻译；
- `sampleId` 使用 `sourceMod:sourcePath:sourceKey`；
- `sourcePath` 通过 `Path(source_path).as_posix()` 规范化，禁止写入盘符或绝对路径。

- [ ] **步骤 4：运行解析器测试**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_corpus.py -q -p no:cacheprovider
~~~

预期：解析器测试 PASS。

- [ ] **步骤 5：让现有索引调用统一解析器**

在 `ProfileIndexBuilder._extract_dialogue_changes` 中把当前重复的 target/Entries 逻辑替换为：

~~~python
records, warnings = extract_content_patcher_dialogue(
    payload,
    source_mod=source_mod,
    source_path=source_path,
)
samples.extend(records)
index_warnings.extend(warnings)
~~~

方法签名增加 `index_warnings: list[str]`，并在调用处传入现有 `warnings`。`styleSamples` 继续保留旧字段；新增的 `conditions` 和 `evidenceKind` 允许 Prompt 层选择更精确样本。

- [ ] **步骤 6：运行旧索引回归并提交**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_profile_index.py -q -p no:cacheprovider
~~~

预期：原有 profile、i18n、婚后对白和绝对路径测试全部 PASS。提交：

~~~powershell
git add bridge/src/stardew_ai_bridge/corpus.py bridge/src/stardew_ai_bridge/profile_index.py bridge/tests/test_corpus.py bridge/tests/test_profile_index.py
git commit -m "feat: 统一角色对白语料记录"
~~~

### 任务 2：扩展索引并实现来源优先级检索

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`
- 修改：`bridge/tests/test_profile_index.py`
- 修改：`bridge/tests/test_profile_context.py`

- [ ] **步骤 1：编写失败测试，锁定 schema v2 和事实边界**

在 `test_profile_index.py` 增加：

~~~python
def test_index_v2_keeps_fact_provenance_and_excludes_unverified_by_default(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {
            "mod": "vanilla",
            "personas": {
                "Wizard": {
                    "knowledgeFacts": [
                        {
                            "factId": "tower-residence",
                            "summary": "居住并工作的地点是法师塔。",
                            "knowledgeScope": "canon_confirmed",
                            "confidence": "high",
                            "sourceRefs": ["vanilla:Wizard:Tower"],
                        },
                        {
                            "factId": "unverified-rumor",
                            "summary": "没有来源的传闻。",
                            "knowledgeScope": "unverified",
                            "confidence": "low",
                            "sourceRefs": [],
                        },
                    ],
                },
            },
        },
    )

    index = ProfileIndexBuilder(persona_dir).build()

    assert index["schemaVersion"] == 2
    assert index["knowledgeFacts"] == [
        {
            "factId": "tower-residence",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "summary": "居住并工作的地点是法师塔。",
            "knowledgeScope": "canon_confirmed",
            "confidence": "high",
            "sourceRefs": ["vanilla:Wizard:Tower"],
        },
    ]
~~~

- [ ] **步骤 2：运行测试确认失败**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_profile_index.py::test_index_v2_keeps_fact_provenance_and_excludes_unverified_by_default -q -p no:cacheprovider
~~~

预期：FAIL，`schemaVersion` 仍为 `1`，且不存在 `knowledgeFacts`。

- [ ] **步骤 3：实现 v2 索引字段和事实归一化**

在 `ProfileIndexBuilder.build` 的初始索引中增加：

~~~python
index = {
    "schemaVersion": 2,
    "profiles": {},
    "styleSamples": [],
    "speechEvidence": [],
    "voiceCards": {},
    "knowledgeFacts": [],
    "storyEvents": [],
    "sources": [],
    "warnings": [],
}
~~~

从 persona 的 `knowledgeFacts` 读取时，补齐 `npcId`、`sourceMod`，只接受 `canon_confirmed`、`runtime_confirmed`、`player_provided` 三类事实进入默认列表；`inferred_style` 只进入语气分析输入，`unverified` 只进入 warning 统计，不进入 `knowledgeFacts`。

新增只读方法：

~~~python
def knowledge_facts(
    self,
    npc_id: str,
    source_mods: Iterable[str],
    *,
    limit: int = 8,
    completed_event_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    return []
~~~

方法必须复用 `_source_matches`，上限固定为 8，并在 `ProfileIndexStore._load` 中接受 schema `1` 和 `2`；schema `1` 缺失的新字段按空列表兼容读取。

- [ ] **步骤 4：增加来源优先级测试并实现排序**

在 `test_profile_context.py` 写入 vanilla/SVE/Rasmodia 同一 `factId` 的 fixture，断言排序为：

~~~python
assert [item["sourceMod"] for item in store.knowledge_facts(
    "Wizard", ["SVE", "Romanceable Rasmodius"]
)] == ["Romanceable Rasmodius", "SVE", "vanilla"]
~~~

实现 `_source_priority(source_mod: str) -> int`，返回 Rasmodia `30`、SVE `20`、vanilla `10`、其他 `0`；相同优先级保持文件顺序，不覆盖来源。

- [ ] **步骤 5：运行索引与上下文测试并提交**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_profile_index.py bridge/tests/test_profile_context.py -q -p no:cacheprovider
~~~

预期：新旧索引读取、来源排序、完成事件状态和绝对路径隔离测试全部 PASS。提交：

~~~powershell
git add bridge/src/stardew_ai_bridge/profile_index.py bridge/tests/test_profile_index.py bridge/tests/test_profile_context.py
git commit -m "feat: 增加角色事实索引与来源优先级"
~~~

### 任务 3：实现确定性语气分析并补 Rasmodia 审阅资料

**文件：**
- 创建：`bridge/src/stardew_ai_bridge/speech.py`
- 创建：`bridge/tests/test_speech.py`
- 修改：`data/personas/rasmodia.json`
- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`

- [ ] **步骤 1：编写失败测试，锁定语气卡输出**

在 `test_speech.py` 写入：

~~~python
from stardew_ai_bridge.speech import derive_speech_profile


def test_derive_speech_profile_reports_markers_and_capped_evidence() -> None:
    samples = [
        {"sampleId": "a", "text": "也许这只是星界能量的回响。", "sourceMod": "vanilla"},
        {"sampleId": "b", "text": "魔法需要边界，旅行者。", "sourceMod": "SVE"},
        {"sampleId": "c", "text": "当然，我并不打算把猜测称作预言。", "sourceMod": "Rasmodia"},
    ]

    card = derive_speech_profile("Rasmodia", samples, max_evidence=2)

    assert card["npcId"] == "Rasmodia"
    assert card["features"]["uncertaintyMarkers"] >= 1
    assert card["features"]["magicMarkers"] >= 1
    assert card["evidenceRefs"] == ["a", "b"]
~~~

- [ ] **步骤 2：运行测试确认失败**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_speech.py -q -p no:cacheprovider
~~~

预期：FAIL，报错为 `ModuleNotFoundError: No module named 'stardew_ai_bridge.speech'`。

- [ ] **步骤 3：实现固定词表和样本上限**

在 `speech.py` 定义：

~~~python
def derive_speech_profile(
    npc_id: str,
    samples: Iterable[Mapping[str, Any]],
    *,
    max_evidence: int = 6,
) -> dict[str, Any]:
    """只做可复现统计，不把统计结论当成剧情事实。"""
~~~

固定词表包括：不确定性 `也许/或许/可能/不确定/无法断言`、魔法 `魔法/星界/法术/仪式/能量`、边界 `秘密/风险/边界/同意` 和干燥幽默 `当然/显然/可惜/真是`。输出必须包含 `npcId`、`features`、`topicHints`、`evidenceRefs`；`evidenceRefs` 按输入顺序截断，不复制原始文本。

- [ ] **步骤 4：将语气卡接入索引**

在 `ProfileIndexBuilder.build` 完成语料收集后，对每个 NPC 调用：

~~~python
voice_cards[npc_id] = derive_speech_profile(
    npc_id,
    speech_evidence_for_npc,
    max_evidence=6,
)
~~~

仅把统计卡和引用写入 `voiceCards`，保留 `speechEvidence` 原文来源；`ProfileIndexStore.voice_card(npc_id)` 返回深拷贝，避免调用方修改缓存。

- [ ] **步骤 5：补 Rasmodia 的审阅字段**

在 `data/personas/rasmodia.json` 的 `Wizard` 与 `Rasmodia` 两个入口中补充同一份经过审阅的结构：

~~~json
"biography": [
  {"factId": "tower-residence", "summary": "居住并工作的地点是法师塔。", "sourceRefs": ["vanilla:Wizard:Tower"]},
  {"factId": "magic-research", "summary": "日常围绕魔法研究与星界现象展开。", "sourceRefs": ["vanilla:Wizard:Research"]}
],
"knowledgeFacts": [
  {"factId": "tower-residence", "summary": "居住并工作的地点是法师塔。", "knowledgeScope": "canon_confirmed", "confidence": "high", "sourceRefs": ["vanilla:Wizard:Tower"]},
  {"factId": "magic-research", "summary": "日常围绕魔法研究与星界现象展开。", "knowledgeScope": "canon_confirmed", "confidence": "high", "sourceRefs": ["vanilla:Wizard:Research"]}
],
"voiceEvidenceRefs": ["vanilla:Wizard:Introduction", "SVE:Wizard:Research", "Rasmodia:Dialogue:Boundary"]
~~~

不把未触发的关系、事件结果或他人秘密写入静态事实；关系阶段仍由运行时状态决定。

- [ ] **步骤 6：运行语气与 Persona 回归并提交**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_speech.py bridge/tests/test_prompts.py -q -p no:cacheprovider
~~~

预期：语气卡统计、Rasmodia 两个 ID、未启用 Mod 不覆盖原版显示名的测试全部 PASS。提交：

~~~powershell
git add bridge/src/stardew_ai_bridge/speech.py bridge/src/stardew_ai_bridge/profile_index.py bridge/tests/test_speech.py bridge/tests/test_prompts.py data/personas/rasmodia.json
git commit -m "feat: 建立 Rasmodia 语气卡与背景事实"
~~~

### 任务 4：把语气和事实投影到 Context/Prompt

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`bridge/tests/test_profile_context.py`
- 修改：`bridge/tests/test_prompts.py`

- [ ] **步骤 1：编写失败测试，锁定阶段和数量上限**

在 `test_profile_context.py` 增加：

~~~python
def test_context_projects_one_voice_card_and_capped_evidence(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(json.dumps({
        "schemaVersion": 2,
        "profiles": {},
        "styleSamples": [],
        "speechEvidence": [
            {"sampleId": str(i), "npcId": "Wizard", "sourceMod": "vanilla", "text": f"样本{i}"}
            for i in range(12)
        ],
        "voiceCards": {"Wizard": {"npcId": "Wizard", "features": {"magicMarkers": 3}}},
        "knowledgeFacts": [],
        "storyEvents": [],
        "sources": [],
        "warnings": [],
    }, ensure_ascii=False), encoding="utf-8")

    context = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    ).build("Wizard", source_mods=["vanilla"], relationshipStage="friend")

    assert context["voiceCard"]["features"]["magicMarkers"] == 3
    assert len(context["speechEvidence"]) <= 6
    assert "stageProfiles" not in context["npcIdentity"]
~~~

- [ ] **步骤 2：运行测试确认失败**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_profile_context.py::test_context_projects_one_voice_card_and_capped_evidence -q -p no:cacheprovider
~~~

预期：FAIL，`ContextBuilder` 尚未返回 `voiceCard` 和 `speechEvidence`。

- [ ] **步骤 3：实现 ContextBuilder 投影**

在 `ContextBuilder.build` 的 profile index 分支中增加：

~~~python
voice_card = self.profile_index.voice_card(str(npc_id))
speech_evidence = self.profile_index.speech_evidence(
    str(npc_id),
    source_mod_list,
    relationship_stage=game_state.get("relationshipStage", ""),
    limit=6,
)
knowledge_facts = self.profile_index.knowledge_facts(
    str(npc_id), source_mod_list, limit=8,
)
if voice_card:
    context["voiceCard"] = voice_card
if speech_evidence:
    context["speechEvidence"] = speech_evidence
if knowledge_facts:
    context["knowledgeFacts"] = knowledge_facts
~~~

所有检索结果先经过现有 `_sanitize_value`，并只投影一个当前 `stageProfile`；不能把整个 `stageProfiles` 显示给 Provider。

- [ ] **步骤 4：实现 Prompt 独立消息和未知事实保护**

在 `PromptBuilder.build` 中新增三个可选系统消息：

~~~python
messages.append({
    "role": "system",
    "name": "voice_card",
    "content": _json({"voiceCard": safe_context["voiceCard"]}),
})
messages.append({
    "role": "system",
    "name": "speech_evidence",
    "content": _json({"speechEvidence": safe_context["speechEvidence"][:6]}),
})
messages.append({
    "role": "system",
    "name": "knowledge_facts",
    "content": _json({
        "knowledgeFacts": safe_context["knowledgeFacts"][:8],
        "instruction": "只能把 knowledgeScope 为 canon_confirmed、runtime_confirmed 或 player_provided 的内容当作已知事实；其余内容必须保留不确定性。",
    }),
})
~~~

消息只在对应字段非空时加入；所有文本继续执行 Secret label 清理和长度截断。

- [ ] **步骤 5：增加 Prompt 回归测试并提交**

在 `test_prompts.py` 断言：

~~~python
names = [message["name"] for message in PromptBuilder().build(context, "你知道那件事吗？")]
assert names.index("voice_card") < names.index("conversation_history")
assert "knowledgeScope" in rendered_prompt
assert "未确认" in rendered_prompt or "不确定性" in rendered_prompt
~~~

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_profile_context.py bridge/tests/test_prompts.py bridge/tests/test_game_context_contract.py -q -p no:cacheprovider
~~~

预期：Context/Prompt、输入清理、历史限制和 API contract 测试全部 PASS。提交：

~~~powershell
git add bridge/src/stardew_ai_bridge/prompts.py bridge/tests/test_profile_context.py bridge/tests/test_prompts.py bridge/tests/test_game_context_contract.py
git commit -m "feat: 将角色语气与知识边界投影到 Prompt"
~~~

### 任务 5：增加本地语料导出命令

**文件：**
- 创建：`scripts/export_dialogue_corpus.py`
- 修改：`scripts/build_profile_index.py`
- 修改：`.gitignore`
- 创建：`bridge/tests/test_corpus_cli.py`

- [ ] **步骤 1：编写 CLI 失败测试**

测试准备一个 `vanilla/Characters/Dialogue/Wizard.json` 和一个带 manifest 的 SVE Content Patcher 根目录，执行：

~~~python
result = subprocess.run(
    [
        sys.executable,
        str(script),
        "--vanilla-root", str(vanilla_root),
        "--mod-root", str(sve_root),
        "--output", str(output),
    ],
    cwd=PROJECT_ROOT,
    capture_output=True,
    text=True,
    check=False,
)
assert result.returncode == 0
payload = json.loads(output.read_text(encoding="utf-8"))
assert payload["schemaVersion"] == 1
assert {record["sourceMod"] for record in payload["records"]} == {"vanilla", "FlashShifter.SVECode"}
assert str(tmp_path) not in output.read_text(encoding="utf-8")
~~~

- [ ] **步骤 2：运行测试确认失败**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_corpus_cli.py -q -p no:cacheprovider
~~~

预期：FAIL，`scripts/export_dialogue_corpus.py` 不存在。

- [ ] **步骤 3：实现本地导出命令**

命令参数固定为：

~~~text
--vanilla-root PATH   已解包的 Content/Characters/Dialogue 根目录
--mod-root PATH       可重复指定的 Mod 根目录
--output PATH         必填，明确指定的 generated 输出文件
~~~

vanilla 根目录的 `*.json` 按文件名作为 NPC ID，sourceMod 固定为 `vanilla`；Mod 根目录复用 manifest UniqueID 和 `extract_content_patcher_dialogue`。遇到 `.xnb` 时输出明确 warning：`xnb source requires unpacked JSON`，退出码仍为 0，但 warning 写入 JSON，避免伪装成完整采集。

- [ ] **步骤 4：让 build_profile_index 读取 corpus**

为 `scripts/build_profile_index.py` 增加可重复参数：

~~~python
parser.add_argument("--corpus", action="append", default=[], type=Path)
parser.add_argument("--vanilla-root", type=Path)
~~~

构建命令读取 `--corpus` 后把 `records` 合并进 `speechEvidence` 和旧 `styleSamples`，并打印：

~~~text
profile index written: data/generated/profile-index.json profiles=2 styleSamples=4 speechEvidence=4 knowledgeFacts=2 warnings=0
~~~

- [ ] **步骤 5：运行 CLI 测试并提交**

运行：

~~~powershell
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_corpus_cli.py bridge/tests/test_profile_index.py -q -p no:cacheprovider
~~~

预期：CLI、缺少输入目录、解包 XNB warning、索引输出和路径隔离测试全部 PASS。确认 `.gitignore` 包含：

~~~text
data/generated/rasmodia-corpus.json
data/generated/unpacked-vanilla/
~~~

提交：

~~~powershell
git add scripts/export_dialogue_corpus.py scripts/build_profile_index.py bridge/tests/test_corpus_cli.py .gitignore
git commit -m "feat: 增加本地角色语料导出命令"
~~~

### 任务 6：完成 Rasmodia 评测和本机索引验证

**文件：**
- 创建：`bridge/tests/test_rasmodia_evaluation.py`
- 修改：`docs/handoff-2026-08-23.md`

- [ ] **步骤 1：编写四组黄金场景测试**

场景固定为：初识问候、朋友阶段研究话题、亲近阶段危险魔法、未触发秘密追问。测试只断言结构和边界，不锁死 Provider 的自然语言措辞：

~~~python
def test_rasmodia_never_projects_unverified_story_fact() -> None:
    index_path = PROJECT_ROOT / "data" / "generated" / "profile-index.json"
    persona_dir = PROJECT_ROOT / "data" / "personas"
    context = ContextBuilder(
        PersonaStore(persona_dir),
        ProfileIndexStore(index_path),
    ).build(
        "Wizard",
        source_mods=["SVE", "Romanceable Rasmodius"],
        relationshipStage="close",
        recentFacts=["玩家确认今天下雨"],
    )
    rendered = json.dumps(
        PromptBuilder().build(context, "告诉我那件未发生的秘密"),
        ensure_ascii=False,
    )
    assert "unverified" not in rendered
    assert "不能把未确认内容当作事实" in rendered or "不确定性" in rendered
~~~

- [ ] **步骤 2：运行 Bridge 全量测试**

运行：

~~~powershell
$env:PYTHONPATH = "$PWD/bridge/src"
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests -q -p no:cacheprovider
~~~

预期：全部测试 PASS；允许现有 Starlette/httpx deprecation warning，但不能出现失败或绝对路径泄露。

- [ ] **步骤 3：生成本机语料和索引**

先使用外部 XNB 解包工具把本机 vanilla `Content/Characters/Dialogue` 输出到 `data/generated/unpacked-vanilla/`，再运行：

~~~powershell
$env:PYTHONPATH = "$PWD/bridge/src"
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/export_dialogue_corpus.py `
  --vanilla-root data/generated/unpacked-vanilla/Characters/Dialogue `
  --mod-root 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest\[CP] Romanceable Rasmodia' `
  --output data/generated/rasmodia-corpus.json
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/build_profile_index.py `
  --persona-dir data/personas `
  --corpus data/generated/rasmodia-corpus.json `
  --mod-root 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest\[CP] Romanceable Rasmodia' `
  --output data/generated/profile-index.json
~~~

预期：输出 `schemaVersion=2`，统计中出现 `speechEvidence` 和 `knowledgeFacts`，warnings 明确反映任何未解包或缺失来源；生成文件不包含 `C:\`、`D:\` 或 `E:\` 绝对路径。

- [ ] **步骤 4：更新交接记录并提交**

在 `docs/handoff-2026-08-23.md` 增加实际运行日期、语料来源数量、Rasmodia 事实数量、语气证据数量和未解决 warning；不写入原始对白全文和本机绝对路径。运行：

~~~powershell
git diff --check
git status --short
git diff -- docs/handoff-2026-08-23.md
~~~

确认只提交测试、源码和交接摘要，不提交 `data/generated/`，然后提交：

~~~powershell
git add bridge/tests/test_rasmodia_evaluation.py docs/handoff-2026-08-23.md
git commit -m "test: 完成 Rasmodia 语料链路评测"
~~~

## 规格覆盖自检

- 来源分层与覆盖关系：任务 2、任务 3、任务 6。
- 原始语料记录与条件标签：任务 1、任务 5。
- 背景事实、可信度与知识范围：任务 2、任务 3、任务 4。
- Rasmodia 语气特征与代表样本：任务 3、任务 4。
- Prompt 最小投影与关系阶段：任务 4。
- 缺失资源、i18n、绝对路径和未确认事实边界：任务 1、任务 2、任务 5、任务 6。
- 自动测试与人工验收准备：任务 6 及各任务的 TDD 步骤。

## 计划自检结果

- 计划内容均为具体操作、代码接口、命令和预期结果，没有空泛占位步骤。
- 所有新增函数名、索引字段名和测试访问路径在前置任务中定义后再被后续任务使用。
- 旧版 `styleSamples`、`storyEvents` 和 schema v1 读取保持兼容，避免已有 FastTest 运行时因索引升级中断。
- 原版 XNB 解析明确放在外部解包输入边界内，Bridge 不引入大型二进制解析依赖。
- 每个任务都包含失败测试、最小实现、验证命令和独立提交点。
