# 好感度系统 NPC · 气泡元素分配（2026-09-19）

> **先期准备产物。** 气泡元素的适用范围 = **能进入聊天与群聊的 NPC**，
> 也就是存档 `player.friendshipData` 里有记录的角色（`GroupInvitationGenerator` 与
> `GroupParticipantMenu` 都按 `HasFriendshipRecord` 过滤候选人）。
> 本文是该范围的完整元素表；上一版按索引全量铺开的 135 角色表已作废。

---

## 1. 范围

| | 数量 |
|---|---|
| 存档 `friendshipData` 条目 | **47** |
| 归并后独立角色 | **46** |
| 其中索引里有资料的 | 45 |
| 索引里有、但不在好感度系统的 | **90（本次全部排除）** |

名单固化在 `data/friendship-roster.json`（由存档导出，含别名与归并组）。

来源：正式存档 `Wofs_412086775`。测试存档 `test_447101921` 只有 Lewis、Robin 两条，
不具代表性。

---

## 2. 为什么不是 135

`/api/npcs` 返回 135 个"可聊天角色"，那是**索引全量**，包含三个内容 mod 叠加出来的
所有人（SVE 87 个、Rasmodia 77 个、原版 46 个）。但其中 90 个不在好感度系统里——
它们没有好感度记录，进不了聊天与群聊，做了气泡也永远不会显示。

按对白证据量看也很清楚：135 里有 28 个只有 2–4 条台词（`Alecto` 全部台词是
"等等，几点了？"），另有 16 个精灵图变体与 7 个占位。收窄到好感度系统后，
这 46 个每个都有实质戏份。

---

## 3. 不重复记录同一角色

两类重复，都只写一份元素：

**别名**（SVE 与原版命名指向同一角色，存档里只出现其中一个）：

| 存档 ID | 归一为 |
|---|---|
| `GuntherSilvian` | Gunther |
| `MarlonFay` | Marlon |
| `MorrisTod` | Morris |
| `MermaidLantana` | Mermaid |

**归并组**（同一角色的多个 ID 同时出现在存档里）：

| 成员 | 说明 |
|---|---|
| `Henchman` / `SVE_Henchman` | 同一个随从，共用一套元素 |

男版与娘化版**本来就不重复**：`female-bachelors` 是启用状态，它覆盖的是同一个 npcId
（`Elliott` 显示名为埃琳娜、`Harvey` 为哈丽特、`Alex` 爱丽克斯、`Shane` 珊恩、
`Sebastian` 塞布瑞娜、`Sam` 萨姆），存档里各只有一条记录。
气泡元素用道具表示角色、不涉及性别，因此男女版共用同一套元素，无需特殊处理。

---

## 4. 元素表（46 个角色）

★ = 该条同时覆盖多个名单 ID

| 角色 | 名单 ID | 色相 | 底色 | 材质 | 标志物 | 气质 |
|---|---|---|---|---|---|---|
| Alex | Alex | 5° | L24 | 月桂枝 | 橄榄球 / 哑铃 | 直球 · 行动派 |
| Claire | Claire | 12° | L33 | 作物茎 | 咖啡杯 / 信件 | 疲惫 · 打工 |
| Clint | Clint | 18° | L21 | 金属锭 | 铁砧 / 矿镐 | 沉默 · 锻造 |
| Robin | Robin | 25° | L25 | 木栏 | 锯子 / 锤子 | 爽利 · 木工 |
| Elliott | Elliott | 32° | L30 | 纸卷 | 羽毛笔 / 手稿 | 铺陈 · 诗意 |
| Pam | Pam | 38° | L21 | 线缆 | 巴士 / 啤酒杯 | 豪爽 · 直来直去 |
| Andy | Andy | 44° | L33 | 作物茎 | 南瓜 / 锄头 | 固执 · 务农 |
| Dwarf | Dwarf | 51° | L21 | 碎石 | 原石 / 矿镐 | 直率 · 交易 |
| Gus | Gus | 57° | L33 | 作物茎 | 平底锅 / 啤酒杯 | 热络 · 掌勺 |
| Marnie | Marnie | 63° | L21 | 毛线 | 牛奶罐 / 小鸡 | 热心 · 牧养 |
| Haley | Haley | 70° | L33 | 缎带 | 相机 / 向日葵 | 明艳 · 爱美 |
| Gunther ★ | GuntherSilvian | 76° | L21 | 书脊 | 化石 / 卷轴 | 博学 · 收藏 |
| Sandy | Sandy | 82° | L33 | 花枝 | 仙人掌 / 椰子 | 慵懒 · 沙漠 |
| Martin | Martin | 88° | L21 | 纸卷 | 工牌 / 信件 | 青涩 · 打工 |
| Susan | Susan | 95° | L33 | 作物茎 | 蜂蜜 / 菜篮 | 干练 · 经营 |
| Caroline | Caroline | 101° | L21 | 花枝 | 茶壶 / 向日葵 | 温和 · 园艺 |
| Pierre | Pierre | 107° | L33 | 作物茎 | 菜篮 / 种子袋 | 精明 · 营生 |
| Leah | Leah | 114° | L21 | 阔叶枝 | 刻刀 / 画架 | 自在 · 雕刻 |
| Linus | Linus | 120° | L33 | 阔叶枝 | 帐篷 / 野莓 | 淡泊 · 野外 |
| Harvey | Harvey | 126° | L29 | 藤蔓 | 医疗十字 / 咖啡杯 | 稳重 · 照料 |
| George | George | 137° | L21 | 木栏 | 电视机 / 勋章 | 固执 · 老兵 |
| Marlon ★ | MarlonFay | 148° | L25 | 金属锭 | 短剑 / 地图 | 硬派 · 探险 |
| Kent | Kent | 159° | L29 | 木栏 | 勋章 / 爆米花 | 沉重 · 军旅 |
| Emily | Emily | 170° | L24 | 缎带 | 宝石 / 彩色线轴 | 温柔 · 灵感 |
| Mermaid ★ | MermaidLantana | 178° | L33 | 渔网 | 珍珠 / 海螺 | 悠远 · 海 |
| Willy | Willy | 185° | L21 | 渔网 | 钓竿 / 鱼 | 老练 · 钓鱼 |
| Demetrius | Demetrius | 192° | L25 | 书脊 | 显微镜 / 齿轮 | 严谨 · 研究 |
| Shane | Shane | 200° | L30 | 麦秆 | 小鸡 / 咖啡杯 | 疲惫 · 嘴硬 |
| Morris ★ | MorrisTod | 206° | L21 | 纸卷 | 领带 / 工牌 | 圆滑 · 商务 |
| Maru | Maru | 212° | L33 | 线缆 | 望远镜 / 齿轮 | 灵巧 · 发明 |
| Sam | Sam | 218° | L21 | 线缆 | 吉他 / 滑板 | 随性 · 音乐 |
| Henchman ★ | Henchman / SVE_Henchman | 229° | L33 | 金属锭 | 木箱 / 斗篷 | 寡言 · 随从 |
| Sebastian | Sebastian | 235° | L24 | 线缆 | 蝙蝠 / 游戏手柄 | 克制 · 短句 |
| Lewis | Lewis | 243° | L25 | 纸卷 | 紫色短裤 / 钥匙 | 体面 · 镇长 |
| Victor | Victor | 251° | L29 | 纸卷 | 蓝图 / 酒杯 | 内敛 · 设计 |
| Abigail | Abigail | 259° | L30 | 矿脉 | 紫水晶簇 / 短剑 | 好奇 · 直觉 |
| Krobus | Krobus | 274° | L21 | 黏液 | 虚空蛋 / 史莱姆球 | 谨慎 · 暗影 |
| Wizard | Wizard | 288° | L24 | 符文线 | 水晶球 / 法杖 | 神秘 · 判断 |
| Jas | Jas | 299° | L29 | 花枝 | 布偶 / 粉花 | 安静 · 童真 |
| Olivia | Olivia | 309° | L33 | 缎带 | 酒杯 / 珠宝 | 矜贵 · 品味 |
| Sophia | Sophia | 320° | L29 | 葡萄藤 | 葡萄串 / 粉花 | 轻快 · 跳脱 |
| Vincent | Vincent | 328° | L21 | 花枝 | 糖果 / 风筝 | 活泼 · 童言 |
| Scarlett | Scarlett | 335° | L33 | 缎带 | 剪刀 / 线团 | 利落 · 裁缝 |
| Penny | Penny | 342° | L21 | 书脊 | 书 / 粉笔 | 温柔 · 教学 |
| Evelyn | Evelyn | 350° | L33 | 毛线 | 饼干 / 粉花 | 慈祥 · 烘焙 |
| Jodi | Jodi | 358° | L29 | 作物茎 | 平底锅 / 菜篮 | 操持 · 家常 |

色相从 5° 到 358° 铺开，相邻间隔 5.8–9°，底色亮度档交替。

---

## 5. 材质库与物件库

**材质 19 种**（决定气泡边框形态，organic 沿边框蜿蜒生长）：

| 键 | 名称 | 类 | 键 | 名称 | 类 |
|---|---|---|---|---|---|
| `vine` | 藤蔓 | organic | `crystal` | 矿脉 | hard |
| `grapevine` | 葡萄藤 | organic | `ore` | 金属锭 | hard |
| `laurel` | 月桂枝 | organic | `arcane` | 符文线 | hard |
| `wheat` | 麦秆 | organic | `cable` | 线缆 | hard |
| `leaf` | 阔叶枝 | organic | `ribbon` | 缎带 | hard |
| `crop` | 作物茎 | organic | `paper` | 纸卷 | hard |
| `flower` | 花枝 | organic | `book` | 书脊 | hard |
| `wood` | 木栏 | hard | `wool` | 毛线 | hard |
| `fish` | 渔网 | hard | `slime` | 黏液 | hard |
| `stone` | 碎石 | hard | | | |

**物件 96 件**：32×32 像素道具，每个角色取 2 件，头像遵循 JSON 中显式指定的 `glyph`。2026-09-20 实施核对：`objectLibrary` 实际为 96 个键，原文与交接附件中的 100 为计数误记；不增加无规格物件凑数。九角色已认可的成品图案继续保留。
完整清单见 JSON 的 `objectLibrary`。

---

## 6. 分配与审计

| 维度 | 规则 |
|---|---|
| 色相 | 九个已交付色相作**锚点**切段，其余角色按语义归段、段内均匀铺开 |
| 底色亮度 | 四档 `21 / 25 / 29 / 33`，按色相顺序选"与邻近角色亮度差最大"的档 |
| 材质 / 物件 | 按角色语义指定；无专属定义的走关键词推断 |

**审计口径**：色相相差 <6° 的两个角色，底色亮度必须相差 ≥6。
（4 个亮度档跨度只有 12，在 12° 色相跨度内塞 4 个角色时两两差 ≥8 数学上做不到。）

另有校验：每条元素引用的材质与物件必须存在于库中。

实测：

```text
好感度名单 47 条 → 独立角色 46 个（登记覆盖 47 条）
  别名复用 4 个，归并组 1 个
审计通过：色相相差 <6° 的角色，底色亮度都拉开了 ≥6 ✅
exit=0　compileall exit=0
```

---

## 7. 与九角色定稿的关系

`docs/npc-bubble-elements-2026-09-19.json` 里九个角色的色板（hue / bubbleLevel / accent /
accentSoft / bubble / border / fruit / fruitHi）在本表中原样保留，逐字段一致。

---

## 8. 给实现方的要点

1. **以本 JSON 为唯一数据源**，生成 `NPC_STYLES`、`VINE_COLORS` 与头像 glyph，
   消除现在散落多处的拷贝。
2. **补材质渲染分支**：现有实现只支持 9 种，本表用到 19 种。
3. **补物件图形**：机读库里有 96 件，实施前仅约 18 件。
4. **不要改九个已交付角色的色值**；改任何值后重跑脚本确认审计通过。
5. 玩家遇到新 NPC、`friendshipData` 增长时，更新 `data/friendship-roster.json` 后重跑即可。

---

## 9. 复现

```powershell
Set-Location E:\workspace\projects\stardew-ai-npc.worktrees\story-memory

py -3.10 -B scripts/build_npc_bubble_elements.py           # 生成
py -3.10 -B scripts/build_npc_bubble_elements.py --check   # 只审计
py -3.10 -B -m compileall -q scripts
```

视觉核对：`E:\workspace\hub\.tmp\npc-scoped-pairs.png`（色相最接近的 8 组，逐组渲染真实气泡）
与 `npc-scoped-grid.png`（46 角色色卡）。

---

## 10. 边界

新增 `data/friendship-roster.json`、`docs/npc-bubble-elements-all-2026-09-19.{md,json}`、
`scripts/build_npc_bubble_elements.py`。未改任何业务代码，未启动 Stardew/SMAPI、
未部署 DLL、未修改正式 Mods/存档（存档为只读解析）、未发起云端请求、未创建 Git commit。
