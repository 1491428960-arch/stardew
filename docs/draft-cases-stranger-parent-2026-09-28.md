# 补 stranger / parent 评测 case（2026-09-28）

> **状态**：**未入库**。`bridge/src/stardew_ai_bridge/character_quality_eval.py` **一字未改**。
> **已实测**：§二的两个 case 已在**副本**上打补丁跑通（见 §四验证记录）。

---

## 一、为什么补这两档

**「初识」= `stranger`**（实测，**不是** `acquaintance`）。
artifact 里该阶段 **0 个 case**，而这两条约束只在它生效：

```
「初识阶段不得反问、邀约或主动换题；」
「初识阶段只起一句眼前的小事，不反问也不邀约；」
```

`parent` 同样 **0 个 case**，而它的 prompt 与 `married` **不同**
（6324 字 vs 7222 字，`stage_execution_card` 内容不一样），**一次都没跑过**。

⚠ 我 09-28 曾拿全阶段样本去测那条初识约束，得到一个 **8.8% 的无意义数字**。

---

## 二、⭐ 每加一个 case **必须改两处**（这是我实测才发现的）

```python
# 第 1 处：_BASE_CASES（L769 起）追加 CharacterQualityCase
# 第 2 处：_FOLLOW_UP_TURNS（L1830 起）追加两条续聊
```

原因在 `_materialize_quality_turns`：

```python
follow_ups = _FOLLOW_UP_TURNS.get(case.case_id, ())
if len(follow_ups) != 2:
    raise ValueError(f"角色质量案例缺少两轮续聊：{case.case_id}")
```

⇒ **只加第 1 处会直接抛 `ValueError`**。首轮 turn 是**自动生成**的
（`CharacterQualityTurn("turn-1", case.message, ...)`），
**续聊必须手写且恰好 2 条**。

### ✅ 已实测通过的两个 case（可直接用）

```python
# === 第 1 处：追加到 _BASE_CASES（注意 4 空格缩进 + 结尾逗号）===
_BASE_CASES = _BASE_CASES + (
    CharacterQualityCase(
        case_id="wizard-stranger-invitation",
        profile_key="wizard_rasmodia", npc_id="Wizard", display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",), relationship_stage="stranger",
        channel="remote", message="改天一起去矿洞看看？",
        game_state=_game_state(season="春", date="春 1 日", weather="晴天",
                               time=900, location="法师塔", friendshipHearts=0),
    ),
    CharacterQualityCase(
        case_id="shane-parent-child-safety",
        profile_key="shane", npc_id="Shane", display_name="Shane",
        source_mods=("vanilla", "female-bachelors"), relationship_stage="parent",
        channel="face_to_face", message="贾斯说想去矿洞。",
        game_state=_game_state(season="夏", date="夏 12 日", weather="晴天",
                               time=1400, location="牧场", friendshipHearts=12,
                               marriageStatus="married", childrenCount=1),
    ),
)

# === 第 2 处：追加到 _FOLLOW_UP_TURNS 字典（紧跟开括号之后即可）===
_FOLLOW_UP_TURNS: dict[str, tuple[CharacterQualityTurn, CharacterQualityTurn]] = {
    "wizard-stranger-invitation": (
        CharacterQualityTurn("turn-2", "那你有空的时候呢？",
                             (), (), "看初识阶段是否不反问、不邀约。"),
        CharacterQualityTurn("turn-3", "好吧，那我先走了。",
                             (), (), "看收尾是否自然，不挽留、不升级关系。"),
    ),
    "shane-parent-child-safety": (
        CharacterQualityTurn("turn-2", "你觉得需要注意什么？",
                             (), (), "看涉及孩子时是否先说安全和实际安排。"),
        CharacterQualityTurn("turn-3", "那我先跟他商量一下。",
                             (), (), "看是否给出可执行的下一步。"),
    ),
    # ... 原有条目保持不变 ...
}
```

⚠ **`_FOLLOW_UP_TURNS` 是字典字面量** —— 追加时**插进已有的 `{ }` 里**，
不要写成 `_FOLLOW_UP_TURNS = _FOLLOW_UP_TURNS + {...}`（那会**整体覆盖**）。

### ⭐ 这两个 case 的设计要点

**stranger 的场景必须刻意诱发违规**：`message` 本身就是**一个邀约**
（「改天一起去矿洞看看？」），`turn-2` 再追一句试探。
⇒ 按约束，NPC **不得接住并反向邀约、不得反问、不得主动开新话题**。
⇒ **若它回「那你也来」或反问「你呢？」，就是可观测的违规。**

⚠ 给一个**没机会违规**的输入（比如纯陈述句），通过率必然 100%
—— **那样什么也没证明**。

**parent 的场景试探 `boundaryMode`**：
「涉及孩子和魔法时**先解释风险**，不把成人秘密交给孩子承担」。
⇒ 若直接答「没事」，**就是可观测的违规**。

---

## 三、其余待补的 case（**还需补 `_FOLLOW_UP_TURNS`**）

§二那两个已实测可用。若要凑齐 5+5，其余 8 个**照同样格式补**即可，
`case_id` 与续聊的对应关系是唯一的硬约束。

建议的 `case_id`（含各自的话题意图，用于对齐约束）：

| case_id | 阶段 | 话题意图 |
|---|---|---|
| `wizard-stranger-invitation` | stranger | 邀约 ✅**已实测** |
| `sophia-stranger-invitation` | stranger | 邀约 |
| `shane-stranger-invitation` | stranger | 邀约 |
| `sebastian-stranger-open-topic` | stranger | 反问（开放式陈述） |
| `alex-stranger-open-topic` | stranger | 反问 |
| `shane-parent-child-safety` | parent | 孩子安全 ✅**已实测** |
| `sophia-parent-child-safety` | parent | 孩子安全 |
| `wizard-parent-child-disclosure` | parent | 该不该告诉孩子 |
| `sebastian-parent-child-safety` | parent | 孩子安全 |
| `alex-parent-child-safety` | parent | 孩子安全 |

⚠ **`friendshipHearts` 要用对**：stranger=**0**、parent=**12**（+ `childrenCount`）。
⚠ **`sourceMods` 要照抄现有条目**：wizard=`("Romanceable Rasmodius",)`、
sophia=`("Stardew Valley Expanded",)`、
shane/sebastian/alex 在 dating/married 用 `("vanilla","female-bachelors")`。

---

## 四、⭐ 验证记录（不是推测，是跑出来的）

**方法**：把整个 `stardew_ai_bridge` 包复制到 `E:\workspace\.scratch\patchtest\`，
**只在副本上**打补丁，真源码不动。

**第一次跑 → 抓到会造成阻塞的问题**：

```
ValueError: 角色质量案例缺少两轮续聊：wizard-stranger-invitation
```

⇒ 若不先验证就入库，**用户一跑就报错**。这个错只有真跑起来才会暴露。

**补上 `_FOLLOW_UP_TURNS` 后 → 通过**：

```
模块来源: .scratch\patchtest\...（确认为副本，非真源码）
并集 257 个 case（255 + 2）
阶段分布: {acquaintance:12, friend:44, close:20, married:124,
           dating:55, stranger:1, parent:1}     ← 从 0 变 1
[OK] wizard-stranger-invitation  stage=stranger  turns=3  hearts=0
     responseShape=像原版日常对白一样简短；能一句说清就不要补长段
[OK] shane-parent-child-safety   stage=parent    turns=3  hearts=12
     responseShape=可用 1–2 句，清楚、耐心；涉及孩子时先说安全和实际安排
```

⚠ **顺带修正一个我先前的笼统说法**：
`responseShape` **因角色而异**（Wizard 与 Shane 的 stranger 措辞不同），
所以我先前那句「stranger 的 responseShape 是…」**漏了角色限定**。

---

## 五、⚠ 入库前还需确认

1. **新 case 会进哪些 suite** —— 加进 `_BASE_CASES` 会进 `default`（47 → 49），
   但 `topic-start-*` 等 suite 是**另外生成**的，**未必带上** ⇒
   要先读 `quality_cases_for_suite`（L2578）的组装逻辑。
2. **跑全量测试** —— 可能有测试断言了 case 总数或阶段集合。
   ⚠ **要逐个看清是「断言该更新」还是「case 写错了」，不要直接改测试。**
3. **`childrenCount` 要给**：case 的 `relationship_stage` 本身足以让 policy 生效
   （已实测），但 prompt 内部会**从 `game_state` 再推导一次**阶段 ⇒
   缺了它，**声明的阶段与推导出的阶段可能不一致**。
