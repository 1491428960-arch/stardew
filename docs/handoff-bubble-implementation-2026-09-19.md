# 交接指令 · 好感度系统 NPC 气泡元素落地（2026-09-19）

> 给接手实现的一方。元素已敲定（46 个角色），你负责落地实现。
> 复制下方"指令正文"整段即可。

---

## 指令正文（从这里开始复制）

````text
# 任务：星露谷 AI NPC · 让好感度系统里的每个 NPC 都有各自的气泡

你是接手实现的 Agent。前一轮已完成**元素敲定**（只定规格、未改业务代码），
你负责把规格落地到代码，并补上缺失的图形与渲染分支。没有前情上下文，本文自包含。

## 0. 一句话目标

聊天与群聊只服务**好感度系统内的 NPC**（存档 player.friendshipData 里有记录的角色），
共 47 条记录、归并后 **46 个独立角色**。现在代码里只有 9 个角色有气泡元素定义，
其余全部退化成同一套默认样式。

让这 46 个角色**各有各的气泡**，并且装饰风格统一、不压字。
用户对当前藤蔓装饰的原话是「不是蜿蜒的、廉价感强、与星露谷风格不统一」——
装饰形态的返工是本次核心，不是可选优化。

## 1. 工作现场

    项目根：E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory
    分支：  codex/story-memory
    页面实现：bridge/src/stardew_ai_bridge/group_dialogue_review_page.py
    元素数据：bridge/src/stardew_ai_bridge/npc_bubble_elements.py（目前只有 9 个角色）
    回放页：http://127.0.0.1:5678/test/group/review
    启动 Bridge：powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1

本工作树**非常脏**（数十个文件未提交、上万行改动），且**可能有其他会话同时工作**：

- 禁止 `git reset --hard`、`git clean`、`git checkout --`、`git stash`
- 不创建 Git commit，除非用户明确要求
- 所有 git 命令加 `-c safe.directory=<项目根绝对路径>`
- 动手改 `group_dialogue_review_page.py` 前，先确认没有其他会话正在改它

## 2. 先读这些（按顺序，不要跳过）

1. `docs/npc-bubble-elements-all-2026-09-19.md` —— **权威规格**：范围界定、归并规则、
   46 角色元素表、材质库、审计口径
2. `docs/npc-bubble-elements-all-2026-09-19.json` —— 机读数据：46 角色完整色板 / 材质 /
   标志物 / 气质标签，以及 19 种材质与 100 件物件的语义定义
3. `data/friendship-roster.json` —— 适用范围名单（来自存档 friendshipData），含别名与归并组
4. `docs/npc-bubble-elements-2026-09-19.md` / `.json` —— 九个已交付角色的定稿（**不可改动**）
5. `bridge/src/stardew_ai_bridge/npc_bubble_elements.py` —— 你要扩展的数据模块
6. `bridge/src/stardew_ai_bridge/group_dialogue_review_page.py` —— 你要改的页面

## 3. 现状

| 位置 | 内容 | 状态 |
|---|---|---|
| `npc_bubble_elements.NPC_BUBBLE_ELEMENTS` | 9 个角色：icon / tone / palette / ornament / motifs | 只覆盖 9/46 |
| 页面内 `_CHARACTER_FRAME_SCRIPT` | 按气泡尺寸生成角色边框 SVG | 只支持 9 种 ornament kind |
| `NPC_STYLES` 兜底 | `styleFor()` 对未定义角色返回统一灰色样式 | 其余 37 个角色全走这里 |

**不要**按 `/api/npcs` 的全量名单做——那有 135 个，其中 90 个不在好感度系统里、
进不了群聊，做了也不会显示。

## 4. 你要做的事

### 任务 A · 数据源合并

以 `docs/npc-bubble-elements-all-2026-09-19.json` 为**唯一数据源**，生成
`NPC_STYLES`、`VINE_COLORS`、头像 glyph——消除现在散落在多处的拷贝。
九个已交付角色的色板逐字段保持原样。
别名（`GuntherSilvian`→Gunther 等）与归并组（`Henchman`/`SVE_Henchman`）共用同一份元素。

### 任务 B · 补 10 种材质的渲染分支

现有 `_CHARACTER_FRAME_SCRIPT` 只画得了 9 种 kind。规格定义了 **19 种**，
以下 10 种需要你补渲染分支：

    crop 作物茎 · leaf 阔叶枝 · flower 花枝 · ore 金属锭 · book 书脊
    wood 木栏 · wool 毛线 · fish 渔网 · slime 黏液 · stone 碎石

`crop`/`leaf`/`flower` 属于 organic（沿边框蜿蜒生长），其余是硬边装饰。
每种要有自己的轮廓特征，不能只换颜色。

### 任务 C · 补标志物图形

物件库有 **100 件** 32×32 像素道具，现有实现只画了约 18 件。按语义补全其余；
同一件图形可同时用于边框挂饰与头像 glyph（`glyph` 就是该角色 `objects[0]`）。

### 任务 D · 重做气泡装饰形态（本次核心）

现有实现把装饰画在气泡**内侧**（`inset: 0`，viewBox = 气泡盒子），
pad 13 + 振幅 5.4 + 主干 4.2 ≈ 视觉厚度 15px，而单行气泡高约 60px、行高约 26px、
上下各余 17px —— **装饰直接压到文字边上**。

必须满足：

1. 装饰与文字最小净距 **≥8px**
2. pad 随气泡高度自适应：`clamp(13, height/6, 18)`
3. 气泡高度 <72px 时振幅降到 ≤3，或只保留左右两边
4. **保持"一条连续 SVG、非平铺"**：`border-image` 九宫格平铺方案已被用户否决过一次
   （平铺每 64px 印一遍相同图案，与"蜿蜒"本身矛盾），不要退回
5. 蜿蜒感要真的出来——现有参数在 300px 宽气泡上周期偏短，观感接近"锯齿贴边"。
   具体参数你定，但必须用截图证明
6. 装饰只加在 `.message.npc-message .bubble` 上（曾误加到玩家气泡）

头像当前是圆角方块 + 单色符号，与星露谷像素风不一致。**风格你来定**。

### 任务 E · 形状与死代码

- 删除 `role-sebastian` / `role-sophia` / `role-elliott` / `role-wizard` 四条专属圆角
  （九角色里只有 4 个有＝不完整的角色化），统一 12px 圆角
- 清理 `_VINE_BASE`、`_pixel_vine_border()`、CSS `.bubble-ring` 等无调用方的残留

## 5. 验收标准（全部必须通过）

```powershell
Set-Location E:\workspace\projects\stardew-ai-npc.worktrees\story-memory
$env:PYTHONPATH='bridge/src;scripts'

# 1) 元素分配审计：名单全覆盖 + 材质物件引用有效 + 退出码 0
py -3.10 -B scripts/build_npc_bubble_elements.py --check

# 2) 色板审计（九角色口径）
py -3.10 -B scripts/audit_npc_bubble_palette.py

# 3) 页面契约测试
py -3.10 -m pytest bridge/tests/test_external_dialogue_lab.py -q

# 4) Bridge 全量（当前基线 1732 passed，不得低于此）
py -3.10 -m pytest bridge/tests -q

# 5) 结构检查
py -3.10 -B -m compileall -q bridge/src scripts

# 6) 工作树检查（只允许既有 LF/CRLF 提示）
git -c safe.directory=E:\workspace\projects\stardew-ai-npc.worktrees\story-memory diff --check
```

**视觉验收（必须做，不能只靠测试）**：

- 选一个群聊案例，确认每个参与者都有自己的气泡，不再是统一灰色
- 三人同场时气泡一眼可分
- 装饰不压字、不再"锯齿贴边"

截图手段：无头 Chrome（`chrome --headless=new --screenshot=out.png --virtual-time-budget=7000 <url>`）
或 Python playwright（已装，用自带 headless chromium，**不要用用户的 Chrome profile**）。
逐案例截图 + 直接读图自查，别靠猜。

## 6. 红线

- **不改九个已交付角色的色值**（`docs/npc-bubble-elements-2026-09-19.json` 为准）
- **不改九角色声线/persona**，不动 `data/personas/`
- **不改 `prompts.py`、群聊 Prompt、批次生成逻辑**（另一条工作线，其他会话在改）
- **不要按 135 个全量做**（见 §3 末）
- 改任何色值后必须重跑 `scripts/build_npc_bubble_elements.py` 确认审计通过
- 不启动 Stardew/SMAPI、不部署 DLL、**不写存档**（读 friendshipData 只读）
- 不发起云端模型请求（需用户明确确认，且写新目录、不覆盖旧批次）
- 不 reset / clean / commit
- 不输出任何 API Key、Token、Cookie

## 7. 已知坑

1. 适用范围来自**存档** `friendshipData`，不是索引全量；玩家遇到新 NPC 后名单会变长，
   更新 `data/friendship-roster.json` 再重跑脚本即可
2. `GuntherSilvian` / `MarlonFay` / `MorrisTod` / `MermaidLantana` 是 SVE 命名，
   与原版 ID 指向同一角色，**只写一份元素**
3. 男版与娘化版**不重复**：`female-bachelors` 覆盖同一个 npcId（`Elliott` 显示名埃琳娜、
   `Harvey` 哈丽特、`Alex` 爱丽克斯、`Shane` 珊恩、`Sebastian` 塞布瑞娜、`Sam` 萨姆）。
   气泡元素用道具表示角色、不涉及性别，男女版共用
4. `_available_batches()` 曾按目录名做字符串排序，`v9` > `v10` 导致新批次不显示，
   已改为按 `cases.json` 写入时间倒序。**不要改回字符串排序**
5. 回放页有 `visibilitychange` 监听：切回标签页且距上次加载 >2 秒会自动 reload
6. `bridge/tests/test_external_dialogue_lab.py` 对 `VINE_COLORS` 等常量有断言，
   改数据结构必须同步测试
7. 环境提示：若 `py -3.10` 报「Python 3.10 not found」，改用完整路径
   `C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe`（不带 `-3`）

## 8. 交付物

1. 扩展后的 `npc_bubble_elements.py`（覆盖 46 个角色）与改后的 `group_dialogue_review_page.py`
2. 同步更新的测试
3. `docs/active-work.md` **末尾追加一条**日志：改了什么、实测命令与输出（数量、退出码）、
   截图路径、未做的事
4. 截图证据（放 `E:\workspace\hub\.tmp\`，命名自明）

交付说明里请列出：哪些验收项通过（附实际输出）、哪些没做或存疑。

## 9. 遇到歧义怎么办

- 规格说清了 → 照做，不要自行发挥
- 规格没说清（装饰参数、材质的具体画法、头像风格）→ 你定，但必须给截图与理由
- 与用户既有偏好冲突（例如"星露谷风格"的具体理解）→ **停下来问用户**，不要猜
- 发现规格有错 → 修完重跑 `scripts/build_npc_bubble_elements.py --check`，并写进交付说明
````

## 指令正文（复制到此结束）

---

## 附：本轮交付物

| 文件 | 内容 |
|---|---|
| `data/friendship-roster.json` | 适用范围名单（存档 friendshipData，含别名与归并组） |
| `docs/npc-bubble-elements-all-2026-09-19.md` | 46 角色规格：范围、归并规则、元素表、材质库、审计口径 |
| `docs/npc-bubble-elements-all-2026-09-19.json` | 机读数据：46 角色 + 19 种材质 + 100 件物件 |
| `scripts/build_npc_bubble_elements.py` | 分配器：可重跑、可审计，名单变化自动纳入 |

截图证据在 `E:\workspace\hub\.tmp\`：`npc-scoped-pairs.png`（色相最接近的 8 组）、
`npc-scoped-grid.png`（46 角色色卡）。
