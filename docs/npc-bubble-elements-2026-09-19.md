# 群聊气泡 · 九角色元素规格（2026-09-19）

> **先期准备产物。** 本文只**敲定元素**，不含实现改动。气泡视觉本身（藤蔓形态、留白、头像风格）由接手实现的一方按本文契约继续做。
>
> 现场：worktree `story-memory`，回放页 `http://127.0.0.1:5678/test/group/review`，
> 实现文件 `bridge/src/stardew_ai_bridge/group_dialogue_review_page.py`。

---

## 1. 结论先行

现有九角色**只有气泡底色一个变量**在起作用，而这个变量本身是坏的：

| 问题 | 实测数据 | 后果 |
|---|---|---|
| accent 撞色 | Abigail `#b796ff` × Wizard `#b18cff` 色相差 **0.4°**；Emily `#69d7c4` × Harvey `#72c9c5` **7.6°**；另有 3 对 <25° | 同场角色的名字色、头像、边框几乎一样 |
| 气泡底色重叠 | Emily × Harvey 底色色相差 **0.2°**、亮度差 **0.2**；Abigail × Wizard **2.0° / 0.6** | 两人同场时气泡糊成一片 |
| 果实被底色吞掉 | 果实/底色对比最低 **2.14**（Wizard）、**2.22**（Sebastian） | 藤蔓上唯一的角色差异看不见 |
| 果实与角色脱节 | Sophia accent 色相 337.5°，果实 279.0°，差 **58.5°** | 果实色像是随便给的 |

上表旧值由一次性脚本直接读取 `group_dialogue_review_page.py` 里的 `NPC_STYLES` / `_VINE_FRUIT` 常量算出（口径：气泡底色按 alpha 合成到页面 `--bg: #11121b` 后再算 WCAG 对比度）。**新**色板则随时可用 `py -3.10 scripts/audit_npc_bubble_palette.py` 复跑。

**本轮已把色板重排并审计通过**（见第 3 节），实测值见第 7 节。

---

## 2. 现状盘点（实现方需要知道的坑）

元素当前散落在**四处**，彼此没有单一数据源：

| 位置 | 内容 | 状态 |
|---|---|---|
| `NPC_STYLES`（JS 模板内） | icon / tone / className / accent / accentSoft / bubble / border | 在用；`border` 字段实际未被 CSS 读取 |
| `_SPEAKER_GLYPHS` | 九角色头像内联 SVG | 在用 |
| `_SPEAKER_MOTIFS` | 九角色 ×3 标志物 SVG | **死数据**：注入为 JS 常量 `SPEAKER_MOTIFS` 后无任何消费者 |
| `_VINE_FRUIT` | 九角色果实双色 | 在用（`VINE_COLORS`） |

另有 vine3 时代的残留死代码：`_VINE_BASE`、`_pixel_vine_border()`、CSS `.bubble-ring { display: none }` —— 均无调用方，建议实现时一并清理。

气泡形态现状：圆角 12px，**没有尾巴**；`role-sebastian / role-sophia / role-elliott / role-wizard` 另有四条专属圆角（九角色里只有 4 个有，属不完整的角色化）。

---

## 3. 定稿元素表

### 3.1 视觉令牌（本轮敲定值）

按色相环顺序排列。`bubbleLevel` 是气泡底色的目标亮度分层，用于把色相接近的相邻角色再拉开一层。

| NPC | 语义锚点 | 色相 | 底亮度 | accent | accentSoft | bubble | border | fruit | fruitHi |
|---|---|---|---|---|---|---|---|---|---|
| Alex | 运动红 · 夹克明星 | 5° | 24 | `#f29a92` | `#f0ccb2` | `rgba(87, 40, 35, .92)` | `#d4685e` | `#e7746a` | `#f1c0bb` |
| Elliott | 手稿琥珀 · 海边棕 | 32° | 30 | `#f2c592` | `#f0e8b2` | `rgba(109, 79, 44, .92)` | `#d49d5e` | `#e7ac6a` | `#f1d8bb` |
| Harvey | 诊所苔绿 · 照料 | 126° | 29 | `#92f29c` | `#b2f0cd` | `rgba(43, 105, 49, .92)` | `#5ed46a` | `#6ae776` | `#bbf1c1` |
| Emily | 碧玉青 · 布料宝石 | 170° | 24 | `#92f2e2` | `#b2e6f0` | `rgba(35, 87, 78, .92)` | `#5ed4c0` | `#6ae7d2` | `#bbf1e8` |
| Shane | Joja 牛仔蓝 · 疲惫 | 200° | 30 | `#92d2f2` | `#b2c7f0` | `rgba(44, 87, 109, .92)` | `#5eadd4` | `#6abde7` | `#bbdff1` |
| Sebastian | 夜色靛蓝 · 雨车库 | 235° | 24 | `#929af2` | `#c1b2f0` | `rgba(35, 40, 87, .92)` | `#5e68d4` | `#6a74e7` | `#bbc0f1` |
| Abigail | 紫水晶 · 冒险 | 259° | 30 | `#b092f2` | `#dab2f0` | `rgba(65, 44, 109, .92)` | `#835ed4` | `#916ae7` | `#ccbbf1` |
| Wizard | 星界品红紫 · 符文 | 288° | 24 | `#de92f2` | `#f0b2e8` | `rgba(77, 35, 87, .92)` | `#bc5ed4` | `#ce6ae7` | `#e6bbf1` |
| Sophia | 葡萄花粉 · 轻快 | 320° | 29 | `#f292d2` | `#f0b2c7` | `rgba(105, 43, 84, .92)` | `#d45ead` | `#e76abd` | `#f1bbdf` |

完整可机读版本（含 SVG、声线）：`docs/npc-bubble-elements-2026-09-19.json`。

### 3.2 气质标签与标志物

气质标签沿用现有六字标签（`tone`），它们是回放页 `speaker-tone` 的显示文案，**不建议改动**（已与资料库声线一致）。

| NPC | 气质标签 | 主标志物（= 头像 glyph） | 备用标志物 | 果实语义 |
|---|---|---|---|---|
| Abigail | 好奇 · 直觉 | 紫水晶 | 剑 / 音符 | 紫水晶果 |
| Alex | 直球 · 行动派 | 橄榄球 | 哑铃 / 爪印 | 运动红果 |
| Emily | 温柔 · 灵感 | 宝石 | 水晶球 / 星芒 | 碧玉果 |
| Elliott | 铺陈 · 诗意 | 羽毛笔 | 海浪 / 书页 | 琥珀果 |
| Harvey | 稳重 · 照料 | 医疗十字 | 咖啡 / 眼镜 | 苔绿果 |
| Sebastian | 克制 · 短句 | 蝙蝠 | 键盘 / 车轮 | 靛蓝果 |
| Shane | 疲惫 · 嘴硬 | 咖啡杯 | 小鸡 / 酒瓶 | 牛仔蓝果 |
| Sophia | 轻快 · 跳脱 | 花（五点） | 葡萄 / 星 | 葡萄串 |
| Wizard | 神秘 · 判断 | 五角星 | 法杖 / 符文 | 星界果 |

头像 glyph 即 `_SPEAKER_MOTIFS[npc][0]` 包一层 `<svg viewBox="0 0 24 24">`，与 `_SPEAKER_GLYPHS` 完全对应 —— **两处是同一份数据的两份拷贝**，实现时应合并为单一来源。

### 3.3 声线锚点（来自资料库，不新写画像）

群聊 Prompt 已由 `prompts.build_group_voice_cards()` 消费这些字段，元素规格只做**确认**，不改写：

| NPC | 资料库来源 | 核心特质 | 招牌动作（signatureMoves） |
|---|---|---|---|
| Abigail | vanilla | 好奇 / 勇敢 / 有点叛逆 | 资料库无独立字段，走 tone + sentencePattern |
| Alex | vanilla + female-bachelors | 自信 / 外向 / 行动派 | 同上 |
| Emily | vanilla | 热情 / 富有创造力 / 尊重直觉 | 同上 |
| Elliott | female-bachelors | （coreTraits 为空） | 同上，另有 `emotionTexture` |
| Harvey | female-bachelors | （coreTraits 为空） | 同上，另有 `emotionTexture` |
| Sebastian | vanilla + female-bachelors | 安静 / 讽刺 / 喜欢独处 / 有创造力 | 同上 |
| Shane | vanilla + female-bachelors | 直率 / 疲惫 / 愿意改变 | 同上 |
| Sophia | sve | 热爱葡萄酒酿造 / 敏感而坚韧 | ✅ 有两条：细节起句、被夸/被催时停顿改口 |
| Wizard | vanilla + sve + rasmodia | 谨慎 / 博学 / 观察敏锐 | ✅ 有两条：先给判断不铺垫、关心藏在提醒里 |

只有 Sophia 与 Wizard 定义了 `signatureMoves`；其余七人靠 `tone` + `sentencePattern` + `openers/closers/avoid`。字段明细见 JSON。

---

## 4. 敲定决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | **accent 在色环上重排**，九角色最小间距 ≥24°（原 0.4°） | 颜色是同场区分的第一通道，原来等于没有 |
| D2 | **气泡底色用亮度分层**：色相相差 <30° 的相邻角色，底色亮度差 ≥5 | Emily×Harvey 原本底色完全一样（差 0.2） |
| D3 | **果实色 = accent 同色系提亮**，保证果实/底色对比 ≥2.8（实测 3.15–5.96） | 果实是藤蔓上唯一的角色差异，必须看得见；Sophia 的葡萄紫与粉色 accent 脱节 58.5°，本次归到同色系 |
| D4 | **藤蔓保持游戏绿统一**，角色差异只走果实色 | 藤蔓是"世界观统一"，角色化交给果实与底色；九种颜色的藤蔓会立刻散架 |
| D5 | **气泡形状统一 12px 圆角**，删除四条 `role-*` 专属圆角 | 只有 4/9 有专属圆角＝不完整的角色化；形状对辨识贡献极低，反而破坏统一（用户已明确抱怨"不统一"） |
| D6 | **motif[0] 作头像主标志，motif[1]/[2] 保留为标志物库但不上气泡** | 用户已否决"标志物环绕"与"角部徽记"两种用法；备用标志可用于参与者 chip、hover 等未来位置 |
| D7 | **声线锚点一律取自资料库**，群聊不复写画像 | 单 NPC 链路已有 `ContextBuilder` + 索引管线，手写第二套必然漂移 |
| D8 | **色板必须有可复跑的审计** | 撞色是肉眼容易漏、数据一测就现形的问题 |

---

## 5. 给实现方的契约

### 5.1 不变量（改视觉时不得破坏）

1. 九个 accent 两两色相差 ≥20°；相邻 <30° 的必须靠底色亮度差 ≥5 区分。
2. 名字色/气泡底对比 ≥4.5；果实/气泡底对比 ≥2.8；气泡底/页面底对比 ≥1.30。
3. 果实色必须与所属角色 accent 同色系（色相差 ≤45°）。
4. 任何新元素都必须能由 `scripts/audit_npc_bubble_palette.py` 审计通过。

### 5.2 当前待修的视觉缺陷（本轮未动，留给实现）

| 现象 | 实测 | 规格要求 |
|---|---|---|
| 藤蔓侵入文字区 | 藤蔓画在气泡**内侧**（`.bubble-vine { inset: 0 }`，viewBox = 气泡盒子），pad 13 + 振幅 5.4 + 主干 4.2 ≈ 视觉厚度 15px；单行气泡高约 60px，行高约 26px，上下各余 17px | 装饰与文字最小净距 **≥8px**；藤蔓 pad 随高度自适应 `clamp(13, height/6, 18)` |
| 矮气泡装饰过密 | 高 <72px 时波峰波谷几乎贴住文字（截图可见 Sophia「我喜欢安静些的……钢琴曲算吗？」） | 高 <72px 时振幅降到 ≤3，或只保留左右两边 |
| 蜿蜒感不足 | pad 13 / amp 5.4 / wave 62，在 300px 宽的气泡上周期偏短，观感接近"锯齿贴边" | 由实现方定，但需保持"连续一条、非平铺"（`border-image` 平铺方案已被否决） |
| 头像风格 | 圆角方块 + 单色符号，与星露谷像素风不一致 | 建议改像素风；本轮只确认 glyph 语义（见 3.2），未定风格 |
| 死代码 | `_VINE_BASE`、`_pixel_vine_border()`、`.bubble-ring`、`_SPEAKER_MOTIFS→JS` 注入 | 建议清理；`_SPEAKER_GLYPHS` 与 `_SPEAKER_MOTIFS[npc][0]` 合并为单一来源 |

### 5.3 落地方式建议

把第 3 节的数据提升为**单一数据源**（模块常量或 JSON），由它同时生成 `NPC_STYLES`、`VINE_COLORS`、`_SPEAKER_GLYPHS`，消除现在的四份散落拷贝。`docs/npc-bubble-elements-2026-09-19.json` 可直接作为该数据源的初始内容。

---

## 6. 待用户确认

1. **Elliott 与 Harvey 的人称冲突**：`data/personas/` 里 vanilla **没有** Elliott / Harvey，两人的声线只来自 `female-bachelors.json`（性转版，`pronouns = she/her`），`coreTraits` 也为空；而气泡视觉用的是男性默认形象（§3.2 的羽毛笔、医疗十字 + 现有头像）。**需要确认气泡与称谓按男版、女版还是按 mod 启用状态切换。**
2. **Wizard 同样多来源**：`vanilla`（他）+ `sve` + `rasmodia`（她，Romanceable Rasmodius）。当前规格取 rasmodia 的 `tone`/`signatureMoves`（更明确），显示名仍是 `Wizard`。是否需要在 Rasmodia 路线下换显示名与视觉？
3. **色板数值是否接受**：本轮只保语义锚点（紫水晶、Joja 蓝、诊所绿、葡萄花粉……），具体数值是重新排布的。若某个角色有指定色，改单个 accent 后重跑审计即可。
4. **Alex 覆盖缺口**：`20260919-*` 全部群聊批次里 Alex 从未发言（历史批次有 `group-alex-sebastian-relationship` 案例）。若要验收他的气泡，需要补一个含 Alex 的批次。

---

## 7. 复现与验证

```powershell
Set-Location E:\workspace\projects\stardew-ai-npc.worktrees\story-memory

# 色板审计（退出码 0 = 全部达标）
py -3.10 -B scripts/audit_npc_bubble_palette.py

# 结构检查
py -3.10 -B -m compileall -q scripts
```

本轮实测证据：

```text
审计通过：色相分离、果实对比、名字对比、底色可辨全部达标 ✅  [exit=0]

角色         accent     色相   气泡底                 果实        名字/底  果实/底
Abigail    #b092f2   259.0  rgb(61, 42, 102)     #916ae7      4.79    3.15
Alex       #f29a92     5.0  rgb(81, 38, 34)      #e7746a      5.95    4.30
Emily      #92f2e2   170.0  rgb(34, 81, 74)      #6ae7d2      6.84    5.96
Elliott    #f2c592    32.0  rgb(98, 71, 42)      #e7ac6a      5.37    4.28
Harvey     #92f29c   126.0  rgb(41, 98, 47)      #6ae776      5.34    4.62
Sebastian  #929af2   235.0  rgb(34, 38, 82)      #6a74e7      5.54    3.59
Shane      #92d2f2   200.0  rgb(41, 79, 99)      #6abde7      5.32    4.20
Sophia     #f292d2   320.0  rgb(98, 41, 79)      #e76abd      5.04    3.69
Wizard     #de92f2   288.0  rgb(72, 34, 82)      #ce6ae7      5.84    4.21
```

**真实渲染验证**：把候选色板注入正在运行的回放页（拦截 HTML 响应、只替换 `NPC_STYLES` 与 `VINE_COLORS` 两处数据，渲染逻辑与线上完全同源），逐案例截图核对。批次 `20260919-group-dialogue-cloud-v15-everyone-speaks` 四个案例（8 角色）实测：

- `Abigail + Sebastian + Sophia`：三人在旧色板下底色几乎同紫，新色板下分别为紫水晶 / 靛蓝 / 玫粉，一眼可分；
- `Wizard + Elliott + Harvey`：品红紫 / 琥珀 / 苔绿，果实全部浮出底色；
- `Shane + Harvey`：牛仔蓝 / 苔绿，两人原本 accent 只差 7.6°。

截图与脚本留在 `E:\workspace\hub\.tmp\`（`palette-new-case1..4.png`、`verify_npc_palette.py`、`design_npc_palette.py`）。

---

## 8. 边界

本轮**未改任何业务代码**，只新增 `scripts/audit_npc_bubble_palette.py` 与 `docs/npc-bubble-elements-2026-09-19.{md,json}`；未启动 Stardew/SMAPI、未部署 DLL、未修改正式 Mods/存档、未发起云端请求、未创建 Git commit。
