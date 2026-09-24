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

> 池大小**不影响 prompt 体积**（每轮仍只注入 1 条），所以放宽是免费的；
> 代价只是每轮那 1 条从「前 4 名」变成「前 6 名」里轮，单条质量略降。

只是被 accessor 的 cap 挡住了，一直没落地。本次把它拆开。

## 二、改动

| 常量 | 含义 | 原值 | 新值 |
|---|---|---|---|
| `_MAX_SPEECH_EVIDENCE` | speech 每轮**注入**上限 | 6 | **6（不变）** |
| `_MAX_STYLE_SAMPLES` | style 每轮**注入**上限 | 6 | **6（不变）** |
| `_SPEECH_EVIDENCE_POOL` | speech 轮转**池**宽 | （与注入共用 6） | **12** |
| `_STYLE_SAMPLE_POOL` | style 轮转**池**宽 | （与注入共用 6） | **24** |
| `profile_index._SPEECH_EVIDENCE_CANDIDATES` | accessor 候选上限 | 6 | **18** |
| `profile_index._STYLE_SAMPLE_CANDIDATES` | accessor 候选上限 | 8 | **24** |

「注入上限」一个数字没动 —— 这是"免费"的全部含义。

## 三、实测

### 3.1 轮转覆盖（索菲亚，20 轮，`app._build_context(compact_prompt=True)`）

| | 改动前 | 改动后 |
|---|---|---|
| 20 轮覆盖到的**不同**素材 | **5 条** | **8 条** |
| 每轮注入条数 | 1 | **1（未变）** |
| `voice_execution_card` 字节数 | — | **恒定 886 / 656** |

### 3.2 style 一路的可用条数（全 139 个角色）

| | 改动前 | 改动后 |
|---|---|---|
| style 可用条数**合计** | 174 | **392（+125%）** |
| style 不足 6 条的角色 | 139 / 139 | **121 / 139** |
| 逐角色 | — | **改善 75、不变 63、退化 1** |

唯一退化的 `ProfessorSnail`（2 → 0）落在**保底**兜住的范围内（见 §四）。

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

最终解法三条一起：

1. **整池去重** —— 保住 `isdisjoint` 这条不变量；
2. **保底** —— 去重后为空时退回未去重列表。语料不足的角色宁可两张卡
   偶尔重复一句，也不能让 `styleSamples` 为空：空列表会让 PromptBuilder
   **静默跳过** `style_evidence` 卡（`if safe_context["styleSamples"] ...`），
   「说话方式要贴原文」这条约束随之丢失，比重复一句严重得多；
3. **测试语料扩到 40 条** —— 让「互斥」在正常路径下可满足（10 条语料下
   「整池互斥」+「两边都非空」在数学上无解）。

## 五、验证

- 新增 `bridge/tests/test_evidence_pool_width.py`（2 项），其中
  `test_the_rotation_pool_is_wider_than_the_injection_cap` 在改动前**必然失败**
  （实测报「20 轮只建议过 5 条不同素材」），改动后通过 —— TDD 的失败面是真的。
- 全量 `bridge/tests`：**3992 passed**（四个 gate 全绿）。

## 六、留下的方法论

**第 31 条：一个常量承担两个用途时，先问"这两个用途会不会互相要价"。**
`_MAX_SPEECH_EVIDENCE = 6` 在注释里被解释成"池子"，在切片处又被当成"注入量"，
于是"放宽池子"这个免费改动被 accessor 的同名 cap 挡住了整整一天。

**第 32 条：注意索引里内容对称的两组数据。**
`speechEvidence` 与 `styleSamples` 是同一批对白的两个用途，任何"只放大一边"
的想法都会撞上互斥瓜分。改之前先用全量角色扫一遍前后对比
（本次:改善 75 / 不变 63 / 退化 1），比读代码推断可靠。
