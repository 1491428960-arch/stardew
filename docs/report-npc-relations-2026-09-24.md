# NPC↔NPC 关系层（2026-09-24）

> 起因是一句玩家反馈：「角色之间的关系还是没到位，格斯和索菲亚应该挺熟的」。
> **用户是对的**，而且比「没到位」更具体 —— 关系事实一直躺在游戏文件里，
> 只是从来没有到过模型的眼前。
>
> 相关：`docs/active-work.md` 的 ㉙（关系层本体）与 ㉚（铺到所有主要角色）。

## 一、查证：不是模型不会演关系，是它没数据

动手之前先查证，因为「角色关系不像」有两种完全不同的成因：模型不肯演，或者模型没料。

索菲亚是 SVE 角色，她的事件对白在 `[CP] Stardew Valley Expanded/i18n/zh.json` 里。
翻出来是这样的：

| 场景 | 原文 |
|---|---|
| 4 心事件（**Gus 说**） | `"Of course, Sophia! Anything for a close family friend!"`<br>中文 i18n：「当然，索菲娅！我很乐意为一位**亲密的家庭朋友**做任何事！」 |
| 8 心事件（**Gus 说**） | 「**我知道你来这里是为了什么！** 格兰普顿香橙鸡马上就到！」 |
| 7 心事件（**索菲亚说**） | 「那天晚上，前门有人敲门……**刘易斯镇长和格斯眼中充满了泪水**看着我……」 |
| 日常对白（**索菲亚说**） | 「**格斯从我很小的时候起就是我家人的朋友。** 我喜欢他来看望我。」 |

熟到不用点单，Gus 还说这顿算他的（`.08`「*低声耳语* 食物免费，@。」）。

**而她在游戏里说的是**：

> 格斯做的菜总是很有味道……我可以去问问他，**就是、就是有点怕打扰到他**，如果你真的想让我学，那我就去！

**方向完全相反。**

根因在她的人设素材里：「格斯」出现 5 次，**全是「格斯做的菜」「格斯做菜时那股香味」** ——
只够她夸菜，不够她知道「我们很熟」。模型在信息缺口处自己填了空，填成了陌生人。

⇒ **所以要做的不是加规则让她显得热情，而是把事实给她。**

## 二、数据源

### 2.1 vanilla：`FriendsAndFamily` 是权威的

`Content (unpacked)/Data/Characters.json` 每个角色都有一个 `FriendsAndFamily` 字段：

```json
"Gus": { "FriendsAndFamily": { "Emily": "[LocalizedText Strings\\Characters:Relative_...]" } }
```

- **27/48 个角色有边，合计 56 条**
- value 是**本地化引用**，配 `Strings/Characters.zh-CN.json` 的 22 个 `Relative_*` 条目，
  能精确到中文的「外甥／侄女／丈夫／女儿」这种词
- **空串 ≠ 没数据**：这个字段的语义是「朋友和家人」，空串表示「亲近但不是亲属」
  ⇒ 映射成「熟人」（Gus 的 Emily/Pam、Sam↔Sebastian、Clint→Emily 都是这一类）

**⚠️ 原版的关系是单向声明的。** `Abigail → Caroline = Relative_Mom` 有，
`Caroline → Abigail` 却是空串 —— 直接按空串判「非亲属」会得到错误的「熟人」。
所以加了反向推导 `fill_reciprocal_relations`：只填那些**正好等于「熟人」**的边，
反向词按**正向主体的性别**取，**绝不覆盖**原版已写明的措辞
（`Pam → Penny` 的「小女婴」原样保留）。

### 2.2 SVE：全部留空，只能策展

**SVE 把它所有角色的 `FriendsAndFamily` 都留空了** —— 实测 284 个 JSON 里
`Data/Characters` 的 EditData 全是 `{}`。所以 SVE 角色的关系**没有自动来源**，
只能从事件对白里挖。

这就是 ㉙ 只做透了索菲亚时留下的缺口：**另外 7 个 SVE persona 在关系表里一个字都没有**，
而这个缺口**在数据层完全看不出来** —— 表照样生成、测试照样过、prompt 照样注入，
只是那些角色聊起熟人时会照样把对方当陌生人。

## 三、关系事实的格式

```json
{
  "npc": "Gus",
  "term": "家人的朋友",
  "note": "格斯从我很小的时候起就是我家人的朋友……去酒馆我从来不用点单，他知道我要格兰普顿香橙鸡，还总说这顿算他的。",
  "evidence": "Sophia.CharacterDialogue.107 / Sophia.4hearts.HowAreYou.07 / Sophia.8hearts.14"
}
```

- `term` 是**称谓**（短，会进 prompt 的关系卡）
- `note` 是**第一人称的关系知识** —— 它是这个角色自己的认知，会被注入她的 prompt
- `evidence` 是**游戏原文的 key**，不进 prompt，只用于复核

**`evidence` 不是装饰。** 这份数据的全部价值在于它**有原文可依** ——
一旦允许「凭常识补」，它就从「事实」退化成「另一个会编的来源」。

## 四、挖掘工具与两个读法陷阱

新增 `scripts/mine_npc_relations.py`：按「事件归属前缀 × 关系词 × 角色名」交叉命中候选句。

**它只找候选，不下结论。** 关系事实必须人工按原句判定：
「我明天要去见维克多」不是关系，「维克多对我来说一直是位好朋友」才是。

角色中文名有两条来源：SVE i18n 的 `Name.*`（14 个）与 vanilla 的
`Strings/NPCNames.zh-CN.json`（49 个）。**注意 `Data/Characters.json` 的 `DisplayName`
指向的是 `Strings\NPCNames` 而不是 `Strings\Characters`** —— 指错了会一个名字都读不到。

### 陷阱一：key 前缀是「事件归属」，不是说话人

`Sophia.4hearts.HowAreYou.07` 里那句 `"Anything for a close family friend!"`
是 **Gus** 说的。所以工具的输出只能说「在这些 key 下命中」，
**不能断言谁在说** —— 断言了就会把 Gus 的关系记到索菲亚头上。

### 陷阱二：`Apples` 是祝尼魔

它的 135 条对白里「朋友」出现无数次，**全是指玩家**（「苹果朋友来看苹果！」）。
是纯噪音，已排除。

## 五、挖到的关键事实

每条都带 key，可复核：

| 角色 | 事实 | 证据 |
|---|---|---|
| Olivia ↔ Victor | **母子**（双向印证） | `Olivia.CharacterDialogue.001`「你见过我**儿子**维克多了吗？」+ `Victor.divorcedOlivia`「我**妈妈**对离婚的事情还无法完全接受」 |
| Olivia | 卡洛琳和乔迪是**最好的朋友**，「我们三个都是母亲」 | `Olivia.CharacterDialogue.125` / `.050` |
| Olivia | **「我尽量离潘姆远一点，她就是不喜欢我」** | `Olivia.CharacterDialogue.050` |
| Scarlett ↔ Sophia | **最好的朋友，同时是老板** | `Sophia.CharacterDialogue.172`「我**最好的朋友**斯嘉丽」+ `Scarlett.funReturn.Fall.3`「**当你和你的老板是朋友时**，这确实挺难的」 |
| Martin → Claire | 最好的朋友 + 同事 + **暗恋** | `Martin.marriedClaire`「**她是我最好的朋友**」+ `Martin.8hearts.16`「我**不只是把你当朋友**……喜欢」 |
| Claire | 同事马丁 / 同事潘姆 | `Claire.funReturn.Fall_7` / `Claire.funReturn.Fall_4` |
| Morris | **「除了安迪之外**，这个镇上没人接近我心目中的「朋友」二字」 | `Morris.2hearts.14` |
| Morris | 谢恩是**最信任的员工** | `Morris.marriedShane` |
| Lance | 认识法师，「**我们一起进行过几次探险**」 | `Lance.Nightmarket.001` |
| Marlon | **「吉尔和我认识很长时间了**……好兄弟千金不换」 | `Marlon.CharacterDialogue.073` |
| Morgan | **法师的学徒**（「是魔法部的命令」） | `Morgan.CharacterDialogue.001` + `Morgan.Apprentice.Married.02`（法师自述「我**以前从未有过学生**」） |
| Andy | 皮埃尔「**只跟他「亲密」的朋友分享**」——托一年的福他终于尝到了 | `Andy.CharacterDialogue.072` |

**Wizard 是 0 条。** 他一贯神秘、台词里不提任何人 —— **这本身是结论**，不是漏挖。

**「负面关系也是关系」**：Olivia 与潘姆合不来，同样是应当被 NPC 知道的事实。

## 六、接入 Bridge 与三个静默闸门级别的坑

关系要进入模型眼前，得过**两道白名单加一次压缩**，每一道都能让它静默消失：

1. **`_IDENTITY_FIELDS`**（`prompts.py:38`）—— `identity` 字典的字段白名单
2. **`persona_fields`**（`prompts.py:6269`）—— `persona_core` 卡消费的字段列表
3. **`_compact_npc_relations`** —— 逐条裁剪

**⚠️ 三个坑（都在 ㉙ 踩过）**：

- **关系表不能放进 `data/personas/`** —— `PersonaStore._load()` 把该目录下每个 JSON
  的顶层键当作条目表，`relations` 会变成一个叫 "relations" 的垃圾 NPC。
  最终放在 `data/` 下。
- **关系挂在 `get_persona` 而不是 `_load`** —— 否则要先过 `merge_persona`，
  一旦它只挑固定字段就会被静默丢掉。
- **`persona_fields` 里必须放「基础列表」而非 `stagePolicy` 那个 `not compact` 分支** ——
  **游戏走的正是 `compact=True` + `_runtime_compact` 那条路**，放分支里等于没做。

**本次（㉚）新增的一条**：`_compact_npc_relations` 的 `limit` **6 → 8**。
索菲亚按原句挖出来就有 7 条（格斯／斯嘉丽／维克多／艾米丽／海莉／苏珊／刘易斯），
6 会**静静砍掉最后一条** —— 正是这个项目反复栽的「数据有、没发出去」。

## 七、覆盖面

| | ㉙ 完成时 | ㉚ 完成时 |
|---|---|---|
| 角色数 | 28 | **39** |
| 边数 | 56 | **84** |
| 策展条数 | 5（只有索菲亚） | **33**（12 个角色） |
| SVE persona 覆盖 | 1/8 | **8/8** |

12 个有策展数据的角色：Sophia(7)、Olivia(5)、Scarlett(3)、Martin(3)、Morgan(3)、
Victor(2)、Lance(2)、Claire(2)、Morris(2)、Wizard(2)、Andy(1)、Marlon(1)。

## 八、验证

**测试 +2**（`bridge/tests/test_npc_relations_prompt.py`）：

- `test_every_sve_persona_has_relations` —— 8 个 persona 逐个必须有数据，
  **防「退回只有索菲亚」**
- `test_olivia_and_victor_know_each_other_both_ways` —— 母子关系两个方向都要到 prompt，
  单向的数据会让一方把另一方当陌生人

**全量**：`scripts/verify_project.ps1` 四项全 PASS —— SMAPI **1025 passed**、
Bridge **3959 passed**（+2）、`compileall` exit=0、`git diff --check` 无空白错误。

**线上逐角色验证**（走 Bridge 内部的 `_build_context`，确认 `_runtime_compact=True`）：

```
OK   Sophia   compact=True  命中 家人的朋友 斯嘉丽 海莉
OK   Olivia   compact=True  命中 儿子 卡洛琳 潘姆
OK   Victor   compact=True  命中 妈妈 索菲娅
OK   Morris   compact=True  命中 安迪 谢恩
OK   Claire   compact=True  命中 马丁 潘姆
OK   Scarlett compact=True  命中 最好的朋友兼老板
OK   Morgan   compact=True  命中 马格努斯 贾斯
OK   Marlon   compact=True  命中 吉尔
OK   Lance    compact=True  命中 图腾 马龙
OK   Andy     compact=True  命中 皮埃尔
OK   Wizard   compact=True  命中 学徒
OK   Linus    compact=True  命中 （无关系，正确地什么都没多出来）
```

**提交**：`f6ca6a7`（关系层本体）、`9c795de`（铺到所有主要角色）。
Bridge 已重载（PID 38084）。

## 九、方法论

**第 27 条（本轮最重要）：当一个缺口在数据层看不出来时，它一定在测试层也看不出来 ——
缺口要么写成断言，要么它就不存在。**

「只有索菲亚有关系」这件事，在整个工程里没有任何一个信号：表生成成功、
测试全绿、prompt 注入正常、端到端验证通过 —— 因为那些检查问的都是
「关系有没有到 prompt」，而不是「该有的关系是不是都有了」。
**覆盖类的缺口只能用覆盖类的断言来钉。**

**第 28 条：挖掘工具只找候选，结论必须人工按原句判定。**
把判定也交给脚本，得到的就是一堆似是而非的边 —— 而这份数据的价值恰恰在于它有原文可依。

**第 29 条：key 的结构含义要先确认再依赖。**
`Sophia.4hearts.*` 看起来像「索菲亚在说」，实际是「这个事件归属索菲亚」，
说话人可能是 Gus。按错误的理解去挖，会把关系记到错误的人头上，而且**看起来很合理**。

## 十、未做

- **关系层的实机复验未做** —— 线上逐角色验证走的是 Bridge 内部路径，
  还没有一次「玩家在游戏里和 Olivia 聊起维克多」的真实体验确认。
- **SVE 之外的大型 mod 未覆盖** —— 目前只有 vanilla + SVE + Rasmodia。
  任何新 mod 的 NPC 如果也留空了 `FriendsAndFamily`，都需要同样的策展。
- **关系是静态的** —— 不带「关系随时间变化」的语义（比如心数到了关系会不会变）。
  目前按「不随阶段变化的事实」处理。
