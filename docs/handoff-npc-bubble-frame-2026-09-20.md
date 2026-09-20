# 角色气泡装饰边框 · 交接（2026-09-20）

## 目标

把 astra 在 Bridge 回放页做的**角色气泡装饰边框**搬进游戏内的 F8/F9 界面。
气泡本体（角色配色 + 图标徽章）已经接完并验收，本文件只覆盖**装饰边框**这一块。

## 为什么不能用九宫格

边框由 `bridge/src/stardew_ai_bridge/group_dialogue_review_page.py`
的 `_CHARACTER_FRAME_SCRIPT`（第 46–150 行）**按气泡实际尺寸过程式生成**，
不是平铺图案。三个特征决定了切图必然坏构图：

1. **位置按比例、尺寸绝对**：细节元素摆在边上的 `t ∈ [0,1]` 比例位置，
   但元素自身大小固定（`detailScale ∈ {1, .75, 1.125, .875}`），只有位置随尺寸走。
2. **variant 决定构图**：`variant = (该角色出现次数 + kind 字符码和) % 3`，
   三套 `layouts` 的细节分布完全不同，同角色多次发言还会轮换。
3. **茎是连续折线**：沿边每 ~8px 一个 2px 阶梯，跨整个边长。

所以做法是**在 C# 里复刻这套布局算法**，素材只导出「零件」。

## 已完成：零件素材

`scripts/export_npc_bubble_frames.py` → `smapi/assets/npc_bubble_frames.png`

- 46 行（角色）× 3 列，每格 **32×32**，透明底，共 96×1472
- 第 0 列 = **细节造型**（按该角色 palette 着色；19 种 kind 各自的形状）
- 第 1、2 列 = 两个 **32×32 大物件**（`ornament.objects`）
- 脚本从回放页源码里正则取出 `characterFrameSvg` 并**在浏览器里真实执行**，
  再从生成的 SVG 中摘出 `[data-ink="detail"]` / `[data-ink="object"]` 元素，
  清掉定位 transform 后单独渲染——**形状与配色都来自唯一那份定义，没有复制**。

同批还有 `npc_bubbles.png`（46 个角色图标，用于气泡内的头像徽章，已接入）。

## 待做

### 1. `smapi/NpcBubbleFrameData.cs`（由导出脚本生成）

`NpcBubbleStyle.cs` 目前只有配色与图标索引，**没有边框需要的 kind 与四个描边色**。
需要补一张表：

- `Kind`（19 种字符串）
- `Line` / `Highlight` / `Leaf` / `LeafHi`（来自 `ornament.colors`）
- `SheetRow`（角色在素材表里的行号，与 `npc_bubble_frames.png` 对齐）

生成方式照抄 `scripts/export_npc_bubble_assets.py` 的写法（含 `utf-8-sig` 输出）。

### 2. `smapi/NpcBubbleFrame.cs`（手写，约 250 行）

复刻 `characterFrameSvg`，逐条对应：

```
pad = 14；画布 = 气泡尺寸 + 2*pad，边框以气泡为中心外扩
variant = (occurrence + kind 各字符码之和) % 3
layouts[3]  → 四条边各自的细节比例位置表（照抄三行常量）
organic = kind ∈ {vine, grapevine, laurel, wheat, crop, leaf, flower}
edgePoint(side, t)：organic 加 sin(π·t)·4 的弯曲；vine/grapevine 再加 sin(2π·t)·2 摆动
pixel(n) = round(n/2)*2   ← 2px 阶梯的像素对齐，必须保留
茎：从 t=0 到 1 取 count = max(2, ceil(边长/8)) 段，交替 H/V 走折线
   先画 outline（#171f20，宽 lineWidth+2），再画 stem（c.line，宽 lineWidth）
   lineWidth：ribbon/wood/book → 6；arcane/fish → 2；slime → 5；其余 → 3
   organic 或 ribbon 再叠一条 1px 的 c.highlight 高光
细节：每条边按 layouts[variant][side] 逐个摆放
   detailScale 按 (index + variant + (水平边?0:1)) % 4 取 {1,.75,1.125,.875}
   organic 的额外偏移与左右翻转（(index+variant)%2 决定镜像）见源码 105–111 行
   grapevine 在水平边且 index 为奇时多画一小段卷须
大物件：placements[3] 照抄，尺寸 36/40/28；grapevine 且 w ≥ 260 时多摆一个
```

**绘制手段**：茎用 `Game1.staminaRect`（1×1 白点纹理）逐段 `b.Draw(...)` 画矩形——
像素风本来就该是矩形，不需要 XNA 的画线 API。细节与大物件用 `b.Draw(sheet, dest, src, Color.White)`。
零件图集要做成嵌入资源（见下）。

### 3. 接入点

`smapi/ChatBubbleDrawing.cs` 的 `Draw(...)` 里，**画完 `drawTextureBox` 底色、写文字之前**调用：

```csharp
NpcBubbleFrame.Draw(b, bounds, npcId, occurrence);
```

`occurrence` 需要调用方提供：F8 私聊可固定传 0（同一 NPC 一个会话里构图稳定即可）；
F9 群聊按 `visibleMessages` 里该 NPC 已出现的次数递增（与回放页语义一致）。

**注意**：边框会画到气泡外侧 `pad = 14` 的范围，F8/F9 的气泡间距
（`ChatBubbleDrawing.Gap = 8`）需要相应调大，否则相邻气泡的装饰会叠在一起。

## 验收

```powershell
dotnet build smapi\StardewAI.NPC.csproj /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false
dotnet test  smapi\tests\StardewAI.NPC.Tests.csproj -p:GamePath="D:\sbeam\steamapps\common\Stardew Valley"
pwsh -File scripts\start_visual_test.ps1 -ActionId group-message -OutputPath 'artifacts\visual-tests\bubble-frame-v1' -ScenarioId 'bubble-frame'
```

对比基准：`.tmp/all-npc-bubbles/characters-1..4.png`（astra 的 46 角色样张，
variant 固定为 2）。**建议先只调一个角色对齐，再铺开到全部 kind**。

## 已知坑（都已踩过）

- 素材必须走 `<EmbeddedResource>`：本项目部署脚本只复制 DLL 与 manifest.json。
- 建纹理要等 `GameLoop.GameLaunched`，`Entry()` 阶段 `GraphicsDevice` 常为 null。
- 构建必须显式传 `GamePath`（DSH 以 SYSTEM 运行，ModBuildConfig 探不到游戏目录）。
- `-ActionId capture` 只开空界面，看不到气泡；要用 `topic` / `group-message`。
- 跑导出脚本要设 `PYTHONIOENCODING=utf-8` 与 `PLAYWRIGHT_BROWSERS_PATH`。
