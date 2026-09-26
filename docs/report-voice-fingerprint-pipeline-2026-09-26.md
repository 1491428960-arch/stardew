# 语言指纹管线：从原文统计「他怎么说」（2026-09-26）

## 结论

**管线已落地，并且它立刻抓出了四个「不报错、只产错数字」的缺陷 —— 这些缺陷正是
「不太贴角色 / 原文那块处理得不怎么样」的直接成因之一。**

| 交付物 | 位置 |
|---|---|
| 统计与审计逻辑（纯函数） | `bridge/src/stardew_ai_bridge/voice_fingerprint.py` |
| 生成 / 审计 / 校验 CLI | `scripts/mine_voice_fingerprint.py` |
| 全库指纹数据（44 角色，入库） | `data/voice-fingerprints.json` |
| 闸 | `bridge/tests/test_voice_fingerprint.py`（20 条）、`test_voice_fingerprints_data.py`（17 条） |

四个缺陷按危害排序：

| # | 缺陷 | 症状（看起来正常，实际是垃圾） |
|---|---|---|
| ① | 统计读了 `text`，**没读 `resolvedText`** | SVE 角色「句长中位 35、语气字 0」——拿 `{{i18n:Sophia.CharacterDialogue.001}}` 在算 |
| ② | npcId **别名没有归一** | Morris / Marlon / Gunther 的语料挂在 `MorrisTod` / `MarlonFay` / `GuntherSilvian` 上，特质与语料永远见不到面 |
| ③ | 语气字写了 5、6 个，**prompt 只取前 4 个** | 「配了 6 个语气字」是错觉，第 5 个起是净损失 |
| ④ | `closers` **不进任何 prompt** | 41 个角色写了它，改了没有任何效果 |

全库现状：**44/44 个角色的人设语言层与原文有落差**（high 4 / medium 51 / low 41）。
其中 **4 个角色声明了原文里 0 次的语气字**（Evelyn「哎呀」/ Harvey「欸」/ Krobus「噢」/ Lance「嗯」）。

---

## 一、缺陷①：读错字段，把 SVE 角色的日常对白当成了键名

语料的 `text` 保存的是 **Content Patcher 原始模板**（`corpus.py::_apply_i18n_resolution`
的设计是「原始 text 不被覆盖」），解析出来的中文在 `resolvedText` ——
20260923 批次里 **8509/14063 条有**，只有 **310 条**真的没解析出来。

只读 `text` 不会报错，会得到一组**很像结论的数字**：

| 角色 | 读 `text`（错） | 读 `resolvedText`（对） |
|---|---|---|
| Lance | 出声 173，句长中位 **35**，语气字 **—** | 出声 167，句长中位 **13**，语气字 啊8 吧6 哪3 |
| Olivia | 出声 282，句长中位 **37**，语气字 **—** | 出声 273，句长中位 **12**，语气字 吧16 啊9 哦8 |
| Sophia | 出声 313，句长中位 **37**，语气字 **—** | 出声 305，句长中位 **9**，语气字 嘿40 哦39 吧24 |
| Andy | 出声 134，句长中位 **35** | 出声 129，句长中位 **12** |

**「索菲亚没有日常对白」这个已经写进工作日志的结论，就是这么来的** ——
她实际有 **305 条**日常对白（SVE 的 `assets/CharacterFiles/Dialogue/Sophia/Dialogue.json`），
读的字段错了，全部变成了 35 个字符长的键名。

取值口径现在只收在 `voice_fingerprint.dialogue_text()` 一处，并有一条测试
（`test_dialogue_text_prefers_resolved_text_over_the_raw_template`）钉住。

## 二、缺陷②：别名没归一，特质与语料挂在两个键上

SVE 把三个角色的**角色键**写成全名，而 `data/personas/sve.json` 用短名：

| 语料 npcId | persona 键 | 归一前出声 | 归一后出声 | 别名证据（`sourcePath` 目录名） |
|---|---|---:|---:|---|
| `MorrisTod` | `Morris` | 26 | **147** | `assets/CharacterFiles/Dialogue/Morris/Dialogue.json` |
| `MarlonFay` | `Marlon` | 3 | **110** | `assets/CharacterFiles/Dialogue/Marlon/Dialogue.json` |
| `GuntherSilvian` | `Gunther` | 12 | **74** | `assets/CharacterFiles/Dialogue/Gunther/Dialogue.json` |

证据不是猜的：`MorrisTod` 的初见台词是「我叫**莫里斯**，是鹈鹕镇 Joja 超市的经理」，
而 persona 的 `Morris` 就是 Joja 经理。生成时逐条校验（`_alias_evidence()`），
对不上直接报错而不是静默合并。

**✅ 生产侧已落地（同日，`personas.NPC_ID_ALIASES`）**：`canonical_npc_id()` 是索引构建、
prompt、阶段策略、关系门控的**公共入口**（`profile_index.py` 里 30 多处调用），所以别名
补在这一层，一处改动全链路受益。重建索引实测：

| npcId | 旧 | 新 |
|---|---:|---:|
| `Marlon` | 40 | **276** |
| `Morris` | 153 | **220** |
| `Gunther` | 61 | **92** |
| `MarlonFay` / `MorrisTod` / `GuntherSilvian` | 236 / 67 / 31 | **0** |

`profiles` **139 → 136**（消失的正是那三个全名条目，无新增），`styleSamples` /
`speechEvidence` 保持 **10213**、`knowledgeFacts` **47**、`warnings` **10** ——
**样本是搬迁不是丢失**；旧索引里同一个角色有两张卡（`MorrisTod` 也有 voiceCard），
现在只剩一张。闸：`bridge/tests/test_npc_id_aliases.py`（7 条）。

⚠ **默认索引尚未替换**：线上索引是 Bridge **启动时**读入的，换文件必须重载 Bridge
（会打断正在进行的游戏会话），所以留给人择时执行：

```powershell
Copy-Item -LiteralPath 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json' `
  -Destination 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue-v4.json'
Copy-Item -LiteralPath '.tmp/pipeline-audit/index-aliased.json' `
  -Destination 'data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json'
# 然后重载 Bridge
```

## 三、缺陷③：写了 5、6 个语气字，只有前 4 个进 prompt

`prompts.py:3198-3206`（`_compact_voice_style`）的实际顺序是：

```
speechParticleHints（limit=4） ——有就用它
   ↓ 为空时
openers 首字里抽（首字必须落在 _INTERJECTION_HEADS，最多 4 个）
```

⇒ **`speechParticleHints` 优先，`openers` 只是兜底** —— 这一条与 ㊵ 的笔记
（「语气颗粒是从手写 openers 里提取的」）不一致，以代码为准。
另外 `_INTERJECTION_HEADS` **不含「嚯」**，所以靠 openers 兜底时「嚯」抽不出来。

现状：`Sophia` 写了 5 个（第 5 个「呃」不生效）；`Lewis` 原先写了 6 个（本轮已删到 4 个）。

闸：`test_prompt_really_keeps_only_four_particles` **调用真实的
`prompts._compact_voice_style()`** 验证只留 4 个，而不是靠人记住这个数字；
`test_interjection_heads_are_shared_with_prompts` 用 `is` 断言叹词表与 prompt 是同一个对象。

## 四、缺陷④：`closers` 是死字段

`prompts.py` 里**没有任何一处**读 `closers`（`personas.py` 只在默认模板里出现）。
**41 个角色**写了它。它不影响线上，但会让「我改了收尾语」变成一次空操作。

## 五、全库落差清单

### 5.1 high：声明了原文里 0 次的语气字（**4 个角色**，必须改）

| 角色 | 出声 | 句长中位 | 原文前 5 语气字 | 人设声明 | 凭空写的 |
|---|---:|---:|---|---|---|
| Evelyn | 55 | 11 | 啊11 哦9 哎3 吧2 呀2 | 啊、哎呀 | **哎呀**（原文只有拆开的「哎」） |
| Harvey | 127 | 10 | 吧11 啊8 噢6 哦5 呃4 | 嗯、欸 | **欸** |
| Krobus | 124 | 11 | 吧10 呢7 啊3 哎2 哦2 | 哦、噢 | **噢** |
| Lance | 167 | 13 | 啊8 吧6 哪3 呢2 唔1 | 啊、嗯、呃 | **嗯** |

⚠️ **这一节在第一轮里是错的（写着 11 个角色、其中 8 个是「嗨」），已于同日更正。**

原因是 `PARTICLE_CHARS` 漏了「嗨」「欸」「哈」三个字 —— 而它们**都在 prompt 的叹词表里**。
全文语气字统计从没统计过它们，于是**凡是声明「嗨」的角色都被判成「凭空写的字」**。
实测：「嗨」在语料里出现 **142 次**、作句首 133 次。

所以第一轮那句「8 个角色用同一个『嗨』，是批量模板值（与 ㉞ 的『朋友』同型）」**是假的，撤回** ——
那 8 个角色是真的在用「嗨」说话，模板值这个判断没有任何证据支撑。

修法：语气字表补齐三个字，并加闸
`test_particle_chars_cover_every_interjection_head` 钉住「语气字表必须是叹词表的**超集**」。
这类缺口是「静默」的典型：表缺一个字，不报错，只产出一个看起来很确定的假结论。

### 5.2 汇总

| 问题码 | 数量 | 含义 |
|---|---:|---|
| `particle_missing` | 42 | 原文高频语气字没写进人设（**改动清单的主体**） |
| `closers_dead_field` | 41 | 写了不生效的字段 |
| `particle_not_in_corpus` | 11 | 凭空写的（上表） |
| `no_particle_anywhere` | 7 | 人设没写、openers 首字也不是叹词 ⇒ prompt 里一个颗粒都没有 |
| `particle_over_prompt_limit` | 1 | Sophia 写 5 个，第 5 个不生效 |
| `no_spoken_evidence` | 1 | Rasmodia（出声 0、事件 0） |

### 5.3 句长：角色之间差一倍

最短：Jas 7 / Vincent 7 / Claire 8 / George 8 字。
最长：Pierre 12 / Lance 13 / Wizard 13 字（P90 分别 23 / 23 / 26）。
**这不是文风评价，是可直接对照的数字** —— 人设里 `openers` 的长度应当落在这附近，
而现状是大量 10~15 字的完整礼貌句。

### 5.4 没写完的部分

- 语料里有出声证据、但**人设里没有**的角色 13 个：`Alesia`、`Apples`、`GuntherSilvian`（已归一，列为兜底）、
  `HankSVE`、`MarlonFay`（同上）、`Martin`、`Morgan`、`MorrisTod`（同上）、`Scarlett`、`Susan`、`Treyvon`、
  `MarriageDialogue`、`rainy`。
  后两个是**伪 npcId**（由文件名/键名误判而来），属语料侧缺陷。
- `Rasmodia` 出声 0 条：`Nom0ri.RomRas` 的 2231 条全在事件侧。

## 六、Lewis 试点收口

试点改动（唯一动过的角色）：

| 字段 | 改前 | 改后 |
|---|---|---|
| `speechParticleHints` | `["啊","嘿","吧","嗯","嘛","嚯"]`（6 个，只有前 4 个生效） | `["啊","嘿","吧","嗯"]`（4 个，按原文频次 啊17 嘿8 吧6 嗯4） |
| `tone` / `sentencePattern` / `signatureMoves[0]` / `openers` | 上一轮已按原文改过 | 未再动 |

指纹核对：Lewis 出声 **87** 条、分句后中位 **12** 字、P90 23、省略号率 **0.31**、
感叹号率 **0.36**；声明的 4 个字全部在原文里出现且按频次降序 —— 试点通过。

## 七、口径（用数据前先读这一节）

1. **出声证据 = `evidenceKind ∈ {dialogue, marriage_dialogue, extra_dialogue}`**。
   `event_dialogue`（7391 条）是剧情节拍，**不作**语气证据 —— 拿事件台词冒充日常
   正是这条管线要防的错。
2. **两个长度口径都给**：`utteranceLength`（一条发言，用来衡量 `openers` 长度）
   与 `sentenceLength`（按 `。！？…` 分句，用来描述落笔节奏）。Lewis 是 41 / 12。
   只报一个必然误导。
3. **性别变体取第一支**：`${子^女}$` → 「子」。原因是 prompt 里**没有玩家性别**
   （见 `stardew-persona-addressing-field`）。这是已知偏差，不是正确解。
4. **残留标记不静默删除**：`%` 313、`*` 374、`[`/`]` 170、`{`/`}` 99/53。
   语义没有把握的一律只统计上报（`residualMarkers`），不擅自清。
5. **证据不足的角色照实标**：`thin`（< 30 条）、`event_only`、`none`。
   `Rasmodia` 是 `none`。

## 八、复现

```powershell
$env:PYTHONPATH = 'bridge/src'
$py = 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe'

& $py scripts/mine_voice_fingerprint.py --audit                 # 打印差异表
& $py scripts/mine_voice_fingerprint.py --audit --audit-md .tmp/gaps.md
& $py scripts/mine_voice_fingerprint.py --check                 # 校验产物与语料一致
& $py -m pytest bridge/tests/test_voice_fingerprint.py bridge/tests/test_voice_fingerprints_data.py -q
```

验证（2026-09-26）：`pwsh -NoProfile -File scripts/verify_project.ps1` → **全部通过**
（SMAPI 1046 / Bridge 4116 / compileall / `git diff --check`）。

## 九、落差怎么改（路线）

### 9.1 先认清一件事：语言层通往 prompt 的位置是**有界**的

`_compact_voice_style`（`prompts.py:3146-3206`）就是语言层进 prompt 的**唯一白名单**：

| 字段 | 条数 | 单条上限 |
|---|---:|---:|
| `tone` | 1 | 120 字 |
| `sentencePattern` | 2 | 65 字 |
| `responseRules` | 2 | 75 字 |
| `signatureMoves` | 2 | 140 字 |
| `preferredTopics` | 12 | 80 字 |
| `avoid` | 2 | 60 字 |
| `emotionRange` | 4 | 45 字 |
| `openers` | 4 | 60 字 |
| `speechParticleHints` | 4 | 12 字 |
| `closers` | — | **不在表里**（死字段） |

⇒ 写第 3 条 `sentencePattern`、第 5 个语气字、第 5 条 `openers` **全是白写**。
**改造 = 在这些位置里换内容，不是往里加内容。** 这也是 44 个角色「写了却不像」的
结构性原因之一 —— 额度本来就那么小，而现有内容大半是模板。

### 9.2 三种落差、三种改法

| 类型 | 数量 | 改法 | 要判断力吗 |
|---|---:|---|---|
| **错的信息**：声明了原文 0 次的字（哎呀 / 欸 / 噢 / 嗯） | 4 | 删掉、换成原文 top 字 | 不要，机械 |
| **缺的信息**：漏了原文高频字、句长没锚点 | 42 | 按指纹生成草稿 → 人审 | 要（审） |
| **无效的字段**：`closers` | 41 | 删掉（或接进 prompt，但要占预算） | 一次性拍板 |

### 9.3 机制：把「从零手写」换成「生成草稿 + 审」

指纹数据已经把四个字段的原料算好了 —— 这正是本管线的用途：

| voiceStyle 字段 | 指纹里现成的原料 |
|---|---|
| `speechParticleHints` | 原文 top4 语气字**及其频次** |
| `sentencePattern` | 「一句话通常 N~M 字」（N = 分句长度中位、M = P90） |
| `openers` | `samples.typical` 里的**真实原话**（先分句，再取长度接近句长中位的；`shortest` 只作补充） |
| `tone` | 「将近三成的话带省略号」这类描述，取自 `rates` |

⇒ 给脚本加 `--suggest`：输出每个角色的 `voiceStyle` **草稿**，只覆盖这四个字段；
`coreTraits` / `knowledgeRules` / `stageProfiles` / `avoid` / `preferredTopics`
**一律不碰**（保持 ㊵ 的变量隔离：要能分清是哪一层在起作用）。
工作量从「44 × 从零写」变成「44 × 审 4 句话」。

### 9.4 分批

| 批 | 范围 | 依据 |
|---|---|---|
| 1 | **4 个 high** | 机械、无争议，先清掉错的信息 |
| 2 | 出声 **≥100** 的 **22** 个角色 | 数据最扎实（Sophia 305 / Victor 288 / Olivia 273 / Abigail 240 …） |
| 3 | 出声 30~99 的 **19** 个 | 够用但薄 |
| — | **先不动**：`thin` 2（Dwarf 27 / Leo 12）、`none` 1（Rasmodia） | 证据不足，硬改又是凭想象 |

另有一类**不用改人设、要改代码**：`no_particle_anywhere` 的 7 个角色（人设没写语气字、
`openers` 首字也不是叹词 ⇒ prompt 里一个颗粒都没有）。它们的 `speechParticleHints` 是空的，
填上原文 top4 就行 —— 属于批 2。

### 9.5 验证怎么算过

- **离线**（免费、每次改完跑）：`--audit` 里 `particle_not_in_corpus` 归零、
  `particle_missing` 显著下降、`--check` 通过。
- **线上**（有成本）：**不必 44 个都跑**。每个批次抽 2~3 个角色，用 ㊵ 那套对照法
  （同一串玩家台词，改前/改后各跑一遍）。指纹保证的是「数据对得上原文」，
  **保证不了「模型照做」** —— 后者只能靠对话验证。

### 9.6 建议的第一步

1. **批 1 清零**（4 个 high）—— 不需要任何判断，改完离线闸立刻可见。
2. 挑 **1 个高证据、且语言层从未配过的角色**完整走一遍 9.3 的流程 ——
   建议 **Victor**（出声 288、句长中位 11、`speechParticleHints` 为空、
   且**从未被前几轮实验改过**，是干净对照）。Sophia 虽是证据最多的（305），
   但她在 ㉑~㉕ 被反复改过，不适合当「方法有效性」的对照。
3. 有效再铺开到批 2。

## 十、第二轮（同日）：草稿生成器 `--suggest` + 又抓出两个清理缺陷

用户拍板「先做 `--suggest`、出 high 的草稿 + Victor 试点」后开工。过程中又抓到
**两个清理缺陷和一个口径缺陷** —— 都属于「旧脚本沉默吞掉、只有把清理结果拿出来看才会暴露」那一类，
和第一轮那四个是同一个病根。

### 10.1 缺陷 ⑤：`#$e#` 的**两侧**都要看（290 条）

`$6` 这类表情标记常紧跟句末标点：`…去了。$6#$b#…`。清理顺序若先处理分页符，
它前面看到的是 `$6` 而不是标点，于是补一个句号；随后删掉 `$6` 就成了「去了**。。**」。
**290 条命中**（Abigail 的婚姻对白整片），表现是草稿的 openers 里冒出
「是小南瓜形状的哦。。」。

修法：`_EMOTE` 提到 `_PAGE_BREAK` 之前，并给它加负向后顾避开 `#$e#` 里的 `$e`
（否则会把分页符破坏成 `##`）。

### 10.2 缺陷 ⑥：`$q` / `$r` 互斥分支被拼成一段话（215 条）

星露谷的 `#$q <id>/<ans> <key>#` 与 `#$r …#` 是**问句与各个互斥的回答**。语料原样保留，
于是「我不知道。我们会变成鬼魂。我们会上天堂。」被当成**一个人一口气说的话** ——
句长、语气字、样本全被污染（Abigail 的问句对白最多）。

修法：`_drop_branch_tail()` 只保留第一段、其余整段丢弃；`$c` / `$p` / `$1` 这类
带参指令一并删除。

⚠ **一个差点修错的地方**：带参指令与单字符标记的分界线是**空格**。`$h#$e#` 里那个 `#`
属于后面的分页符，不是 `$h` 的参数 —— 第一版正则把它当参数吃掉，`#$e#` 退化成 `$e#`，
**残留从 215 条涨到 669 条**。加上「参数必须以空格开头」后：含 `#` 残留 215 → **38**、
含 `$` 仅 **7** 条（14063 中 0.27%）。

### 10.3 口径稳定性（这一节是给以后的人看的）

清理改动后重算全库：**Lewis 87 条 / 句长中位 12 / 省略号 0.31 / 感叹号 0.36 —— 与改前逐位相同**，
六类落差计数（42 / 41 / 11 / 7 / 1 / 1）也一字不差。也就是说这两个缺陷只污染边缘记录，
**不动摇任何结论** —— 但它会污染任何直接使用 openers 原话的地方（草稿、prompt），
所以不能因为「统计没变」就放着。

### 10.4 `--suggest`：草稿生成器

```powershell
python scripts/mine_voice_fingerprint.py --suggest --suggest-severity high
python scripts/mine_voice_fingerprint.py --suggest --suggest-npc Victor,Lewis
```

只覆盖会进 prompt 的 4 个字段；`coreTraits` / `knowledgeRules` / `stageProfiles` /
`avoid` / `preferredTopics` **一律不碰**（保持 ㊵ 的变量隔离）。输出到
`.tmp/voice-suggest/voice-suggestions.json`，**绝不写 `data/personas/`**。

生成规则（每一条都对应一个实测教训）：

| 字段 | 取法 | 踩过的坑 |
|---|---|---|
| `speechParticleHints` | 原文频次前 4 | —— |
| `sentencePattern` ① | 「一句话通常 N 字上下，最多 M 字左右」（N = 分句中位、M = P90） | —— |
| `sentencePattern` ② | 句首叹词（「常以『嘿』这类语气字起句」）或括号描写 | **高频短语不能用**：`phrases` 前几是「今天」「我们」这类通用词，对谁都一样 |
| `openers` | `samples.typical` 分句后挑长度接近句长中位的 4 句，同等长度优先带语气字的 | **`shortest` 不能用**：它是「我正在刷牙。」「我的庄稼很健康！」（后者被采样 4 次）这类场景短句 |
| `tone` | 省略号率 / 感叹号率，按阶梯转成「将近三成的话带省略号」 | **不与 `sentencePattern` 重复句长** |

输出用三种标记区分可判定性，避免误导审稿的人：

- `≠`（`speechParticleHints` / `openers`）：直接从语料取的，**可照抄**；
- `~`（`sentencePattern` / `tone`）：数字堆的骨架，**要改成人话** —— 现状若已有等价说法
  （如「一句话通常十来个字」对「12 字上下」）就不用动；
- `!`：证据不足或信息缺失时的明示（如「句式只出一条，第二条要你自己写」）。

**证据不足不出草稿**：`event_only` / `none` 直接返回空建议 + 说明 —— 那正是「凭想象写」的起点。
`thin` 出草稿但带「别照抄」警告。

### 10.5 批 1 的草稿（4 个 high + Victor 试点，实测）

| 角色 | 出声 | 人设声明的语气字 | 草稿建议的前 4 | 开场原话（草稿） |
|---|---:|---|---|---|
| Evelyn | 55 | 啊 / **哎呀** | 啊 / 哦 / 哎 / 吧 | 亲爱的，我真为你高兴。 |
| Harvey | 127 | 嗯 / **欸** | 吧 / 啊 / 噢 / 哦 | 我大概是要生病了…… |
| Krobus | 124 | 哦 / **噢** | 吧 / 呢 / 啊 / 哎 | 等等，这是我吗……？ |
| Lance | 167 | 啊 / **嗯** / 呃 | 啊 / 吧 / 哪 / 呢 | 我在想今天要做什么好…… |
| **Victor**（试点） | 288 | （空） | 吧 / 呃 / 嘿 / 嗯 | 万灵节快乐，亲爱的！ |

（加粗 = 原文里 0 次的字，即批 1 要清掉的「错的信息」。）

Victor 那 4 条原话是「万灵节快乐，亲爱的！」「明天我想去山顶远足。」
「大概是因为我总玩电子游戏吧。」「我真想吃薄荷巧克力碎冰淇淋！」——
和他现有手写的「你发现什么了？」「这个问题有意思。」相比，语料版明显更像
**一个会突然兴奋起来的工程师**，而那正是他 `tone` 里写着、却没落进 `openers` 的性格。

### 10.6 缺陷 ⑦：语气字表漏了三个字，造出 7 个假 high（**本轮最值钱的发现**）

做批 1 草稿时撞上一个自相矛盾：Pierre 被审计判成「声明了原文 0 次的『嗨』（high）」，
可同一份草稿的句式建议却写着「常以『嗨』这类语气字起句」—— **两者不可能同时为真**。

查下去：`PARTICLE_CHARS` 是 `"啊哦嗯呀嘿呃嘛吧呢啦噢哎唉唔咦哇嚯哪哟诶"`，
**里面没有「嗨」**，而 prompt 的叹词表里有。两个表不一致的后果是**静默**的：

- 句首能当叹词、却不在语气字表里的字，**全文频次永远记 0**；
- 于是凡是声明了它的角色，一律被判成「凭想象写的字（high）」。

实测这三个字在语料里都真实存在：
**「嗨」142 次（作句首 133 次）、「哈」129 次、「欸」7 次。**

⇒ 第一轮 §5.1 的「11 个 high」里 **7 个是假的**；那句「8 个角色共用『嗨』= 批量模板值
（与 ㉞ 的『朋友』同型）」也**随之撤回** —— 那 8 个角色是真的在用「嗨」说话。
补齐表之后 high 从 11 降到 **4**，剩下每一个都是「这个角色确实从不说这个字」。

闸：`test_particle_chars_cover_every_interjection_head`，钉住
**语气字表必须是叹词表的超集**。

**为什么它比前六个都值钱**：前六个缺陷只污染数据（改完结论不变），这一个直接
**伪造了一个洞察** —— 而且看起来非常确定、非常有解释力。两张表之间的包含关系
若不写成断言，它就会以「一个漂亮的结论」的形式还回来。

## 十一、待办

1. ~~**生产侧别名归一**~~ ✅ **已完成**（见 §二）：`personas.NPC_ID_ALIASES` + 重建索引
   （profiles 139→136、Marlon 40→276）。**唯一剩下的动作是替换默认索引文件并重载 Bridge**
   —— 会打断正在进行的游戏会话，留给人择时（命令见 §二）。
2. ~~**`--suggest` 草稿生成器**~~ ✅ **已完成**（见 §10.4）。
3. **批 1：4 个 high 清零**（Evelyn / Harvey / Krobus / Lance，见 §10.5）——
   机械、无争议，草稿已就绪。
4. **Victor 试点**：把 §10.5 那 4 句草稿改成人话、写进 `data/personas/sve.json` 的
   `voiceStyle`，然后按 §9.5 做对话级对照。**这一步是全流程是否成立的唯一判据。**
5. **42 个角色的 `particle_missing`**：这是「贴角色」的主战场（B 档内容工作），
   数据已在 `data/voice-fingerprints.json` 的 `gaps` 里逐条列好。
6. **`%` / `*` 的语义拍板**：要不要从统计里清掉（`$q` / `$r` 那类已在本轮清掉）。
7. **语料侧**：伪 npcId（`rainy`、`MarriageDialogue`）与 310 条未解析 i18n。
8. **8 个有语料没人的角色**（Scarlett / Martin / Morgan / Susan / Alesia / Apples …）
   是否要建人设。
9. ㊵ 留下的另外两项仍未动：`preferredTopics` 的公务话题、方向卡第 4 轮起掉
   （`MaxHistoryItems=6` 挤出开场白）。
