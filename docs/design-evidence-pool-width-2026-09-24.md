# 素材轮转池的宽度：把「池子」与「每轮注入量」拆开

日期：2026-09-24
范围：`bridge/src/stardew_ai_bridge/{prompts.py, profile_index.py}`
起因：㉛ 之后复盘 §13.2 的实测 —— *槽位 20 次触发只覆盖了 6 条素材*。

---

## 一、结论

`_MAX_SPEECH_EVIDENCE = 6` 这一个常量原先**同时承担两个用途**：

1. `_rotate_evidence_by_turn(..., pool_size)` 的**轮转池大小**（`prompts.py`）；
2. `speechEvidence[:6]` 的**每轮注入条数**（`prompts.py`）。

而 `profile_index.speech_evidence` 里又硬编码了 `min(int(limit), 6)` —— 调用方
传多大都拿不到更多。**两个 6 叠在一起，池子永远只有 6 条可转。**

作者当时已经写明放宽是免费的（`prompts.py`）：

> 池大小**不影响 prompt 体积**（每轮仍只注入 1 条），所以放宽是免费的。

只是被 accessor 的 cap 挡住了，一直没落地。本次把它拆开，再用曲线定了值。

## 二、改动

| 常量 | 含义 | 原值 | 新值 |
|---|---|---|---|
| `_MAX_SPEECH_EVIDENCE` | speech 每轮**注入**上限 | 6 | **6（不变）** |
| `_MAX_STYLE_SAMPLES` | style 每轮**注入**上限 | 6 | **6（不变）** |
| `_SPEECH_EVIDENCE_POOL` | speech 轮转**池**宽 | （与注入共用 6） | **64** |
| `_STYLE_SAMPLE_POOL` | style 轮转**池**宽 | （与注入共用 6） | **96** |
| `profile_index._SPEECH_EVIDENCE_CANDIDATES` | accessor 候选上限 | 6 | **128** |
| `profile_index._STYLE_SAMPLE_CANDIDATES` | accessor 候选上限 | 8 | **128** |

「注入上限」一个数字没动 —— 这是"免费"的全部含义。

## 三、值是怎么定的

### 3.1 先扫曲线，不要逐个试

直接调轮转实现（`.tmp/topic-probe/scan_pool_width_full.py`），一次运行扫完
6/8/12/18/24/36/48/64/96：

| 池宽 | 首次撞回同一素材 |
|---|---|
| 6（原值） | 第 7 轮 |
| 12 | 第 12 轮 |
| 24 | 第 23 轮 |
| 48 | 第 45 轮 |
| 64 | 第 58 轮 |
| 96 | 第 76 轮 |

**规律：首次撞回 ≈ 池宽 × 0.9。**

**要看「首次撞回」而不是「覆盖率」**：覆盖率分母随池宽变大，
池 18 的 94% 反而高于池 24 的 83%，只看覆盖率会选错。

### 3.2 真正的可用素材量由**关系阶段**决定

`.tmp/topic-probe/scan_stage_material.py` 走真实路径逐阶段实测：

| 阶段 | speech | style | 构成 |
|---|---|---|---|
| stranger | 12 | 3 | dialogue + event_dialogue |
| acquaintance | 13 | 3 | |
| friend | 15 | 3 | |
| close | 23 | 3 | |
| dating | 23 | 3 | |
| **married** | **64** | **31** | marriage_dialogue 61 条解锁 |
| parent | 64 | 13 | |

**这解释了为什么池宽要按 64 定**：低阶段只有 12~23 条（池再宽也用不到），
而最高阶段 64 条 —— 池 64 刚好用满。

### 3.3 池 96 会让 style 走保底

素材是**互斥瓜分**的（见 §四），所以池开太大会把 style 吃光：

| speech 池 | married 阶段 style 实得 |
|---|---|
| 24 | 充足 |
| **64** | **31 条** |
| 96 | **0（保底生效）** |

**64 是那个「最高阶段刚好用满、又不吃掉 style」的点。**

### 3.4 事件解锁不是主要矛盾

用**真实存档**（`test2_412086775`，`eventsSeen` 391 个）实测：

- 索引里索菲亚的事件对白涉及 76 个 eventId，其中**已解锁 41 个**；
- 但事件解锁**只多贡献 3 条素材**（`event_dialogue: 3`）。

**⇒ 「补事件素材」这条路收益很小**（与报告 §12.6 撤回「82 个角色缺素材」同型：
看着缺，实则不是瓶颈）。真正的量在 `dialogue` 与 `marriage_dialogue`。

### 3.5 实测（`app._build_context(compact_prompt=True)`）

- 每轮注入条数 **1（未变）**；
- `speech_evidence` 卡字节数 **323~347**，`style_evidence` 卡 **332~373**；
- `style_evidence` 卡在所有阶段**都存在**（未因去重而消失）。

## 四、改动中撞到的真实约束：两个数组互斥瓜分同一批语料

`test_profile_context.py` 早就钉住了这件事：

```python
assert len(context["speechEvidence"]) + len(context["styleSamples"]) == 8
```

`styleSamples` 与 `speechEvidence` 在索引里**内容对称**（各 10213 条），
`schemaVersion: 1` 的兼容回退甚至让两个 accessor 指向**同一个数组**。
`ContextBuilder` 用前者的文本去重后者，所以两者是**互斥地瓜分同一批语料**：

> **扩大 speech 池 = 抢 style 的份额。**

第一次改动只按「前 6 条」去重（想保住 style），结果 `6-9` 号样本
同时出现在两张卡里，`isdisjoint` 当场变红 —— 因为池子里**任何一条**都可能
被轮转选中，去重必须覆盖**整池**。

最终解法四条一起：

1. **整池去重** —— 保住 `isdisjoint` 这条不变量；
2. **保底** —— 去重后为空时退回未去重列表。空列表会让 PromptBuilder
   **静默跳过** `style_evidence` 卡（`if safe_context["styleSamples"] ...`），
   「说话方式要贴原文」这条约束随之丢失，比重复一句严重得多；
3. **两个池宽一起定**（speech 64 / style 96）而不是只放一边；
4. **测试语料扩到 120 条** —— 让「互斥」在正常路径下可满足。

## 五、验证

- 新增 `bridge/tests/test_evidence_pool_width.py`（2 项），其中
  `test_the_rotation_pool_is_wider_than_the_injection_cap` 在改动前**必然失败**
  （实测报「20 轮只建议过 5 条不同素材」）—— TDD 的失败面是真的。
- 全量 `bridge/tests`：**3992 passed**；`scripts/verify_project.ps1` 四项全绿。

## 六、留下的方法论

**第 31 条：一个常量承担两个用途时，先问"这两个用途会不会互相要价"。**
`_MAX_SPEECH_EVIDENCE = 6` 在注释里被解释成"池子"，在切片处又被当成"注入量"，
于是"放宽池子"这个免费改动被 accessor 的同名 cap 挡住了整整一天。

**第 32 条：注意索引里内容对称的两组数据。**
`speechEvidence` 与 `styleSamples` 是同一批对白的两个用途，任何"只放大一边"
的想法都会撞上互斥瓜分。**扩大一边就要补偿另一边。**

**第 33 条：待调参数先扫曲线，不要逐个试。**
"改一个数跑一遍"会让人停在第一个看起来变好的值上（这次先停在 12、又停在 18），
而拐点在更远处。一次扫完整个区间，并认准与目标直接对应的指标。

**第 34 条：上限要看"唯一真正约束它的那层"。**
池宽的真正上限不是 cap、不是事件解锁，而是**关系阶段**：低阶段 12~23 条、
married 64 条。不知道这件事就会把池定成低阶段够用、高阶段不够的值。
**先量清楚"每个场景下真实有多少条"，再定池宽。**

**第 35 条：模拟的口径决定了结论。**
把素材原文塞进 `recentReplies`（假设她逐字复述）会得出"只覆盖 2 条"这种
与真实无关的数；那是机制**上界**，不是预期表现。离线模拟只能用来定机制参数，
**真实表现必须实机验证**。
