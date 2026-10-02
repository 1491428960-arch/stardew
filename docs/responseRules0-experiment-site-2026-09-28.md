# `responseRules[0]` 实验：落点、链路与基线（2026-09-28 核实）

> **状态**：**只读核实完成，未做任何改动**。
> 备份 `data/personas/vanilla.json-bak-20260928-responseRules0` **存在且与当前一致**
> （⇒ 上次的改动**已回滚到原值**，见 `active-work.md:4383/4395`）。

---

## 一、实验到底该改哪一行

**不是** `data/personas/rasmodia.json`（名字最像 Wizard 的那个），
**而是**：

```
data/personas/vanilla.json   →   Wizard.voiceStyle.responseRules[0]
                                 "先回答眼前的问题"
```

⚠ 我一开始查 `rasmodia.json`，它的 `responseRules` 是**另一套**
（`"先直接回应玩家，不写环境开场"`）⇒ **改它不会影响 prompt**。

**验证方法**：prompt 里 `voice_execution_card` 的 `voiceActions` 实际渲染为

```json
"voiceActions": ["先给简短判断", "解释时一层一层说", "先回答眼前的问题"]
```

第三项与 `vanilla.json` 一致，与 `rasmodia.json` 不一致 ⇒ **落点是 `vanilla.json`**。

---

## 二、⭐ 完整链路（从数据到 prompt 的 5 步）

```
① data/personas/vanilla.json
     Wizard.voiceStyle.responseRules = [
         "先回答眼前的问题",                    ← [0]，实验对象
         "日常近况按日常说，不为显得神秘而加魔法",  ← [1]
         "玩家追问后再展开研究或塔里的事",          ← [2]
         "不把猜测说成结论",                      ← [3]
     ]
     Wizard.voiceStyle.sentencePattern = ["先给简短判断", "解释时一层一层说", "偶尔用‘嗯’或‘唔’停顿，不连续铺陈"]
     Wizard.voiceStyle.signatureMoves  = （**不存在/空**）
                    ↓
② data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json（生成的索引）
     profiles/Wizard/overlays/Romanceable Rasmodius/voiceStyle
     ⇒ responseRules 与源文件**逐字一致**（已比对）
                    ↓
③ bridge/src/stardew_ai_bridge/prompts.py ≈L5057  voiceActions 组装
     signature_moves = _compact_text_list(signatureMoves, limit=2)   ⇒ 空
     voice_actions   = list(signature_moves)                          ⇒ []
     if signature_moves:  ... else:
         voice_actions.extend(sentence_pattern)                       ⇒ 2 条
         voice_actions.extend(_compact_text_list(responseRules, limit=2))  ⇒ 2 条
     voice_actions = voice_actions[:3]                                ⇒ **截到 3 条**
                    ↓
④ voice_execution_card 的 voiceActions
     ["先给简短判断", "解释时一层一层说", "先回答眼前的问题"]
      ↑ sentencePattern[0]  ↑ sentencePattern[1]   ↑ responseRules[0]
```

### ⭐⭐ 由链路推出的三个硬事实

| # | 事实 | 含义 |
|---|---|---|
| 1 | **`responseRules[0]` 落在第 3 槽** | 前两槽被 `sentencePattern` 占满 |
| 2 | **`responseRules[1]` 被 `[:3]` 截掉** | ⚠ **「日常近况按日常说」这条根本没进 prompt** |
| 3 | **`responseRules[2]`、`[3]` 更进不来** | ⚠ 「日常寒暄通常只说 **1–2 句**」（在 `rasmodia.json` 那套里）**也不在 prompt** |

⇒ **事实 3 是对「字数话语权只有 1/6」的又一条独立佐证**：
**角色数据里写的长度规则，有相当一部分连 prompt 都进不去。**

⚠ **推论需谨慎**：`responseRules[2]/[3]` 没进 `voiceActions`，
**不等于**它们完全不出现在 prompt 里 —— 需另查是否有别的卡也渲染 `responseRules`。
**这一点我还没验证，不要当成结论使用。**

---

## 三、⭐ 36 个角色的 `responseRules[0]` 全貌（推广时的关键）

`data/personas/vanilla.json` 里 **36 个角色全部**有 `responseRules[0]`，
**全部是「先回答 / 先回应 / 先接住…」同一模式**，但**信息量差异极大**：

| 写法 | 例子 | 结构 |
|---|---|---|
| **最短** | `先回答眼前的问题`（**Wizard**） | 只有「做 X」 |
| | `先说实际情况，不写漂亮总结`（Shane） | 做 X（+ 模糊的反面） |
| | `先回应眼前的问题，不把普通话题写成散文`（Sebastian） | **做 X + 不做 Y** |
| **最长** | `先回答玩家问的家庭或日常问题，不用泛泛的母亲式说教代替`（Marnie） | **做 X + 不做 Y，且都具体** |
| | `先回答玩家这句话；没提运动时不要硬转成训练建议`（Alex） | 做 X + **条件性禁止** |

### ⇒ 对「推广到其余同类角色」的两条直接结论

1. ⚠ **不能照抄 Wizard 的新写法。**
   36 条各有各的**角色化排除项**（「不用说教代替」「不用销售话术代替」
   「不编造成人信息」…），**统一替换会把这些排除项一起抹掉**。
2. ⭐ **Wizard 那条恰恰是最"空"的一条** ——
   只有正面要求、没有排除项 ⇒ 它**本来就没什么可损失的**，
   这既解释了它为何适合做**第一个单变量实验对象**，
   也提醒：**在它身上有效，不代表在这条更有信息量的角色上也有效。**

---

## 五、⭐ 基线洁净性：已逐字确认（**这一条不做实验就是白做**）

`git status` 里 **`data/personas/vanilla.json` 是 `M`（已修改）** ——
而它正是实验的基线文件。**必须查清这个 `M` 是什么**，否则基线不可信。

**查证结果**：

```
HEAD 版本   Wizard.responseRules[0] = "先回答眼前的问题"
工作区当前   Wizard.responseRules[0] = "先回答眼前的问题"
备份文件     Wizard.responseRules[0] = "先回答眼前的问题"
                                        ⇒ 三者逐字一致
```

⇒ **`M` 的原因是工作区新增了 `Sam` 角色**（diff 里只有 `+ "Sam": {...}` 一大段），
**与 `responseRules[0]` 无关**。

⚠ 为什么必须查：备份与当前 **SHA1 一致**只能说明「当前 = 备份」，
**不能说明备份就是原始值**（若回滚时把改动后的版本当成了备份，两者也会一致）。
⇒ **三方比对（HEAD / 工作区 / 备份）才是可靠的确认方式。**

---

## 六、⚠ 两条分支的差异（推广时会咬人）

`voiceActions` 的组装有**两个分支**，取决于角色**有没有 `signatureMoves`**：

| 角色 | `signatureMoves` | 走的路径 | 第 3 槽 |
|---|---|---|---|
| **Wizard** | **空/不存在** | `sentencePattern`(≤3 取 2) + `responseRules`(≤2) | **`responseRules[0]`** |
| **Sam** | **有 2 条** | `signatureMoves`(≤2) + `responseRules`(≤2) | **`responseRules[0]`** |

⇒ **两条路径恰好都让 `responseRules[0]` 进第 3 槽**，但**机制完全不同**：
- Wizard 是 **`sentencePattern` 占满前两槽**；
- Sam 是 **`signatureMoves` 占满前两槽**。

⚠ **含义**：如果某个角色的 `signatureMoves` **只有 1 条**，
那么 `responseRules` 就会有 **2 条**进 prompt（第 2、3 槽）——
**`responseRules[0]` 的位置会变**。
⇒ **推广到别的角色前，要先数它有几条 `signatureMoves`。**

---

## 七、做实验前还差什么（诚实清单）

| 项 | 状态 |
|---|---|
| 落点确认 | ✅ 已核实（`vanilla.json`，非 `rasmodia.json`） |
| 备份可用 | ✅ `vanilla.json-bak-20260928-responseRules0`，与当前一致 |
| 链路`[:3]`截断 | ✅ 已从源码 + 实际 prompt 双向确认 |
| 基线（改动前） | ⚠ **有历史数据**（`active-work.md:4383` 那次改动**已回滚**），数字待回读 |
| 云端额度 | ❌ **等到 10-01 10:32:50Z**（北京 18:32） |
| 「`responseRules[2]/[3]` 是否另有渲染」 | ❌ **未验证**，见 §二 的谨慎说明 |

> ⚠ 上次这个改动被判定「**无害但零证据**」并回滚。
> 原因不是改动不好，而是**当次实验设计没有能力分辨它** ——
> 跑与跑之间本身就在动（漂移 10~14 字），且动得**比改动大**（效应 ~5.7 字）。
> ⇒ 重做时必须用**交错 A/B/A/B** 相邻配对，把这部分漂移抵消掉。
