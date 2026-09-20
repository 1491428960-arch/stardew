# 事件锁案例数据补全报告（A / B / C 三类）

- 日期：2026-09-20
- worktree：`E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory`（分支 `codex/story-memory`）
- 范围：**只改评测案例数据与相关测试**。没有动事件锁判定逻辑，没有动 2026-09-20 新加的
  `passed` 规则（`character_quality_eval.py` 的 `and "event_gate_intimacy" not in tags`），
  没有碰 `ui_preview_page.py` / `ui_preview_redesign_page.py` / `app.py`。

---

## 一、三类数量汇总

| 类别 | 定义 | 受影响的唯一 case_id | 套件条目 | 处置 | 补数据后事件锁 |
|---|---|---|---|---|---|
| **A 类｜数据缺失** | 案例本身没问题，只是没写事件状态 | **169** | 176 | 按 `_EVENT_GATES` 同名档位补事件链 | 全部解除 |
| **B 类｜数据写错** | `topic-start-event-impact` 的 after 只声明单个被测事件 | **7** | 7 | 改成「被测事件 + 该角色 close 档完整链」 | after 全部解除 |
| **C 类｜确实该锁着** | 语义就是「这段剧情还没发生」的对照组 | **14** | 14 | 保持空元组，只补注释说明 | **保持不变（仍锁定）** |

- 受影响的唯一 case_id 合计：**190**（补数据前 `eventGateApplied=True` 的套件条目 197 条，去重后 190 个）。
- **实际补写范围比受影响面更大**：为了让「忘记声明」不再可能，本次给 **193** 个 A 类案例
  都写上了真实事件链，其中 169 个是补前被锁的，另外 24 个补前没触发锁
  （它们没有声明 `friendship_hearts`，事件锁提前返回）但数据同样缺失——顺手补齐，避免日后补上心数就突然被锁。
- 唯一 case_id 总数 255：207 个带真实事件链（A 193 + B 7），14 个 C 类对照组显式留空，
  34 个角色没有登记链（Sam / Marnie / Linus 等），按「该角色没有与关系阶段绑定的剧情事件」显式写空。

### 补数据前 vs 后：带 `event_gate_intimacy` 风险的案例数

| | 套件条目 | 唯一 case_id | 收窄到的阶段 |
|---|---|---|---|
| 补数据前 | **197** | **190** | 全部 `acquaintance` |
| 补数据后 | **14** | **14** | 全部 `acquaintance`（有意保留的 before 对照组） |

---

## 二、A 类：补了什么、依据是什么

### 补法

每个案例按**它自己声明的 `relationship_stage`** 补该角色对应档位的事件链：

| 案例声明阶段 | 补的登记档位 |
|---|---|
| `acquaintance`（2 心） | `acquaintance` 档 |
| `friend`（6 心） | `friend` 档 |
| `close`（8 心） | `close` 档 |
| `dating` / `married` / `parent` | `close` 档（登记表最高只到 close） |

依据是游戏事实：心数达到某档，就意味着该档之前的好感度事件必然已经走过；
`_EVENT_GATES` 的链本身就是**逐级累积**的（friend 档 = acquaintance 档 + 2 个 ID）。

### 关键 ID 的来历（逐条可追溯）

登记链全部逐字取自 `bridge/src/stardew_ai_bridge/relationship_gating.py` 的 `_EVENT_GATES`
（第 139–175 行）。我用 `data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue-v3.json`
的 `speechEvidence[].eventConditions.raw` 复核了每个 ID 的好感度条件：

| 角色 | acquaintance 档 | friend 档追加 | close 档追加 | 复核到的原始条件 |
|---|---|---|---|---|
| Wizard | `1000075` | `1724096` | `1724097` | `f Wizard 500` / `1500` / `2000`（SVE） |
| Sophia | `8185291` | `8185292`, `8185293` | `8185295` | `f Sophia 500` / `1000` / `1500` / `2000`（SVE） |
| Shane | `611944` | `3910674`, `3910975` | `3900074` | `f Shane 500` / `1000` / `1500` / `2000` |
| Sebastian | `2794460` | `384883`, `27` | `29` | `f Sebastian 1000` / `1500` / `2000` |
| Alex | `20` | `2481135`, `2119820` | `288847` | `f Alex 500` / `1000` / `1500` / `2000` |
| Elliott | `39` | `40`, `423502` | `1848481` | `f Elliott 500` / `1000` / `1500` / `2000` |
| Harvey | `56` | `57`, `58` | `571102` | `f Harvey 500` / `1000` / `1500` / `2000` |

规律很干净：**每个角色的链就是 2 / 4 / 6 / 8 心四档好感度事件**。

> 说明：Sebastian 的 acquaintance 档 `2794460` 在这份 profile index 的 `speechEvidence`
> 里检索不到条目，沿用 `_EVENT_GATES` 的登记值（没有另行编造）；其余 24 个 ID 都复核到了
> 原始条件。`relationship-stage-gating` 的 7 个 after 案例上一轮就已带完整链，本次未改动。

### 落地方式

各案例工厂（`_topic_case` / `_target` / `_control` / `_case` / `_feminine_male_case`）
新增了 **无默认值的必填参数** `completed_event_ids`，每个调用点逐条写出字面元组：

```
case_id="wizard-dating-invite",
completed_event_ids=("1000075", "1724096", "1724097"),
```

刻意不给默认值：`()` 在事件锁里的含义是「这些事件都没发生」，
**「忘记声明」与「声明为空」必须变成两件事**——这正是本次数据问题的根因。
`topic-start-adaptive` 的 41 个案例由 `topic-start-intimacy` 派生，自动继承，无需重复声明。

共修改 165 处字面案例调用 + 12 处循环生成的案例 + 8 个工厂签名。

---

## 三、B 类：`topic-start-event-impact` 的 14 个案例

### 查明的真相：**ID 没写错，错的是漏了关系链**

三个「不在登记链里」的 ID，逐个查回了原始事件条件（同样来自 profile index 的
`speechEvidence[].eventConditions.raw`）：

| 被测 ID | 原始条件 | 它是什么 | 为什么不在 `_EVENT_GATES` 里 |
|---|---|---|---|
| `112` | `112/n seenJunimoNote` | Wizard 的祝尼魔卷轴剧情事件（vanilla） | 条件里**没有好感度**，是玩家进度事件，不是关系节点 |
| `384882` | `384882/f Sebastian 2500/t 2000 2400` | Sebastian 的 **10 心**骑摩托事件 | 高于登记表最高档 close（8 心） |
| `8185290` | `8185290/w sunny/c 1/t 600 1500/z winter/z fall/y 1/f Sophia 50` | Sophia 的**初见**事件（SVE） | 低于登记表最低档 acquaintance（2 心） |

另外 4 个（`20` / `40` / `56` / `3900074`）本身就在链里。

这正好对上 `relationship_gating.py` 的登记纪律注释：
> 这里只登记已从原版/SVE 事件条件核对过的节点。事件素材里存在的其他节点仍然可以作为
> completedEventIds 门控素材，但不会被误当成关系阶段解锁条件。

**真正的错**在于：after 侧整组只声明了单个被测事件，等于宣称「2/4/6/8 心的关系事件都没发生」，
于是已婚 10 心的案例被事件锁压回 acquaintance——这不是本套件要测的「事件记忆差异」，
而是关系状态被写错。

### 改法

- **after**：`completed_event_ids` = 该角色 close 档完整链 + 被测事件（若不在链里，追加在链尾并注明原因）。
- **before**：保持 `()`，并在 `EVENT_IMPACT_SPECS` 与 `_build_case` 处写明「这一侧要测的正是事件没发生」。

| pair | after 声明的事件集合 |
|---|---|
| `wizard-112` | `1000075 / 1724096 / 1724097 / 112` |
| `shane-3900074` | `611944 / 3910674 / 3910975 / 3900074` |
| `sebastian-384882` | `2794460 / 384883 / 27 / 29 / 384882` |
| `alex-20` | `20 / 2481135 / 2119820 / 288847` |
| `elliott-40` | `39 / 40 / 423502 / 1848481` |
| `harvey-56` | `56 / 57 / 58 / 571102` |
| `sophia-8185290` | `8185291 / 8185292 / 8185293 / 8185295 / 8185290` |

---

## 四、C 类：确实该锁着，只补注释

两类 before 对照组合计 **14** 个，`completed_event_ids=()` 是**设计的一部分**，不能补：

1. `relationship-stage-gating` 的 7 个 before —— 案例语义就是「事件链尚未完成」，
   是事件锁的对照组；补了就没有「事件前」这个变量了。
2. `topic-start-event-impact` 的 7 个 before —— 语义是「这个具体事件还没发生」。

两处都补了显式注释，说明空元组是有意保留、不是漏写。回归保护见
`test_event_gate_case_data.py::test_c_class_before_cases_keep_their_locked_behaviour`
与 `test_only_intentional_control_cases_remain_event_gated`：全量案例里**只允许**
这 14 个保持锁定，新增的漏写案例会让测试立刻失败。

---

## 五、测试

### 全量实测

```
$env:PYTHONPATH='bridge/src;scripts'; $env:PYTHONIOENCODING='utf-8'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest bridge/tests -q -p no:cacheprovider

3184 passed in 92.85s (0:01:32)
```

（改动完成后完整跑了两次，两次都是 3184 passed；一次 84.96s，一次 92.85s。）

### 新增/更新的自证测试

新文件 `bridge/tests/test_event_gate_case_data.py`（7 条）：

| 测试 | 覆盖 |
|---|---|
| `test_only_intentional_control_cases_remain_event_gated` | A 类自证：全量案例里被锁的**只允许**是 14 个 C 类白名单 |
| `test_a_class_cases_declare_the_gate_chain_of_their_stage` | A 类自证：每个案例声明的事件链与登记表同名档位逐字一致，且不再被锁（覆盖 ≥190 个案例） |
| `test_b_class_event_impact_after_unlocks_and_before_stays_locked` | B 类自证：after 解锁到 close、before 仍锁在 acquaintance；after 含被测事件 + 完整链 |
| `test_c_class_before_cases_keep_their_locked_behaviour` | C 类自证：14 个对照组的锁定行为不变 |
| `test_case_factories_require_explicit_event_state` | 用 `inspect.signature` 钉住 8 个工厂的 `completed_event_ids` **没有默认值**，防止再出现「忘记声明」 |
| `test_married_case_intimacy_line_is_no_longer_gated` | 端到端：补数据后婚后台词 `passed=True` 且无 `event_gate_intimacy` |
| `test_the_same_line_still_fails_while_the_event_gate_is_closed` | 对照：同一句在 C 类案例里仍越界（证明只补数据、没关规则） |

更新的既有测试：

- `test_event_impact_cases.py`：after 断言从「等于单个被测事件」改为「包含被测事件 + 完整链」。
- `test_character_quality_eval.py`：`shane-close-boundary` 的断言从内容库别名
  `("vanilla:shane-heart-6",)` 改为 close 档游戏 ID 链；`sebastian-married-music` 那处
  手工 `replace` 的补丁删除，直接用案例自带数据。
- `test_dialogue_boundary_semantics.py`：只更新 `_event_gate_case` 的 docstring（该别名已不存在）。

---

## 六、我拿不准、需要你或用户判断的

1. **B 类 before 的语义张力（最需要定夺）**
   现在 before 声明的是「什么都没完成」，而不是「只有这个事件没发生」。
   从游戏事实看，已婚 10 心的 before 更应该是「close 链已完成、只有被测事件未发生」，
   但那样 before 就不再锁定了，与你给的验收口径（「before 案例应仍锁定」）冲突。
   我按你的口径执行。若希望 before 贴近游戏事实，可改为「close 链 − 被测事件」
   （`20` / `40` / `56` / `3900074` 在链里可以减；`112` / `384882` / `8185290`
   不在链里，before 就等于 close 链）——代价是对照组不再是「低权限状态」。

2. **`sophia-8185290` 这个 pair 的有效性**
   它的 `event_source_status` 已经是 `unresolved_i18n`（事件原文只有 i18n 占位符），
   而事件本身是 `f Sophia 50` 的**初见**事件，却挂在「婚后 studio」场景上。
   我按要求让 after 解锁了，但这一对能否有效测「事件记忆差异」值得确认；
   若认为没有测量价值，建议单独下线，而不是继续补数据。

3. **`sebastian-384882` 的档位归属**
   `f Sebastian 2500`（10 心）是恋人/婚后阶段的事件，高于登记表最高档。
   我把它追加在 close 链尾部。如果日后要给 `_EVENT_GATES` 补 dating/married 档，
   这个 ID 应该是首选候选——但那属于改登记表，不在本次范围。

4. **5 个 `default` 案例只有 stage、没有 `friendship_hearts`**
   `wizard-close-background`、`sophia-close-background`、`shane-close-boundary`、
   `alex-close-background`、`sebastian-married-life`：`game_state` 里写了
   `friendshipHearts=8/10`，但 dataclass 字段是 `None`，而 `_event_gate_payload`
   只读 dataclass 字段 → 事件锁对它们**永远不生效**。
   我给它们补了与 stage 一致的链（数据自洽），但只要 `friendship_hearts` 仍是 `None`，
   锁就不会触发。这是独立的「事件锁输入不完整」问题，改它要动 `_event_gate_payload`
   的取值口径（`case.friendship_hearts` vs `_case_friendship_hearts(case)` 会回退到
   `game_state`），我没动，等你定。

5. **`shane-close-boundary` 原来的 `vanilla:shane-heart-6`**
   这是内容库别名，`game_event_id_tokens` 不认语义别名（只认命名空间前缀与分隔符差异），
   所以事件锁识别不了它。我换成了 `_EVENT_GATES["Shane"]` 的 close 档链
   （6 心事件 `3910975` 在链内，语义保留）。它同样因 `friendship_hearts=None`
   目前不受锁影响，行为不变。

6. **要不要把「必填」下沉到 dataclass**
   现在必填只落在案例工厂；`CharacterQualityCase.completed_event_ids` 的默认值仍是 `()`。
   如果希望彻底消除这个默认值，需要改 dataclass 并排查所有直接构造点（含测试与工具），
   影响面更大，我没有自行决定。

7. **是否需要一条「未声明就按阶段推导」的兜底**
   按你的要求**没有加**，一行推导都没有。如果你认为某处确实该有（例如运行时输入
   缺 `completedEventIds` 时按 hearts 推导），请明示，那应该落在运行时/输入层，
   与本次「补评测数据」分开做。

---

## 七、附：全量案例清单

### A 类｜数据缺失：按登记表补上对应阶段的事件链（193 个）

| case_id | 角色 | 案例声明阶段 | 补的事件链（来自 `_EVENT_GATES` 同名档位） | 所在套件 |
|---|---|---|---|---|
| `adaptive-topic-alex-dating-beach` | Alex | dating → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-adaptive |
| `adaptive-topic-alex-dating-gym` | Alex | dating → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-adaptive |
| `adaptive-topic-alex-married-beach` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-adaptive |
| `adaptive-topic-alex-married-dinner` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-adaptive |
| `adaptive-topic-alex-married-evening` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-adaptive |
| `adaptive-topic-control-alex-friend-training` | Alex | friend → friend 档 | 20 / 2481135 / 2119820 | topic-start-adaptive |
| `adaptive-topic-control-elliott-friend-writing` | Elliott | friend → friend 档 | 39 / 40 / 423502 | topic-start-adaptive |
| `adaptive-topic-control-harvey-friend-clinic` | Harvey | friend → friend 档 | 56 / 57 / 58 | topic-start-adaptive |
| `adaptive-topic-control-sebastian-friend-music` | Sebastian | friend → friend 档 | 2794460 / 384883 / 27 | topic-start-adaptive |
| `adaptive-topic-control-shane-acquaintance-coop` | Shane | acquaintance → acquaintance 档 | 611944 | topic-start-adaptive |
| `adaptive-topic-control-shane-friend-rest` | Shane | friend → friend 档 | 611944 / 3910674 / 3910975 | topic-start-adaptive |
| `adaptive-topic-control-sophia-friend-vineyard` | Sophia | friend → friend 档 | 8185291 / 8185292 / 8185293 | topic-start-adaptive |
| `adaptive-topic-control-wizard-friend-records` | Wizard | friend → friend 档 | 1000075 / 1724096 | topic-start-adaptive |
| `adaptive-topic-elliott-dating-poem` | Elliott | dating → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-adaptive |
| `adaptive-topic-elliott-dating-sea` | Elliott | dating → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-adaptive |
| `adaptive-topic-elliott-married-letter` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-adaptive |
| `adaptive-topic-elliott-married-reading` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-adaptive |
| `adaptive-topic-elliott-married-studio` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-adaptive |
| `adaptive-topic-harvey-dating-coffee` | Harvey | dating → close 档 | 56 / 57 / 58 / 571102 | topic-start-adaptive |
| `adaptive-topic-harvey-dating-rest` | Harvey | dating → close 档 | 56 / 57 / 58 / 571102 | topic-start-adaptive |
| `adaptive-topic-harvey-married-check-in` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | topic-start-adaptive |
| `adaptive-topic-harvey-married-clinic` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | topic-start-adaptive |
| `adaptive-topic-harvey-married-heartbeat` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | topic-start-adaptive |
| `adaptive-topic-sebastian-dating-mixtape` | Sebastian | dating → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-adaptive |
| `adaptive-topic-sebastian-dating-rooftop` | Sebastian | dating → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-adaptive |
| `adaptive-topic-sebastian-married-basement` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-adaptive |
| `adaptive-topic-sebastian-married-bike` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-adaptive |
| `adaptive-topic-sebastian-married-game` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-adaptive |
| `adaptive-topic-shane-dating-coop` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | topic-start-adaptive |
| `adaptive-topic-shane-dating-rest` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | topic-start-adaptive |
| `adaptive-topic-shane-married-home` | Shane | married → close 档 | 611944 / 3910674 / 3910975 / 3900074 | topic-start-adaptive |
| `adaptive-topic-shane-married-pizza` | Shane | married → close 档 | 611944 / 3910674 / 3910975 / 3900074 | topic-start-adaptive |
| `adaptive-topic-sophia-dating-grapes` | Sophia | dating → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-adaptive |
| `adaptive-topic-sophia-dating-painting` | Sophia | dating → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-adaptive |
| `adaptive-topic-sophia-married-cellar` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-adaptive |
| `adaptive-topic-sophia-married-studio` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-adaptive |
| `adaptive-topic-sophia-married-vineyard` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-adaptive |
| `adaptive-topic-wizard-dating-moonlight` | Wizard | dating → close 档 | 1000075 / 1724096 / 1724097 | topic-start-adaptive |
| `adaptive-topic-wizard-dating-tea` | Wizard | dating → close 档 | 1000075 / 1724096 / 1724097 | topic-start-adaptive |
| `adaptive-topic-wizard-married-dinner` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | topic-start-adaptive |
| `adaptive-topic-wizard-married-lantern` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | topic-start-adaptive |
| `adaptive-topic-wizard-married-study` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | topic-start-adaptive |
| `alex-close-background` | Alex | close → close 档 | 20 / 2481135 / 2119820 / 288847 | default |
| `alex-dating-beach` | Alex | dating → close 档 | 20 / 2481135 / 2119820 / 288847 | default |
| `alex-follow-up` | Alex | friend → friend 档 | 20 / 2481135 / 2119820 | default |
| `alex-married-evening` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | default, conversation-lead |
| `alex-remote-invite` | Alex | friend → friend 档 | 20 / 2481135 / 2119820 | default |
| `alex-training` | Alex | acquaintance → acquaintance 档 | 20 | default |
| `deep-flirt-alex-married` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | deep-flirt |
| `deep-flirt-elliott-married` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | deep-flirt |
| `deep-flirt-harvey-married` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | deep-flirt |
| `deep-flirt-intimate-alex-married` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | deep-flirt-intimate |
| `deep-flirt-intimate-elliott-married` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | deep-flirt-intimate |
| `deep-flirt-intimate-harvey-married` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | deep-flirt-intimate |
| `deep-flirt-intimate-sebastian-married` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | deep-flirt-intimate |
| `deep-flirt-intimate-shane-dating` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | deep-flirt-intimate |
| `deep-flirt-intimate-sophia-married` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | deep-flirt-intimate |
| `deep-flirt-intimate-wizard-married` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | deep-flirt-intimate |
| `deep-flirt-sebastian-married` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | deep-flirt |
| `deep-flirt-shane-dating` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | deep-flirt |
| `deep-flirt-sophia-married` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | deep-flirt |
| `deep-flirt-wizard-married` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | deep-flirt |
| `elliott-close-studio` | Elliott | close → close 档 | 39 / 40 / 423502 / 1848481 | default |
| `elliott-daily` | Elliott | acquaintance → acquaintance 档 | 39 | default |
| `elliott-dating-letter` | Elliott | dating → close 档 | 39 / 40 / 423502 / 1848481 | default |
| `elliott-follow-up` | Elliott | friend → friend 档 | 39 / 40 / 423502 | default |
| `elliott-married-studio` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | default, conversation-lead |
| `harvey-close-clinic` | Harvey | close → close 档 | 56 / 57 / 58 / 571102 | default |
| `harvey-daily` | Harvey | acquaintance → acquaintance 档 | 56 | default |
| `harvey-dating-check-in` | Harvey | dating → close 档 | 56 / 57 / 58 / 571102 | default |
| `harvey-follow-up` | Harvey | friend → friend 档 | 56 / 57 / 58 | default |
| `harvey-married-clinic` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | default, conversation-lead |
| `pacing-alex-evening-plan` | Alex | close → close 档 | 20 / 2481135 / 2119820 / 288847 | affection-pacing |
| `pacing-alex-explicit-love-request` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | affection-pacing |
| `pacing-alex-friend-training` | Alex | friend → friend 档 | 20 / 2481135 / 2119820 | affection-pacing |
| `pacing-alex-training-tease` | Alex | dating → close 档 | 20 / 2481135 / 2119820 / 288847 | affection-pacing |
| `pacing-elliott-close-sketch` | Elliott | close → close 档 | 39 / 40 / 423502 / 1848481 | affection-pacing |
| `pacing-elliott-dating-letter` | Elliott | dating → close 档 | 39 / 40 / 423502 / 1848481 | affection-pacing |
| `pacing-elliott-friend-writing` | Elliott | friend → friend 档 | 39 / 40 / 423502 | affection-pacing |
| `pacing-elliott-studio-share` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | affection-pacing |
| `pacing-harvey-clinic-care` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | affection-pacing |
| `pacing-harvey-close-coffee` | Harvey | close → close 档 | 56 / 57 / 58 / 571102 | affection-pacing |
| `pacing-harvey-dating-check` | Harvey | dating → close 档 | 56 / 57 / 58 / 571102 | affection-pacing |
| `pacing-harvey-friend-clinic` | Harvey | friend → friend 档 | 56 / 57 / 58 | affection-pacing |
| `pacing-sebastian-bike-plan` | Sebastian | close → close 档 | 2794460 / 384883 / 27 / 29 | affection-pacing |
| `pacing-sebastian-explicit-love-request` | Sebastian | dating → close 档 | 2794460 / 384883 / 27 / 29 | affection-pacing |
| `pacing-sebastian-friend-music` | Sebastian | friend → friend 档 | 2794460 / 384883 / 27 | affection-pacing |
| `pacing-sebastian-music-approach` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | affection-pacing |
| `pacing-shane-closeout` | Shane | married → close 档 | 611944 / 3910674 / 3910975 / 3900074 | affection-pacing |
| `pacing-shane-friend-care` | Shane | friend → friend 档 | 611944 / 3910674 / 3910975 | affection-pacing |
| `pacing-shane-low-mood` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | affection-pacing |
| `pacing-shane-ordinary-coop` | Shane | close → close 档 | 611944 / 3910674 / 3910975 / 3900074 | affection-pacing |
| `pacing-sophia-cellar-sharing` | Sophia | dating → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | affection-pacing |
| `pacing-sophia-explicit-love-request` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | affection-pacing |
| `pacing-sophia-friend-painting` | Sophia | friend → friend 档 | 8185291 / 8185292 / 8185293 | affection-pacing |
| `pacing-sophia-vineyard-evening` | Sophia | close → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | affection-pacing |
| `pacing-wizard-explicit-love-request` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | affection-pacing |
| `pacing-wizard-friend-records` | Wizard | friend → friend 档 | 1000075 / 1724096 | affection-pacing |
| `pacing-wizard-ordinary-evening` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | affection-pacing |
| `pacing-wizard-research-followup` | Wizard | dating → close 档 | 1000075 / 1724096 / 1724097 | affection-pacing |
| `relationship-alex-jealousy-recovery` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | relationship-world |
| `relationship-alex-mediation` | Alex | dating → close 档 | 20 / 2481135 / 2119820 / 288847 | relationship-world |
| `relationship-alex-npc-initiated-jealousy` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | relationship-world |
| `relationship-alex-view-gap` | Alex | close → close 档 | 20 / 2481135 / 2119820 / 288847 | relationship-world |
| `relationship-elliott-jealousy-recovery` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | relationship-world |
| `relationship-elliott-mediation` | Elliott | dating → close 档 | 39 / 40 / 423502 / 1848481 | relationship-world |
| `relationship-elliott-npc-initiated-jealousy` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | relationship-world |
| `relationship-elliott-view-gap` | Elliott | friend → friend 档 | 39 / 40 / 423502 | relationship-world |
| `relationship-harvey-jealousy-recovery` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | relationship-world |
| `relationship-harvey-mediation` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | relationship-world |
| `relationship-harvey-npc-initiated-jealousy` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | relationship-world |
| `relationship-harvey-view-gap` | Harvey | friend → friend 档 | 56 / 57 / 58 | relationship-world |
| `relationship-sebastian-jealousy-recovery` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | relationship-world |
| `relationship-sebastian-mediation` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | relationship-world |
| `relationship-sebastian-npc-initiated-jealousy` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | relationship-world |
| `relationship-sebastian-view-gap` | Sebastian | friend → friend 档 | 2794460 / 384883 / 27 | relationship-world |
| `relationship-shane-jealousy-recovery` | Shane | married → close 档 | 611944 / 3910674 / 3910975 / 3900074 | relationship-world |
| `relationship-shane-mediation` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | relationship-world |
| `relationship-shane-npc-initiated-jealousy` | Shane | married → close 档 | 611944 / 3910674 / 3910975 / 3900074 | relationship-world |
| `relationship-shane-view-gap` | Shane | close → close 档 | 611944 / 3910674 / 3910975 / 3900074 | relationship-world |
| `relationship-sophia-jealousy-recovery` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | relationship-world |
| `relationship-sophia-mediation` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | relationship-world |
| `relationship-sophia-npc-initiated-jealousy` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | relationship-world |
| `relationship-sophia-view-gap` | Sophia | friend → friend 档 | 8185291 / 8185292 / 8185293 | relationship-world |
| `relationship-wizard-jealousy-recovery` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | relationship-world |
| `relationship-wizard-mediation` | Wizard | dating → close 档 | 1000075 / 1724096 / 1724097 | relationship-world |
| `relationship-wizard-npc-initiated-jealousy` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | relationship-world |
| `relationship-wizard-view-gap` | Wizard | close → close 档 | 1000075 / 1724096 / 1724097 | relationship-world |
| `sebastian-bike` | Sebastian | acquaintance → acquaintance 档 | 2794460 | default |
| `sebastian-dating-rooftop` | Sebastian | dating → close 档 | 2794460 / 384883 / 27 / 29 | default |
| `sebastian-follow-up` | Sebastian | friend → friend 档 | 2794460 / 384883 / 27 | default |
| `sebastian-married-life` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | default |
| `sebastian-married-music` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | default, conversation-lead |
| `sebastian-rain` | Sebastian | friend → friend 档 | 2794460 / 384883 / 27 | default |
| `shane-close-boundary` | Shane | close → close 档 | 611944 / 3910674 / 3910975 / 3900074 | default |
| `shane-coop` | Shane | acquaintance → acquaintance 档 | 611944 | default |
| `shane-dating-boundary` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | default, conversation-lead |
| `shane-follow-up` | Shane | friend → friend 档 | 611944 / 3910674 / 3910975 | default |
| `shane-remote-care` | Shane | friend → friend 档 | 611944 / 3910674 / 3910975 | default |
| `sophia-close-background` | Sophia | close → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | default |
| `sophia-daily` | Sophia | acquaintance → acquaintance 档 | 8185291 | default |
| `sophia-dating-wine` | Sophia | dating → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | default |
| `sophia-face-follow-up` | Sophia | friend → friend 档 | 8185291 / 8185292 / 8185293 | default |
| `sophia-married-cellar` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | default, conversation-lead |
| `sophia-vineyard` | Sophia | friend → friend 档 | 8185291 / 8185292 / 8185293 | default |
| `topic-alex-dating-beach` | Alex | dating → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-intimacy |
| `topic-alex-dating-gym` | Alex | dating → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-intimacy |
| `topic-alex-married-beach` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-intimacy |
| `topic-alex-married-dinner` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-intimacy |
| `topic-alex-married-evening` | Alex | married → close 档 | 20 / 2481135 / 2119820 / 288847 | topic-start-intimacy |
| `topic-control-alex-friend-training` | Alex | friend → friend 档 | 20 / 2481135 / 2119820 | topic-start-intimacy |
| `topic-control-elliott-friend-writing` | Elliott | friend → friend 档 | 39 / 40 / 423502 | topic-start-intimacy |
| `topic-control-harvey-friend-clinic` | Harvey | friend → friend 档 | 56 / 57 / 58 | topic-start-intimacy |
| `topic-control-sebastian-friend-music` | Sebastian | friend → friend 档 | 2794460 / 384883 / 27 | topic-start-intimacy |
| `topic-control-shane-acquaintance-coop` | Shane | acquaintance → acquaintance 档 | 611944 | topic-start-intimacy |
| `topic-control-shane-friend-rest` | Shane | friend → friend 档 | 611944 / 3910674 / 3910975 | topic-start-intimacy |
| `topic-control-sophia-friend-vineyard` | Sophia | friend → friend 档 | 8185291 / 8185292 / 8185293 | topic-start-intimacy |
| `topic-control-wizard-friend-records` | Wizard | friend → friend 档 | 1000075 / 1724096 | topic-start-intimacy |
| `topic-elliott-dating-poem` | Elliott | dating → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-intimacy |
| `topic-elliott-dating-sea` | Elliott | dating → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-intimacy |
| `topic-elliott-married-letter` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-intimacy |
| `topic-elliott-married-reading` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-intimacy |
| `topic-elliott-married-studio` | Elliott | married → close 档 | 39 / 40 / 423502 / 1848481 | topic-start-intimacy |
| `topic-harvey-dating-coffee` | Harvey | dating → close 档 | 56 / 57 / 58 / 571102 | topic-start-intimacy |
| `topic-harvey-dating-rest` | Harvey | dating → close 档 | 56 / 57 / 58 / 571102 | topic-start-intimacy |
| `topic-harvey-married-check-in` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | topic-start-intimacy |
| `topic-harvey-married-clinic` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | topic-start-intimacy |
| `topic-harvey-married-heartbeat` | Harvey | married → close 档 | 56 / 57 / 58 / 571102 | topic-start-intimacy |
| `topic-sebastian-dating-mixtape` | Sebastian | dating → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-intimacy |
| `topic-sebastian-dating-rooftop` | Sebastian | dating → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-intimacy |
| `topic-sebastian-married-basement` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-intimacy |
| `topic-sebastian-married-bike` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-intimacy |
| `topic-sebastian-married-game` | Sebastian | married → close 档 | 2794460 / 384883 / 27 / 29 | topic-start-intimacy |
| `topic-shane-dating-coop` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | topic-start-intimacy |
| `topic-shane-dating-rest` | Shane | dating → close 档 | 611944 / 3910674 / 3910975 / 3900074 | topic-start-intimacy |
| `topic-shane-married-home` | Shane | married → close 档 | 611944 / 3910674 / 3910975 / 3900074 | topic-start-intimacy |
| `topic-shane-married-pizza` | Shane | married → close 档 | 611944 / 3910674 / 3910975 / 3900074 | topic-start-intimacy |
| `topic-sophia-dating-grapes` | Sophia | dating → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-intimacy |
| `topic-sophia-dating-painting` | Sophia | dating → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-intimacy |
| `topic-sophia-married-cellar` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-intimacy |
| `topic-sophia-married-studio` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-intimacy |
| `topic-sophia-married-vineyard` | Sophia | married → close 档 | 8185291 / 8185292 / 8185293 / 8185295 | topic-start-intimacy |
| `topic-wizard-dating-moonlight` | Wizard | dating → close 档 | 1000075 / 1724096 / 1724097 | topic-start-intimacy |
| `topic-wizard-dating-tea` | Wizard | dating → close 档 | 1000075 / 1724096 / 1724097 | topic-start-intimacy |
| `topic-wizard-married-dinner` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | topic-start-intimacy |
| `topic-wizard-married-lantern` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | topic-start-intimacy |
| `topic-wizard-married-study` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | topic-start-intimacy |
| `wizard-close-background` | Wizard | close → close 档 | 1000075 / 1724096 / 1724097 | default |
| `wizard-daily` | Wizard | acquaintance → acquaintance 档 | 1000075 | default |
| `wizard-dating-invite` | Wizard | dating → close 档 | 1000075 / 1724096 / 1724097 | default |
| `wizard-follow-up` | Wizard | friend → friend 档 | 1000075 / 1724096 | default |
| `wizard-married-evening` | Wizard | married → close 档 | 1000075 / 1724096 / 1724097 | default, conversation-lead |
| `wizard-remote-invite` | Wizard | friend → friend 档 | 1000075 / 1724096 | default |

### B 类｜数据写错：after 侧只声明单个事件（7 个）

| case_id | 角色 | 声明的事件集合（close 档链 + 被测事件） |
|---|---|---|
| `event-impact-alex-20-after` | Alex | 20 / 2481135 / 2119820 / 288847 |
| `event-impact-elliott-40-after` | Elliott | 39 / 40 / 423502 / 1848481 |
| `event-impact-harvey-56-after` | Harvey | 56 / 57 / 58 / 571102 |
| `event-impact-sebastian-384882-after` | Sebastian | 2794460 / 384883 / 27 / 29 / 384882 |
| `event-impact-shane-3900074-after` | Shane | 611944 / 3910674 / 3910975 / 3900074 |
| `event-impact-sophia-8185290-after` | Sophia | 8185291 / 8185292 / 8185293 / 8185295 / 8185290 |
| `event-impact-wizard-112-after` | Wizard | 1000075 / 1724096 / 1724097 / 112 |

### C 类｜确实该锁着：事件未发生的对照组（14 个）

| case_id | 角色 | 案例声明阶段 | 保留的事件状态 |
|---|---|---|---|
| `event-impact-alex-20-before` | Alex | married | `()`（有意为空） |
| `event-impact-elliott-40-before` | Elliott | married | `()`（有意为空） |
| `event-impact-harvey-56-before` | Harvey | married | `()`（有意为空） |
| `event-impact-sebastian-384882-before` | Sebastian | married | `()`（有意为空） |
| `event-impact-shane-3900074-before` | Shane | married | `()`（有意为空） |
| `event-impact-sophia-8185290-before` | Sophia | married | `()`（有意为空） |
| `event-impact-wizard-112-before` | Wizard | married | `()`（有意为空） |
| `relationship-gate-alex-before` | Alex | married | `()`（有意为空） |
| `relationship-gate-elliott-before` | Elliott | married | `()`（有意为空） |
| `relationship-gate-harvey-before` | Harvey | married | `()`（有意为空） |
| `relationship-gate-sebastian-before` | Sebastian | married | `()`（有意为空） |
| `relationship-gate-shane-before` | Shane | married | `()`（有意为空） |
| `relationship-gate-sophia-before` | Sophia | married | `()`（有意为空） |
| `relationship-gate-wizard-before` | Wizard | married | `()`（有意为空） |

