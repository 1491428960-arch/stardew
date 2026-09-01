# SVE原文采集与i18n解析

日期：2026-08-26
研究问题：SVE原文采集与i18n解析

## 结论

SVE 原文可以直接从 Stardrop 的完整 profile 资源目录采集，不需要从运行中的游戏窗口 OCR，也不需要重新下载 Mod。

本机已确认以下内容包可用：

- `[CP] Stardew Valley Expanded`，manifest 版本 `1.15.11`，UniqueID 为 `FlashShifter.StardewValleyExpandedCP`；
- `[CP] Romanceable Rasmodius SVE`，manifest 版本 `1.6.3`，UniqueID 为 `Parrot.RomRas`。

Content Patcher 的对白文件大多只保存 `{{i18n:...}}` 引用，真正的英文/中文原文在对应内容包的 `i18n/default.json`、`i18n/zh.json` 中。因此完整采集必须分两层：保留原始对白键和来源，同时解析出 `resolvedText` 供 profile index 和模型上下文使用。

原版对白则通过官方 `StardewXnbHack` 解包 `Content/Characters/Dialogue` 后采集；本机 Stardew Valley 1.6.15 解包得到 624 个语言版本 JSON（52 个角色文件 × 12 种语言）。整份 `Content (unpacked)` 不进入项目，只有对话 JSON 复制到 ignored 工件目录；构建中文索引时只选择 `*.zh-CN.json`，无对应文件才回退无后缀文件。

本轮实测得到 3,807 条对白记录，其中 3,785 条是 i18n 引用，3,756 条已完整解析为实际文本；剩余 29 条仍含季节、随机数、事件或表达式运行时键，静态阶段不猜测唯一结果。其中 25 条已经记录了真实 i18n 键族候选，4 条没有可独立枚举的目录键。

## 判断依据

### 来源事实

1. SVE 官方仓库公开了 Content Patcher 内容包结构；本机安装目录中的 manifest 与该结构一致。
2. SVE 的 `assets/CharacterFiles/Dialogue/**`、`assets/Dialogue/**` 文件通过 `EditData -> Characters/Dialogue/<NPC>` 注入对白；`i18n/default.json` 和 `i18n/zh.json` 保存对应文本。
3. `SVECode` 和 `SVE-FTM` 主要是代码/农场类型资产，不是主要对白来源；采集对白时以 `[CP] Stardew Valley Expanded` 为主，研究 Rasmodius 时再叠加 `Parrot.RomRas`。

### 项目实现

- [corpus.py](../bridge/src/stardew_ai_bridge/corpus.py) 新增 i18n 解析：语言优先级为 `zh-CN → zh → default`，支持大小写差异、带空格键名和 `{{expressionList}}` 嵌套形式。
- 原始 `text` 不被覆盖；只有成功解析时增加 `resolvedText`，保留 `sampleId`、`sourceMod`、`sourcePath`、`sourceKey` 和条件信息。
- 对无法唯一解析的动态引用，`corpus.py` 增加 `dynamicCandidates`：按动态键前缀收集真实目录键和值，每个键族最多 24 条，保留可审计候选但不伪造最终句子。
- [profile_index.py](../bridge/src/stardew_ai_bridge/profile_index.py) 构建索引时优先使用 `resolvedText`；仍含动态占位符的记录保留原始表达式作为未确认证据，不伪装成最终句子。
- [export_dialogue_corpus.py](../scripts/export_dialogue_corpus.py) 增加 `--locale` 参数，默认 `zh-CN`。
- [runtime_samples.py](../bridge/src/stardew_ai_bridge/runtime_samples.py) 定义运行时 JSONL：每条记录带 `sourceSampleId`、实际已解析 `text`、`candidateKey`、条件和有限游戏状态；未解析 `{{i18n:...}}` 会被拒绝，内容哈希保证重复采样幂等。
- [profile_index.py](../bridge/src/stardew_ai_bridge/profile_index.py) 和 [build_profile_index.py](../scripts/build_profile_index.py) 支持 `--runtime-samples`，将 `runtime_dialogue` 作为独立证据层合并，不覆盖原始 corpus。
- [RuntimeDialogueSampler.cs](../smapi/RuntimeDialogueSampler.cs) 在原版 `DialogueBox` 打开时输出结构化 Trace 标记；[import_smapi_runtime_samples.py](../scripts/import_smapi_runtime_samples.py) 将 SMAPI 日志导入上述 JSONL。
- 导入器支持可选 `--corpus`：仅当 NPC、`sourceKey`、已解析文本在 corpus 中唯一命中时，才把 `runtime.unattributed` 补回静态 `sourceMod/sourcePath`，并写入 `attribution`；多重命中保持未归属。
- `ProfileIndexStore` 会过滤仍含 `{{i18n:...}}` 的审计记录，并将 `runtime_dialogue` 排在静态候选之前，避免模型把模板当成台词或忽略实况证据。

### 个人推断

静态解析适合建立“角色语气与背景资料库”，但不能还原所有运行时最终句子。随机、季节、婚姻、事件和 `expressionList` 等动态键必须保留原始表达式，后续再用游戏运行时导出或人工抽样补齐。

### 动态候选集

动态候选集不是运行时真值，而是从同一内容包的 i18n 目录反查出的证据集合：

- `{{Random:...}}`、季节、日期等动态键按前缀枚举同族键；多分支对白按键族分别限量，避免一个分支遮住另一个分支；
- 候选对象只包含 `key` 和对应语言优先级下的 `text`，不写入 profile index 的模型样本；
- 本轮 29 条未唯一解析记录中，25 条有候选集；4 条（包括 `AnnouncePregnancy {{expressionList}}` 和带别名的 `expressionList`）没有可独立枚举的目录键，仍需运行时采样或解析表达式上下文；
- 候选集用于审计、后续运行时采样对照和人工整理，不代表游戏当前日期/事件下必然显示的句子。

### 运行时采样小样本

采样文件使用 UTF-8 JSONL，示例工件为 `artifacts/corpus/runtime-dialogue-samples.sample.jsonl`。Claire 婚后 `funReturn_Claire` 的一条已解析分支可以被索引器消费，中文原版筛选后的联合索引样本数从 7,108 增加到 7,109；同一条重复追加不会产生第二条记录。该样本只验证格式和索引链路，不宣称覆盖了游戏当日实际分支。

### Wizard / Rasmodia 语气分层

在中文联合索引中，Wizard 的实际对白证据按来源分开保留：原版 `zh-CN` 24 条、SVE 131 条、`Parrot.RomRas` 720 条，共 875 条（大小写变体按 NPC ID 合并）。索引生成的语气特征计数为：不确定性标记 209、魔法/星界词 291、边界表达 21、干燥幽默 60。它们只用于检索和提示词辅助，不替代原文；模型仍需依据当前 `sourceMods` 和关系阶段选择证据。

这组数据支持一个明确的角色策略：原版提供克制、预言保留和魔法术语的底层声音；SVE 提供扩展世界观与事件语境；RomRas 提供娘化后的亲密关系、婚后生活和情绪暴露样本。三层不直接拼接为一段“平均语气”，而是以 `sourceMod`、`sourcePath`、`sourceKey` 分层检索，避免把 Rasmodia 的婚后台词泄露到陌生阶段。

## 来源

- [FlashShifter/StardewValleyExpanded 官方仓库](https://github.com/FlashShifter/StardewValleyExpanded)：SVE 内容包及版本来源。
- [SVE Content Patcher manifest](https://github.com/FlashShifter/StardewValleyExpanded/blob/master/Stardew%20Valley%20Expanded/%5BCP%5D%20Stardew%20Valley%20Expanded/manifest.json)：确认 CP 内容包和 UniqueID。
- [Content Patcher 作者指南](https://github.com/Pathoschild/StardewMods/blob/develop/ContentPatcher/docs/author-guide.md)：确认 JSON 内容包、`EditData` 和 i18n 机制。
- [Stardew Valley Wiki：Dialogue](https://wiki.stardewvalley.net/Modding%3ADialogue)：确认原版对白资产的组织方式。
- [SVE Nexus 文件页](https://www.nexusmods.com/stardewvalley/mods/3753?tab=files)：版本发布页，实际采集以本机 Stardrop profile 中的安装版本为准。
- [Pathoschild/StardewXnbHack 官方仓库](https://github.com/Pathoschild/StardewXnbHack)：确认原版 XNB 解包方式和输出目录。

## 证据

本机可复现命令（把 `<STARDROP_SELECTED_MODS>` 替换为 Stardrop 的 `Data/Selected Mods` 目录）：

```powershell
$py = 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'bridge/src'
& $py scripts/export_dialogue_corpus.py `
  --mod-root '<STARDROP_SELECTED_MODS>\[CP] Stardew Valley Expanded' `
  --mod-root '<STARDROP_SELECTED_MODS>\[CP] Romanceable Rasmodius SVE' `
  --locale zh-CN `
  --output data/generated/sve-dialogue-corpus.json

& $py scripts/build_profile_index.py `
  --persona-dir data/personas `
  --corpus data/generated/sve-dialogue-corpus.json `
  --output data/generated/sve-profile-index-zh-CN.json

& $py scripts/build_profile_index.py `
  --persona-dir data/personas `
  --corpus data/generated/sve-dialogue-corpus.json `
  --vanilla-root artifacts/corpus/vanilla `
  --vanilla-locale zh-CN `
  --output data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json

& $py scripts/build_profile_index.py `
  --persona-dir data/personas `
  --corpus data/generated/sve-dialogue-corpus.json `
  --vanilla-root artifacts/corpus/vanilla `
  --vanilla-locale zh-CN `
  --runtime-samples artifacts/corpus/runtime-dialogue-samples.sample.jsonl `
  --output data/generated/runtime-sample-profile-index-check.json
```

本轮实际输出：

- `sve-dialogue-corpus.json`：3,807 records，65 warnings；
- i18n 引用 3,785 条，完整解析 3,756 条，未解析 29 条（其中 25 条有 `dynamicCandidates`）；
- `sve-profile-index-zh-CN.json`：77 profiles、3,807 style samples、3,807 speech evidence；
- 全量原版（`zh-CN`）+ SVE + RomRas 联合索引：95 profiles、7,108 style samples、7,108 speech evidence；加入 1 条运行时样本的小样本校验索引为 7,109 条样本和证据。原版解包的其他语言文件仍保留在本地工件中，但不进入中文模型索引。

## 建议

1. 将 Stardrop profile 目录作为 SVE 采集的唯一输入源，不把 `Mods-AI-FastTest` 当作 SVE 资料源；FastTest 只用于运行验证。
2. 对 Wizard/Rasmodia 研究使用 SVE CP 与 `Parrot.RomRas` 分开的 `sourceMod`，先保留来源，再在 profile 层做叠加，避免把 SVE 原版和娘化覆盖混成一套。
3. 先使用已经解析的 `resolvedText` 建立语气卡；对剩余动态键，先利用 `dynamicCandidates` 做审计，再通过运行时 JSONL 采样确认实际分支，不要用猜测补全文本。
4. 生成语料和完整 i18n 文件保持在 `data/generated`/本地 ignored 目录，不提交或公开整包对白；报告只保存统计、来源和复现方法。

## 限制

- 本轮没有启动 SVE 游戏 profile，也没有执行 Content Patcher 的条件、随机和事件求值；因此 29 条动态键仍未被静态阶段强行展开。运行时 JSONL 已完成格式和索引链路验证，实际 SMAPI 观测接入仍是下一阶段。
- SMAPI 观测器本身仍只知道实际 NPC、翻译键和已解析文本，`sourceMod` 初始标记为 `runtime.unattributed`；导入器可用 corpus 做三字段唯一匹配，但未唯一命中时不会猜测来源，不能把运行时日志单独当作来源归属证明。
- SVE 包内的 XNB 地图/美术资源和部分代码目录会产生 warning，但它们不是对白文本；对白采集仍以 JSON `EditData` 目标为准。
- `resolvedText` 仍保留 Stardew 的控制码（如 `#$b#`、表情占位符），模型专用清洗应另设步骤，不能在原始证据层直接删除。
- SVE 更新后目录结构、manifest 版本或 i18n 键可能变化，应重新运行导出并比较统计，不使用旧索引替代新资源。
