# 草案（**部分内容已被取代**）：补 stranger / parent 两档评测 case（2026-09-28）

> ⚠⚠ **请优先读 `docs/draft-cases-stranger-parent-2026-09-28.md`。**
>
> 本文件是我**走弯路时**写的版本，其中两点已被后续实测推翻，**不要照它实施**：
>
> 1. 落点写成评测场景 / JSON 文件 —— **错**。真正的落点是
>    **`bridge/src/stardew_ai_bridge/character_quality_eval.py`**
>    的 `_BASE_CASES` **和** `_FOLLOW_UP_TURNS`（**两处**，不是一处）。
> 2. 只写了 `CharacterQualityCase`、**漏了 `_FOLLOW_UP_TURNS`** ——
>    会直接抛 `ValueError: 角色质量案例缺少两轮续聊`。**这是实测跑出来的。**
>
> **本文件仍有价值的部分**：`responseShape` 阶段对照表、
> 以及「阶段对了但话题不对」的分析过程。**结论以新文件为准。**
> ⚠ 且 `responseShape` **因角色而异**（Wizard 与 Shane 的 stranger 措辞不同），
> 本表取自**单一角色**，勿当成全局值。

> **状态**：**草案，未入库**。`bridge/src/stardew_ai_bridge/character_quality_eval.py` **一个字没改**。
> **用途**：等 `responseRules[0]` 实验（额度 10-01 恢复）时**一并补跑**这两档。

---

## 一、⚠ 先纠正一个方向性错误（我走了两段弯路）

我起初以为「补数据」是改
`data/personas/behavior-quality-scenarios.json`。**错了，而且是错了两次**：

| 我一度以为 | 实际 |
|---|---|
| 该 JSON 是评测 case 的定义 | ❌ 它是**本地行为样本生成器**的输入。`generate_behavior_examples.py` 的 `--provider` **只有 `local`**（走 Ollama），**与云端评测无关** |
| 第二列看 `DEFAULT_CASES`（47 个）就够 | ❌ artifact 里 married 跑过 **59** 个，**比 default 还多** ⇒ case 来自**多个 suite** |

**正确的落点**：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
里的 `_BASE_CASES`（L769 起），以及 `DEFAULT_CASES`（L2531）与
`quality_cases_for_suite`（L2578）的组装。

**正确的「可跑的」口径**：全部 suite 的并集 = **255 个 case**。
阶段分布：married 124 / dating 55 / friend 44 / close 20 / acquaintance 12 /
**stranger 0 / parent 0**。

---

## 二、⭐ 好消息：两个阶段**已经完全被支持**，只是没有 case

```python
_RELATIONSHIP_STAGES = {
    "stranger", "acquaintance", "friend", "close", "dating", "married", "parent",
}

def _case_friendship_hearts(case):
    ...
    return {
        "stranger": 0, "acquaintance": 2, "friend": 6, "close": 8,
        "dating": 8, "married": 10, "parent": 10,
    }.get(case.relationship_stage, 0)
```

⇒ **∪ 校验白名单里有、好感度默认值也有** ⇒ **不用改任何逻辑，只需加数据。**
⇒ 我原本估计要「新造场景 + 改加载端」，**实际只要往 `_BASE_CASES` 里加条目**。

### ⚠ `parent` 与 `childrenCount` 的关系（**我一开始说反了，已实测更正**）

我最初写「不给 `childrenCount` 就会静默落回 `married`」。**实测证明不对**：

```
case.relationship_stage = "parent"  ⇒  build_stage_policy() 直接返回 parent 的 policy
     responseShape = "可用 1–2 句，清楚、耐心；涉及孩子时先说安全和实际安排"
```

⇒ **case 的 `relationship_stage` 是直接给出的**，policy 直接认它，
**不需要 `childrenCount` 参与**。

**但仍然必须给 `childrenCount`** —— 理由不同：prompt 内部会**从 `game_state` 推导**阶段
（那是一条由好感 + `marriageStatus` + `childrenCount` 组成的推导链）。
若 `game_state` 里缺 `childrenCount`，
**case 声明的阶段与 prompt 内部推导出的阶段可能不一致**
⇒ 测的就不是 parent 分支了。

---

## ⭐ 顺带实测到的：七个阶段的 `responseShape` 原文

| 阶段 | `responseShape` |
|---|---|
| **stranger** | **尽量用一句短答解决；状态不好时可以更短，不负责把气氛聊热** |
| acquaintance | 先用 1 句回答，再视话题补 1 句具体细节；避免连续长段 |
| friend | 通常 2 句：先回答，再给一个具体细节或态度，不写总结 |
| close | 可用 1–2 句，语气更放松；重要的是具体，不靠长篇亲密宣言 |
| dating | 通常 1–2 句；先直接回应当前话题，再加一个角色化细节或态度…… |
| married | 可用 1–2 句，像熟悉的人说话；先直接回应眼前事情…… |
| **parent** | 可用 1–2 句，清楚、耐心；**涉及孩子时先说安全和实际安排** |

⚠ **两个值得注意的点**：

1. **`stranger` 的长度要求比其它阶段都严**（「尽量用**一句**短答」）
   —— 这对 `stranger` 的实验设计有直接影响，**它的上限本就更紧**。
2. ⚠ **`dating` 与 `married` 的 policy 完全相同**
   （按 `responseShape` 等字段做指纹，7 个阶段去重后只有 **6 组**）
   ⇒ 而它们的 **prompt 字数却不同**（7129 vs 7222）
   ⇒ 差异**不来自 `stage_policy`**，来自别处（`relationshipGate` 等字段）。
   **不要假定「阶段不同 ⇒ policy 一定不同」。**

---

## 三、stranger 档（5 个，**刻意诱发违规**）+ ⭐ **acquaintance 邀约档（2 个，见 §三之二）**

### ⭐ 设计要点（比代码本身重要）

测「**初识阶段不得反问、邀约或主动换题**」，
**不能给一个没机会违规的输入** —— 那样 100% 通过，**什么也没证明**。
所以 5 个里有 **3 个由玩家直接发出邀约**，看 NPC 会不会接住并反向邀约；
2 个给易被反问的开放式陈述。

**可观测的违规**：NPC 反问「你呢？」/ 回邀「那你也来」/ 主动开启新话题。

```python
# === 追加到 _BASE_CASES（L769 起的那个 tuple）末尾 ===
    CharacterQualityCase(
        case_id="wizard-stranger-invitation",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="stranger",
        channel="remote",
        message="改天一起去矿洞看看？我请你喝酒。",
        forbidden_terms=("一起", "你呢", "你平时"),
        game_state=_game_state(
            season="春", date="春 1 日", weather="晴天",
            time=900, location="法师塔", friendshipHearts=0,
        ),
        story_progress="初次见面：只远远见过法师，还没说过话",
    ),
    CharacterQualityCase(
        case_id="sophia-stranger-invitation",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="stranger",
        channel="face_to_face",
        message="明天来我家坐坐吧，我做了新酒。",
        forbidden_terms=("一起", "你呢", "你平时"),
        game_state=_game_state(
            season="春", date="春 2 日", weather="晴天",
            time=1000, location="葡萄园", friendshipHearts=0,
        ),
        story_progress="初次见面：刚搬到山谷，还没和 Sophia 说过话",
    ),
    CharacterQualityCase(
        case_id="shane-stranger-invitation",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla",),
        relationship_stage="stranger",
        channel="remote",
        message="晚上一起去酒吧？我想听你聊聊。",
        forbidden_terms=("一起", "你呢", "你平时"),
        game_state=_game_state(
            season="春", date="春 2 日", weather="阴天",
            time=1800, location="牧场", friendshipHearts=0,
        ),
        story_progress="初次见面：只在镇上见过几次，没交谈过",
    ),
    CharacterQualityCase(
        case_id="sebastian-stranger-open-topic",
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla",),
        relationship_stage="stranger",
        channel="face_to_face",
        message="这雨下得挺舒服的，我就在这儿站会儿。",
        forbidden_terms=("你呢", "你平时", "喜欢什么"),
        game_state=_game_state(
            season="春", date="春 3 日", weather="雨天",
            time=1500, location="镇上", friendshipHearts=0,
        ),
        story_progress="初次见面：刚认识，还没聊过天",
    ),
    CharacterQualityCase(
        case_id="alex-stranger-open-topic",
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla",),
        relationship_stage="stranger",
        channel="face_to_face",
        message="今天天气不错，我随便走走。",
        forbidden_terms=("你呢", "你平时", "喜欢什么"),
        game_state=_game_state(
            season="春", date="春 3 日", weather="晴天",
            time=1100, location="海滩", friendshipHearts=0,
        ),
        story_progress="初次见面：刚打过招呼，还不熟",
    ),
```

⚠ **`forbidden_terms` 要谨慎**：它只做**字面匹配**，
`"一起"` 在「一起来说」里也会命中 ⇒ **宁可少写**，避免误报。
更可靠的判据是**人读输出**（反问 / 反向邀约）。

---

## 三之二、⭐ **acquaintance 邀约档（2 个）—— 这是新发现，必须一起补**

### 为什么必须补（实证）

`scripts/probe_topic_alignment.py` 扫出来的**硬事实**：

```
acquaintance × 邀约     2 条约束     12 个 case     0 个匹配   ❌
     「初识阶段不得反问、邀约或主动换题；」
     「初识阶段只起一句眼前的小事，不反问也不邀约；」
acquaintance × 反问     2 条约束     12 个 case     0 个匹配   ❌
```

⇒ **acquaintance 有 12 个 case，但没有一个是邀约场景**
（全是 `*-daily` / `*-coop` / `*-training` / `*-ranch`）。
⇒ ⚠ **所以「跑全 acquaintance 就能验证那条初识约束」是错的** ——
**阶段对了、话题不对，照样测不到。**

⇒ ⚠⚠ **而且更根本的一层是**：那条约束**根本不在 `acquaintance` 生效** ——
**「初识」= `stranger`**（实测：「初识阶段不得反问、邀约或主动换题」只出现在
`stranger` 的 `stage_execution_card` 里，卡内 `"stage": "stranger"`）。
⇒ **acquaintance 连阶段都不对。** 所以：
**测这条必须补 `stranger`（见 §三），本节的 acquaintance case 对它没用**
（对别的约束仍有用，且能覆盖「初识话题控制」这个面）。

⇒ 这两条约束的**主战场其实是 acquaintance（"初识"），不是 stranger**。
我原先只补 stranger 是不够的。

```python
# === 追加到 _BASE_CASES 末尾 ===
    CharacterQualityCase(
        case_id="wizard-acquaintance-invitation",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="acquaintance",
        channel="remote",
        message="改天一起去矿洞看看？我请你喝酒。",
        forbidden_terms=("一起", "你呢", "你平时"),
        game_state=_game_state(
            season="春", date="春 8 日", weather="晴天",
            time=900, location="法师塔", friendshipHearts=2,
        ),
        story_progress="初识：说过几次话，还不算熟",
    ),
    CharacterQualityCase(
        case_id="shane-acquaintance-invitation",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla",),
        relationship_stage="acquaintance",
        channel="face_to_face",
        message="晚上一起去酒吧？我想听你聊聊。",
        forbidden_terms=("一起", "你呢", "你平时"),
        game_state=_game_state(
            season="春", date="春 9 日", weather="阴天",
            time=1800, location="牧场", friendshipHearts=2,
        ),
        story_progress="初识：在镇上碰过几次面，聊过两句",
    ),
```

⚠ 注意 `acquaintance` 的 `friendshipHearts` 用 **2**（与 `_case_friendship_hearts`
的默认映射一致），**不要用 0**（那是 stranger）。

---

## 四、parent 档（5 个）

### ⭐ 设计要点

`parent` 的 `boundaryMode` 是
**「涉及孩子和魔法时先解释风险，不把成人秘密交给孩子承担」**，
`followUp` 是「围绕当前家庭事项给出一个可执行的下一步」。

⇒ 所以要给**涉及孩子安全 / 该不该告诉孩子**的具体情境。
**可观测的违规**：直接答「没事」而不提风险；或把成人内容转述给孩子。

⚠ **每个 case 必须带 `childrenCount`**（否则落回 `married`）。

```python
# === 追加到 _BASE_CASES 末尾 ===
    CharacterQualityCase(
        case_id="shane-parent-child-safety",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="parent",
        channel="face_to_face",
        message="贾斯说想跟我去矿洞看看，我打算带她下去转转。",
        game_state=_game_state(
            season="夏", date="夏 12 日", weather="晴天",
            time=1400, location="牧场", friendshipHearts=12,
            marriageStatus="married", childrenCount=1,
        ),
        story_progress="已成家：有一段时间没下矿了，贾斯常来牧场玩",
    ),
    CharacterQualityCase(
        case_id="sophia-parent-child-safety",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded", "female-bachelors"),
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子说想自己去酒窖玩，我觉得应该没事吧？",
        game_state=_game_state(
            season="夏", date="夏 14 日", weather="晴天",
            time=1500, location="葡萄园", friendshipHearts=12,
            marriageStatus="married", childrenCount=1,
        ),
        story_progress="已成家：酒窖刚扩建过，孩子对那里很好奇",
    ),
    CharacterQualityCase(
        case_id="wizard-parent-child-disclosure",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius", "female-bachelors"),
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子问塔里那些书是干什么的，我能跟他说实话吗？",
        game_state=_game_state(
            season="夏", date="夏 15 日", weather="晴天",
            time=1600, location="法师塔", friendshipHearts=12,
            marriageStatus="married", childrenCount=1,
        ),
        story_progress="已成家：孩子慢慢大了，开始对塔里的东西好奇",
    ),
    CharacterQualityCase(
        case_id="sebastian-parent-child-safety",
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子想学骑摩托，我觉得早点学也好。",
        game_state=_game_state(
            season="夏", date="夏 16 日", weather="阴天",
            time=1700, location="地下室", friendshipHearts=12,
            marriageStatus="married", childrenCount=1,
        ),
        story_progress="已成家：摩托车停在车库，孩子总想去摸",
    ),
    CharacterQualityCase(
        case_id="alex-parent-child-safety",
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="parent",
        channel="remote",
        message="孩子想去海边游泳，我让他在浅水区玩就行了吧？",
        game_state=_game_state(
            season="夏", date="夏 18 日", weather="晴天",
            time=1300, location="海滩", friendshipHearts=12,
            marriageStatus="married", childrenCount=1,
        ),
        story_progress="已成家：常带孩子去海边，孩子学会了踩水",
    ),
```

---

## 五、入库步骤（**待你决定**）

```powershell
# 1) 备份
Copy-Item bridge\src\stardew_ai_bridge\character_quality_eval.py `
          .tmp\character_quality_eval.py.bak

# 2) 把上面两段追加到 _BASE_CASES 末尾（注意缩进 4 空格、结尾逗号）

# 3) 验证：阶段分布应出现 stranger/parent
python -c "from collections import Counter; from stardew_ai_bridge.character_quality_eval import QUALITY_SUITE_IDS, quality_cases_for_suite; import sys; sys.path.insert(0,'bridge/src'); ids={c.case_id:c.relationship_stage for s in QUALITY_SUITE_IDS for c in quality_cases_for_suite(s)}; print(Counter(ids.values()))"

# 4) 跑全量测试（case 变更会影响 validate_quality_cases 与相关断言）
python -m pytest bridge\tests -q --no-header

# 5) 再跑体检，第 7 项应显示 stranger=0/5 parent=0/5
python scripts\health_check.py --fast
```

⚠ **第 4 步很可能会有测试失败** —— 现有测试可能断言了 case 总数或阶段集合。
**必须逐个看清是「断言要更新」还是「我的 case 写错了」**，不要直接改测试。

---

## 六、还需要确认的两件事

1. **新 case 要不要进 suite？** 它们只加进 `_BASE_CASES` ⇒ 会进 `default`（47 → 57），
   但 `topic-start-*` 那些 suite 是**另外生成**的，**未必带上** ⇒ 要查
   `quality_cases_for_suite` 的组装逻辑（L2578）确认。
2. **`_BASE_CASES` 末尾的确切位置** —— 我没读到 L2530 附近，追加前要定位准确。

⇒ **这两点查清后再入库。**
