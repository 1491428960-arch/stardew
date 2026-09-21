# 一夜总览 · 对话内容工程（2026-09-21 夜 ~ 09-22 凌晨）

> 执行时间：2026-09-21 23:50 ~ 2026-09-22 02:20（本文件按约定命名 `2026-09-23`，实际收尾于 09-22 凌晨）
> 分支：`codex/story-memory`　｜　范围：`data/personas/*.json`、`bridge/src/stardew_ai_bridge/stage_policy.py`、`profile_index.py`
> 口径来源（用户原话）：**「主要是要自然一点，像真实对话，也要像这个人该说的话」**
> 全部 7 批**已提交**；本轮（收尾）**只读**，除本文件与 `docs/active-work.md` 外未改任何受版本控制文件。

---

## 1. 一句话结论

这一夜把"NPC 该说什么"从**判不出的词表**推进到**有原话依据的素材**：词表补到能判真实对白 →
素材从 **193 条涨到 279 条**、≥5 面角色从 **1 个涨到 41 个** → 揪出索引器漏掉 Birdie 全部台词的根因、**按 21 段真原话重写她的人设** →
再把此前为绕开词表而改写的字面**换回原话**。
收尾体检发现：**同一类"人设与原话对不上"的问题在另外 6 个角色上确凿存在，另有 147 条官方台词从未进索引** —— 本轮只报告，未改，等拍板。

---

## 2. 数据对照表

| 指标 | 这一夜起点（`fd87164^`） | 现在（本轮实测） | 依据 |
|---|---|---|---|
| 素材总条数 | **193** | **279**（**+86 条**） | 实测（`git show fd87164^` vs 工作树） |
| 有素材的角色 | 44 | **44 个 canonical 角色**（45 个 npcId 条目：`Rasmodia` 归一为 `Wizard`） | 实测 + `canonical_npc_id` |
| ≥5 面角色 | **1** | **41** | 实测；第 4 批报告当时记为 2 → 25（口径见下注） |
| ≥6 面角色 | **1** | **12** | 实测 |
| 面数分布 | 1 面×17 / 2 面×13 / 3 面×8 / 4 面×5 / 6 面×1 | 7 面×3 / 6 面×9 / 5 面×29 / 4 面×2 / 3 面×1 / 1 面×1 | 实测 |
| 判定词表 | 旧表 | 第 3 批 **+14 词**（工作、农夫、厨房、酒吧、冰淇淋、甜点、邻居、女儿、儿子、锻炼、花园、电视、动漫、记得）+ 4 处误抓修正；第 6 批 **+6 词** | `stage_policy.py` |
| 角色人设修正 | — | **Birdie 全字段重写**（coreTraits / addressing / tone / sentencePattern×3 / signatureMoves / avoid）、Shane 救赎线回归 | 第 6 批 |
| 素材字面 | 25 条为绕开词表改写过 | **还原 7 条 + 新增 1 条（Pam）**，保留改写 17 条 | 第 7 批报告 §0 |
| 索引器 | 缺 `Data/ExtraDialogue` 入口 | 加了 warning，**入口本身仍未补** | `data/generated/*.json` 的 `warnings` |
| 语料缺口 | — | **147 条官方台词从未进索引**（本轮新查清，见 §5.2） | 本轮 |

> **起点数字的两点说明**（避免误读）：
> ① 起点面数是用**当前词表**回测旧素材得到的；第 4 批报告当时记的是"≥5 面 2 个 → 25 个"，与本表的 1 个差 1，属判据口径差异（我当时不在场，无法还原当时的算法），**两个数字都列出来**，以工作树实测为准。
> ② 一夜新增 **86 条**素材，但第 7 批单独看是 278 → 279（只 +1）—— 因为第 7 批是**换字面**不是加条数；**278 是第 7 批前的值，不是这一夜的起点**。

---

## 3. 逐批做了什么

**第 3 批 · 词表扩容 + 两个样板**（`fd87164`）
判定词表加 14 个真实对白里在用的词（最刺眼的是「工作」「农夫」这种最普通写法反而判不出面），修掉 4 类跨词/跨面/习语误抓；把 Sophia、Elliott 补到 5 面当样板；把"禁令"改写成"范例"（告诉模型该怎么说，而不是不许说）。

**第 4 批 · 素材横向推广 27 角色**（`3aabb0d`）
按第 3 批确立的方法给 27 个角色各补素材，**≥5 面角色从 2 个涨到 25 个**；每条都记录出处原话与"摘取/改写"的判定。

**第 5 批 · 再推 16 角色 + Birdie 缺口查清**（`2e91c58`）
素材补全收尾到 44 角色；同时查清 Birdie 为什么一条语料都没有：她的台词在 `Data/ExtraDialogue.zh-CN.json`（15 条）+ `Strings/Locations` 事件脚本（14 句）里，而索引器三条入口都不扫这两个地方。

**第 6 批 · Birdie 人设按真原话重写 + Shane 救赎线**（`0213cc8`）
凭 21 段真原话逐字段重写 Birdie：`tone` 从"喜欢钓鱼"改成"每天在海滩上散步"、`addressing.player` 从「朋友」改成「**孩子**」（7 条原话）、删掉"不先寒暄/从不用『我』"（**她恰恰先问候、通篇用『我』**）；补 6 个词；给索引器加缺失来源 warning。

**第 7 批 · 把改写的字面换回原话**（`72d0ac2`）
25 条"为绕开词表而改写"的候选逐条回测：**还原 7 条**（面不变）、**新增 1 条**（Pam「要是自己有个什么爱好就好了」，第 5 批判"探不动"）、保留 17 条；全库 278 → 279 条，**0 条丢失识别、0 条主面漂移**。

**收尾（本轮）· 全局一致性体检 + 本文件**
按用户要求做"Birdie 那类问题还有没有别处"的全库体检，**只报告不改**。结果见 §5。

---

## 4. 怎么验证（可以直接照做）

### 4.1 离线可验证（不需要游戏、不需要云端）

```powershell
cd E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory
$py = "C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe"

# ① 素材总数 / 角色数 / 面数分布（应得 279 条 / 45 个 npcId 条目 = 44 个 canonical 角色 / ≥5 面 41 个）
& $py -B .tmp/facet-coverage/c1_audit.py

# ② 逐条素材的面归属与出处
& $py -B .tmp/facet-coverage/b7_inventory.py --write      # 产出 b7-inventory.tsv

# ③ 渲染回测：44 角色素材逐条可见、roleGuidance 不越 240 字
& $py -B .tmp/facet-coverage/b6_render.py                 # 产出 b6-render-all.txt

# ④ 一致性体检全套（本轮新增，只读）
& $py -B .tmp/facet-coverage/c3c_strict.py                # addressing 三层证据
& $py -B .tmp/facet-coverage/c9_material_risk.py          # 素材出处风险分级
& $py -B .tmp/facet-coverage/c1d_extra_gap.py             # ExtraDialogue 缺口

# ⑤ 回归测试（基数是昨夜的，不是本轮实测）
cd bridge; & $py -B -m pytest -q
```

**断言式验收（不跑脚本也能查）**：

- `data/personas/vanilla.json` 的 `Birdie.addressing.player` 必须是 `"孩子"`，且 `tone` 里**不能**出现"钓鱼"；
- 全库 `preferredTopics` 条数 = **279**；
- `stage_policy.py` 的面判定对「工作」「农夫」「邻居」「电视」必须命中（第 3 批新增词没被回退）。

### 4.2 只能真机看的（离线没有代理指标）

| 要验证什么 | 为什么离线测不出来 |
|---|---|
| NPC **实际说出来的话**是否自然、像本人 | 渲染回测只能证明"素材进了 prompt"，不能证明模型据此说了什么 |
| **低阶段**（陌生人/初识）是否出现"婚后语境"的素材 | 需要真机的好感度状态；离线只能标出处风险等级（§5.3） |
| Olivia / Willy / Sandy / Morris / Lance / George **改称呼后**的实际观感 | 得看真实对话，且**改动本身还没做** |
| Birdie 在姜岛遇到时的**开场问候** | 她的台词要走 `Data/ExtraDialogue` 运行时路径 |
| ExtraDialogue 的 147 条**补进索引后**对 Morris/Robin/Gunther 的影响 | 需要重建索引 + 真机跑，索引器入口**尚未修** |

---

## 5. ⚠ 还剩什么（未做的 / 要拍板的 / 可疑的）

### 5.0 一句话

**本轮一件代码都没改。** 下面全部是查出的事实，等用户拍板。

### 5.1 🔴 addressing.player 系统性对不上（最值得拍板的一件）

**根因**：`9388765`（2026-09-20 05:51「data: 更新 persona 声明并新增 friendship-roster」）**一次性给 30+ 角色批量写入** `addressing.player`，大多数填模板值「朋友」，SVE 的 5 个填「农场主」，**没有逐角色核对原话**。第 6 批修 Birdie 时确立了新口径（按真原话），**其余 49 个条目没有跟进**。

**实测**：50 个 persona 条目里，只有 **5 个**在"对玩家的日常对白"里有直接呼语实证（Andy、Birdie、Dwarf、Evelyn、Pam）。

**高严重度 6 条**（人设写的与原话明确冲突，且原话有清晰替代）：

| 角色 | 人设写 | 原话实际 | 证据 |
|---|---|---|---|
| **Olivia** | 农场主 | **亲爱的** | `Olivia/Dialogue.json/Introduction`「亲爱的，欢迎来到星露谷」；非婚后主对白 13 处、全库 40 处 |
| **Willy** | 朋友 | **小伙子／小姑娘／小姐**（按玩家性别） | `Willy.zh-CN.json/Mon`「你好啊，小姑娘」；事件里"小伙子" 11 处 |
| **Sandy** | 亲爱的 | **甜心** | `Sandy.zh-CN.json/Mon`「哈喽，甜心！」 |
| **Morris** | 农场主 | **先生／女士／小姐**（按性别） | `Morris.json/6663501`「你好，女士！」；`ExtraDialogue/Morris_CommunityDevelopmentForm_PlayerMale`「先生，我为您拿到了…」 |
| **Lance** | 农场主 | 亲爱的（日常） | `Lance/Dialogue.json/Wed10`「你好，亲爱的。你今天有探险家公会的事要处理吧？」 |
| **George** | 朋友 | 小伙子／小姐（按性别） | `George.zh-CN.json/Thu`「我现在没空聊天，小伙子」／「小姐」 |

**中严重度**：
- `addressing.player = "农场主"` 但日常对白无据：**Claire、Victor**
- `addressing.player = "亲爱的"` 但日常对白无据：**Caroline、Marnie**
- `addressing.player = "朋友"` 但日常对白无据（**批量模板值**）：Abigail、Clint、Demetrius、Emily、Gunther、Gus、Jodi、Kent、Krobus、Leah、Leo、Lewis、Linus、Marlon、Maru、Penny、Pierre、Robin
- **英文残留**（9 个条目）：Alex×2、Elliott、Harvey、Sam、Sebastian×2、Shane×2 写的是 `"you"`；Wizard 写 `"traveler"`
- **字段缺失** 2 处：**Sophia**（`sve.json`，她的唯一来源，vanilla 没有她 → 运行时这个字段是空的）、Wizard（`sve.json`，overlay 预期，会继承 vanilla 的 `"traveler"`）

**建议改法（待拍板）**：以第 6 批 Birdie 的口径为准 —— **这个字段写"对玩家日常对白里真实出现的称呼方式"**，而不是关系定位。
具体：6 条高严重度按上表替换；批量「朋友」按角色实际改成「用『你』／直呼名字」或原话里真实存在的称呼；英文 `"you"` 统一改成「你」；补 Sophia 的字段。

**⚠ 这条要用户先定口径再动**：如果「朋友」是刻意表达的"关系定位"（而非称呼词），那 18 条都不算错，只是字段语义需要改名。**两种读法我都摆在这里，不替用户决定。**

### 5.2 🔴 `Data/ExtraDialogue` 的 147 条官方台词从未进索引

**这修正了第 5/6 批的结论。** 第 5 批的对照回答的是"哪个 NPC 被**完全**漏掉"（答案：只有 Birdie），但没回答"漏了多少台词"。

本轮实测：`Data/ExtraDialogue.zh-CN.json` 的 **147 条，没有一条进索引**（逐条文本比对索引 `styleSamples`，命中 0）。

| 类型 | 条数 | 说明 |
|---|---|---|
| 角色专属台词 | **Birdie 15、Morris 18、ProfessorSnail 8、Robin 7、Gunther 3、Clint 2、Sandy 1、Wizard 1、MisterQi 1** | key 前缀即角色名 |
| 场景键（内含角色台词） | PurchasedItem 34、SummitEvent 31、Mines 7、NewChild 4、Farm 3（Robin）、Town 3、SkullCavern 2（MrQi）、Island 2（Willy/Leo）、Spouse 1、LostItemQuest 1、JoshHouse 1、SamHouse 1、SeedShop 1 | 前缀不是角色名，但内容是角色在说话 |

**实际影响（值得单独看）**：
- **Morris 缺 18 条核心对白**：Joja 会员推销、社区发展申请书、电影院收购 —— 全是他这个角色的"主业台词"。**他的 `addressing.player` 写错成「农场主」，很可能就是缺这 18 条的直接后果**（那 18 条里明确写着"先生／小姐"）。
- **Robin 缺 7 条**：房屋升级、建筑施工 —— 她作为木匠的主业对白。
- **Gunther 缺 3 条**：博物馆收藏、捐物 —— 他作为馆长的主业对白。
- `SummitEvent` 的 31 条是大结局山顶台词，含 Lewis、Morris 等人的长段自述。

**建议改法（待拍板）**：给索引器补 `Data/ExtraDialogue` 入口（第 6 批只加了 warning）。**注意**：补入口会**改变现有角色的语料池**，可能让已落地的素材出现新的最佳匹配 —— 建议补完后重跑第 7 批那套"字面 vs 原话"回测。

### 5.3 🟠 素材出处风险（字面只能在婚后／高好感来源里找到）

判据：素材字面与某条原话的最长公共子串占比 ≥ 0.6（= 摘取），**且所有**达到该重合度的原话都来自 `MarriageDialogue*` 或高好感事件。

**HIGH 13 条**（低阶段说出来可能违和）：

| 角色 | # | 素材 | 出处 |
|---|---|---|---|
| Olivia | 3 | 冬天把你的脸颊冻得红扑扑的 | MarriageDialogue（重合 1.00） |
| Sophia | 5 | 窝在毯子里看电视 | MarriageDialogue（1.00） |
| Alex | 3 | 夏天是一年里最有活力的季节 | MarriageDialogue（1.00） |
| Maru | 3 | 想吃巧克力蛋糕还是熟草莓 | MarriageDialogue（1.00） |
| Maru | 4 | 雨天看不到星星 | MarriageDialogue（0.71） |
| Maru | 5 | 阅读最新一期的每周图表 | MarriageDialogue（0.64） |
| Penny | 3 | 我给你做了热腾腾的早餐 | MarriageDialogue（1.00） |
| Penny | 4 | 春天大概是我最喜欢的季节 | MarriageDialogue（1.00） |
| Penny | 5 | 我过去经常做最恐怖的噩梦 | MarriageDialogue（1.00） |
| Emily | 3 | 用仙人掌糖浆做的甜点 | MarriageDialogue（0.60） |
| Victor | 2 | 秋天里略带寒意的风 | MarriageDialogue（0.67） |
| Leo | 2 | 还留在岛上的家人 | 高好感事件 2250 点（0.75） |
| ~~Haley~~ | ~~0~~ | ~~摄影~~ | **假阳性已剔除**：2 字短词，日常对白里她同样说摄影 |

**MID 11 条**：Harvey#4、Andy#5、Morris#3/#4/#5、Abigail#5、Dwarf#4、Pierre#5、Vincent#4、Willy#3/#4/#5（事件台词 / 中好感事件 / 未标条件）。

**建议改法（待拍板）**：三种都可选 —— ① 保留（内容本身不涉关系，只是字面来源在婚后）；② 低阶段降权，高阶段才发；③ 换成同角色的日常对白素材。**我建议 ②**，因为 ③ 会牺牲已有的面覆盖。

### 5.4 🟡 Sophia 的「绘画」—— Birdie 同型，找到 1 例

`sve.json` 的 Sophia：
- `signatureMoves[0]`：「谈到酿造、**绘画**或刚发现的小事时…」
- `preferredTopics[1]`：「**画布上还没画完的那一块**」

她的 **265 条语料里含"画"的只有 2 条**：「画了眼线」（化妆）、「你看动画吗」（动漫）—— **没有任何绘画内容**。
该素材来自 2026-09-21 的 `b104833`（强制区分度四批落地 · 专有名词常驻），字面重合度仅 0.18（改写），**无原话支撑**。
**建议**：按 Birdie 的做法，改成她语料里真实存在的东西（葡萄酒酿造、看动画、小镇见闻）。

### 5.5 🟡「不先问候」型否定断言：7 条，5 条成立、2 条偏强

`signatureMoves` 里有 7 条明确的"不先问候／不寒暄"断言：Clint、Lewis、Marlon、Marnie、Maru、Shane、Vincent。
实测这些角色对玩家台词的**问候开场比例**：Clint 7%、Lewis 0%、Maru 9%、Shane 4% → **断言成立**；**Marnie 20%、Vincent 21%** → 可能抹掉约 1/5 的自然开场。

**与 Birdie 的区别（重要）**：Birdie 是**完全反了**（她的标志性特征就是开口先问候 + 喊"孩子"）；这 7 条方向是对的，属于**反机械感的设计选择**，不是事实错误。**风险低，可以不动**。

### 5.6 🟢 已排除的怀疑（查过、没问题）

- **事件台词的角色归属是正确的**。我最初怀疑索引器"按参与者顺序轮转分配说话人"，用 `Data/Events/Town.zh-CN.json/831125` 逐行对照原文脚本的 `speak <NPC>` 指令 —— **22 行全部一致，证伪**。
  （副作用提醒：索引包含角色在事件里**对别人**说的话（如 Clint 在广告里对 Emily 说"亲爱的"），做称呼统计时会假阳性。这是方法学提醒，不是数据缺陷。）
- **Birdie 的 `sourceRefs` 是干净的**：`Data/ExtraDialogue/Birdie`（对应 15 个键）、`Strings/Locations.zh-CN.json` 里的 `IslandSecret_Event_BirdieIntro`、`Data/Quests.zh-CN.json` 里的 `130` —— **三条全部可解析**。
- **活动词同义复核**：Caroline「园艺」（原话"照料公共花园"、"种"×10）、Evelyn「烘焙」（"烤我的招牌饼干"）、Jodi「做饭」（"共进晚餐…炖砂锅"）、Vincent「昆虫」（"捉虫子"）、Maru「机械」（"新发明'玛丽尔达'"）、Dwarf/Marlon「矿洞」（原话用"矿井"）→ **全部成立**。
- **Harvey 的「花」是假阳性**：人设里没有"花"，是 `signatureMoves` 里的"眼睛有点**花**"。**不改**。

### 5.7 本轮明确**没做**的

- ❌ 没改任何 `data/personas/*.json`（除这两个文档外，本轮零改动）
- ❌ 没修索引器入口（只用了既有的 warning 做核对）
- ❌ 没跑云端、没启动游戏、没部署、没 `git commit` / `git add`
- ❌ 没跑 Bridge 全量回归（只做了只读脚本核对；**测试基线是昨夜的 3192 passed，不是本轮实测**）
- ❌ 没验证"改完之后 NPC 实际说得更好"—— 离线没有这个代理指标

### 5.8 不确定的地方（如实说）

1. **「朋友」到底是称呼词还是关系定位** —— 这决定 5.1 里 18 条算不算错。我**没有**找到代码或文档里的定义；只看到 `personas.py` 的兜底文案写"沿用原版或资料中已确认的**称谓**"，倾向"称呼词"读法，但这是推断。
2. **`addressing` 在 prompt 里的实际渲染** —— 我读代码确认 `_compact_identity`（`prompts.py:4430`）会把 `addressing` 原样放进身份 JSON，所以我判断模型会据此称呼玩家；但**没有做端到端实验**证明模型真的被带偏。
3. **Sophia 是否有绘画设定的其他出处** —— 我查的是索引语料（含 SVE 全部来源），未查 SVE 的贴图/家具/邮件等非对白资源。**结论限于"她的对白里没有绘画"**。
4. **高危素材在低阶段的实际违和度** —— 我只能标出处，**没测过**低阶段生成的实感。
5. `rasmodia.json` 的 `vanilla:Wizard:Tower` 格式无法机械校验，**不知道**设计意图是什么。

---

## 6. 复现产物（全部在 `.tmp/facet-coverage/`，该目录 gitignore）

| 脚本 | 产物 | 作用 |
|---|---|---|
| `c1_audit.py` | `c1-coverage.tsv`、`c1-sourcerefs.tsv`、`c1-claims.txt` | 覆盖统计 + sourceRefs + 全部可验证断言清单 |
| `c3c_strict.py` | `c3c-addressing-strict.tsv` | addressing 三层证据（主对白非婚后 / 婚后 / 事件内） |
| `c9_material_risk.py` | `c9-material-risk.tsv` / `-all.tsv` | 素材出处风险分级（全量 279 条） |
| `c1c_sources.py` / `c1d_extra_gap.py` / `c1e_extra_dump.py` | `c1e-extradialogue-all.txt` | `Data/ExtraDialogue` 147 条缺口核查与明细 |
| `c2_calls.py` / `c3b_vocative_split.py` / `c7_greeting.py` | `c2-out-*.txt`、`c3b-out.txt` | 称呼词实证与问候开场比例 |
| `c5_attribution.py` / `c5b_event_speaker.py` | 控制台输出 | 事件台词归属核对（证伪） |
| `c6_claims.py` / `c8_refs_synonyms.py` | `c6-out.txt` | 活动词断言与同义复核 |

> 环境提示：本 worktree 里 `python` 不在 PATH，脚本用
> `C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe`（3.10.8）运行。

---

## 7. 下一步建议（按优先级）

1. **拍板 addressing 字段的口径**（§5.1）—— 这是唯一"一行数据影响 30+ 角色"的事，且改动小、收益大。
2. **修索引器的 `Data/ExtraDialogue` 入口**（§5.2）—— 影响 Morris／Robin／Gunther 的取材质量；修完重跑第 7 批回测。
3. **Sophia 的「绘画」换成有原话支撑的落点**（§5.4）—— 单点小改。
4. **给 HIGH 13 条素材加阶段门槛**（§5.3）—— 需要先决定是否接受"低阶段也能聊婚后话题"。
5. 真机跑一轮，重点看 Olivia／Willy／Sandy 的称呼和低阶段的素材体感。
