"""三个游戏内聊天界面的浏览器复刻稿（/test/ui）。

这是**给人看的设计稿**，不是回放真实数据：它把 C# 里的布局规则、配色与气泡绘制
在浏览器里重画一遍，让不开游戏也能看到 F8 私聊、F9 群聊、群聊中心长什么样。

三条原则（与任务约定一致）：

1. **尺寸/颜色/边距尽量从 C# 抄**：每个几何量都在注释里标了 ``smapi/文件.cs:行号``。
2. **气泡复用回放页那套**：``characterFrameSvg`` / ``NPC_STYLES`` / ``NPC_BUBBLE_ELEMENTS``
   直接 import 自 :mod:`group_dialogue_review_page` 与 :mod:`npc_bubble_elements`，
   不复制实现、也不改动回放页。
3. **抄不到的地方明说**：凡是靠截图反推或机制未查明的值，代码注释与页面都标记 ⚠，
   并在页面底部集中列出，方便与真实游戏核对。
4. **能拿到原版贴图就不用近似**：输入框与菜单九宫格已经改成从本机游戏解包目录裁出的
   真 PNG（base64 内联，页面自包含），绘制规则照抄 C# 源矩形，不再靠色值反推（2026-09-20）。

关于「颜色」的一个关键事实（2026-09-20 由截图逐像素验证）：
游戏里 ``IClickableMenu.drawTextureBox`` 是**用 tint 乘以菜单纹理**得到的最终颜色。
所以同一个菜单纹理，白 tint 是米黄面板，``Color(65,44,109)`` tint 就是 Abigail 的深紫气泡。
本页面照这个乘法复刻：``颜色 = 纹理基色 × tint ÷ 255``（逐通道）。
"""

from __future__ import annotations

import json

from .group_dialogue_review_page import _CHARACTER_FRAME_SCRIPT
from .npc_bubble_catalog import NPC_BUBBLE_ALIASES
from .npc_bubble_elements import NPC_BUBBLE_ELEMENTS
from .npc_bubble_panel_plain import (
    NPC_FALLBACK_BUBBLE_TINT,
    PLAIN_MENU_TEX_DATA_URI,
    PLAYER_BUBBLE_TINT,
)
from .npc_bubble_texture import BUBBLE_MENU_TEX_DATA_URI
from .npc_bubble_tint import bubble_tint_of


def _tint_literal(tint: tuple[int, int, int]) -> str:
    """把 tint 元组写成 JS 数组字面量的内容（页面里外面套一层 []）。"""

    return ", ".join(str(channel) for channel in tint)


def _styles_payload() -> dict[str, dict[str, object]]:
    """与回放页同源的 NPC_STYLES（回放页 group_dialogue_review_page.py:235-241）。

    比回放页多一个 ``bubbleTint``：``bubble`` 是**设计色**（页面拿它当最终色用，例如角色面板
    的立绘占位底色），而画进彩色 MenuTiles 的必须是**反推后的 tint** —— 面板是
    「纹理色 × tint ÷ 255」，直接把设计色当 tint 会再乘一次橙黄木纹、整体暗一档
    （Abigail 设计色 (65,44,109) → 渲染成 (64,32,47)）。公式只在
    :mod:`npc_bubble_tint` 里有一份，这里算好交给 JS，页面侧不再各留一份实现。
    """

    return {
        npc: {
            "icon": item["icon"],
            "tone": item["tone"],
            "className": npc.lower(),
            **{
                key: item["palette"][key]
                for key in ("accent", "accentSoft", "bubble", "border")
            },
            "bubbleTint": list(bubble_tint_of(item["palette"]["bubble"])),
        }
        for npc, item in NPC_BUBBLE_ELEMENTS.items()
    }


def _glyphs_payload() -> dict[str, str]:
    """24×24 的角色徽章（回放页 group_dialogue_review_page.py:242-246）。"""

    return {
        npc: '<svg viewBox="0 0 24 24" fill="currentColor" shape-rendering="crispEdges" '
        'aria-hidden="true">' + item["motifs"][0] + "</svg>"
        for npc, item in NPC_BUBBLE_ELEMENTS.items()
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


_UI_PREVIEW_BODY = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>界面复刻稿 · Stardew AI NPC</title>
<style>
:root {
  color-scheme: dark;
  --bg: #14161c;
  --surface: #1d2028;
  --surface-2: #232733;
  --line: #39404f;
  --text: #eceef4;
  --muted: #a3abbd;
  --soft: #cfd5e2;
  --gold: #e5bf7c;
  --green: #b3ce91;
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; color: var(--text); background: var(--bg); }
a { color: inherit; text-decoration: none; }
button, select { font: inherit; }
.page { width: min(1400px, calc(100% - 48px)); margin: 0 auto; padding: 30px 0 64px; }
.eyebrow { color: var(--green); font-size: .67rem; letter-spacing: .18em; text-transform: uppercase; font-weight: 700; }
h1 { margin: 10px 0 12px; font-size: clamp(1.5rem, 2.6vw, 2.1rem); font-weight: 650; }
.subtitle { max-width: 900px; margin: 0; color: var(--muted); font-size: .8rem; line-height: 1.85; }
.subtitle b { color: var(--soft); font-weight: 400; }

.toolbar { display: flex; flex-wrap: wrap; gap: 18px; align-items: flex-end; margin: 22px 0 14px; padding: 14px 16px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }
.field { display: grid; gap: 7px; }
.field > span { color: var(--muted); font-size: .66rem; letter-spacing: .06em; }
.seg { display: flex; gap: 4px; padding: 3px; border: 1px solid var(--line); border-radius: 5px; background: #191c24; }
.seg button { border: 1px solid transparent; border-radius: 3px; padding: 7px 12px; color: var(--muted); background: transparent; cursor: pointer; font-size: .74rem; white-space: nowrap; }
.seg button:hover { color: var(--text); background: #262b36; }
.seg button[aria-pressed="true"] { color: #1b1d24; background: var(--gold); border-color: var(--gold); font-weight: 600; }
.check { display: flex; align-items: center; gap: 7px; color: var(--soft); font-size: .74rem; cursor: pointer; }
.check input { accent-color: var(--gold); }
.toolbar-note { margin-left: auto; color: var(--muted); font-size: .68rem; line-height: 1.7; text-align: right; }

.statusbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 12px; font-size: .72rem; color: var(--muted); }
.pill { border: 1px solid var(--line); border-radius: 999px; padding: 4px 11px; background: var(--surface); }
.pill.ok { color: var(--green); border-color: #47593b; }
.pill.bad { color: #f0a08a; border-color: #7a4234; }
.pill.warn { color: var(--gold); border-color: #6d5c36; }

/* 舞台：精确等于游戏 UI 视口尺寸，内部一律绝对定位到 C# 算出来的矩形 */
.stage-wrap { position: relative; width: 100%; }
.stage {
  position: relative; transform-origin: top left;
  overflow: hidden; border: 1px solid var(--line); border-radius: 3px;
  /* 游戏画面示意底：真实游戏里菜单是叠在场景画面上的 */
  background:
    radial-gradient(120% 90% at 20% 8%, #4b6b45 0%, #35513a 42%, #243528 100%);
}
.stage::after {
  content: "此处为游戏画面示意（菜单叠在场景之上）"; position: absolute; left: 10px; bottom: 8px;
  color: rgba(255,255,255,.34); font-size: 12px; letter-spacing: .04em; pointer-events: none;
}
/* 整屏遮罩：F8（ChatInputMenu.DrawBackdrop）、F9（GroupDialogueMenu.draw）、
   群聊中心（GroupDialogueHubMenu.draw）**三处都调** MenuSkinDrawing.DrawScrim，
   强度是同一个常量 Color.Black * MenuSkinRules.ScrimAlpha。
   改前 F8 是 Color.Black * 0.42f，而 F9 与中心完全没有遮罩 —— 那层差异是
   「三个界面不像一家人」里最容易被忽略的一条。数值按 C# 逐字写：
   MenuSkinRules.cs:69 ScrimAlpha = 0.28f → rgba(0,0,0,.28)。 */
.stage.f8::before, .stage.f9::before, .stage.hub::before {
  content: ""; position: absolute; inset: 0; background: rgba(0,0,0,.28);
}

/* 游戏字体近似：字号 17.5px 来自 bubble-f9.png 实测的中文全角字宽。
   line-height 取 21px ≈ 字形墨迹高：游戏用 DrawString 从给定 y **向下**画字，
   所以行框不能比字形高太多，否则整行文字会整体下沉、压到卡片或气泡边框上。 */
.g { font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif; font-size: 17.5px; line-height: 21px; }
/* 游戏里提示行、卡片状态行用的也是同一个 Game1.smallFont，所以不缩小字号；
   .g-sm 只是语义标记，样式与 .g 完全一致。 */
.g-sm { font-size: 17.5px; line-height: 21px; }

/* isolation 把元素的混合限制在自身，不影响下层场景 */
.nine { position: absolute; isolation: isolate; }
.nine > .fill { position: absolute; inset: 0; }
.abs { position: absolute; }
.nowrap { white-space: nowrap; }

.guide { position: absolute; border: 1px dashed rgba(255,255,255,.55); pointer-events: none; }
.guide > b { position: absolute; left: 0; top: -15px; padding: 0 4px; color: #0d0f14; background: rgba(255,255,255,.72); font-size: 10px; line-height: 14px; font-weight: 600; white-space: nowrap; }

/* 气泡：复用回放页的 .bubble / .bubble-frame 语义（group_dialogue_review_page.py:345-352）
   ⚠ 这两行必须与 ui_preview_redesign_page.py 的 .bubble-frame 逐字一致（两页对比时以本页观感为准）。

   ⚠⚠ 装饰必须挂在 stage 上，不能 append 进气泡元素（2026-09-20 修，别再放回去）：
   气泡元素带 tint 用的 feColorMatrix（见 tintFilter），而 CSS filter 作用于**整棵子树** ——
   装饰一旦成为它的后代，绿色茎叶会被气泡 tint 逐通道乘成暗紫红
   （实测 Sophia：叶 #7ea466 → #341c22，茎 #779658 → #31191d，六类元素全部偏离数据）。
   所以几何改由 drawBubble 按气泡 bounds 显式给出，与原来的 padding-box inset -34px 等价：
     left = bounds.x - 14, top = bounds.y - 14, width = bounds.w + 28, height = bounds.h + 28

   -34 的来历（换算等价，勿改数）：气泡是 border-box + 20px 边框的九宫格，padding box 比气泡矩形
   内缩 20px；characterFrameSvg 又把线条画在自己的 (14,14)-(14+w,14+h)。取 -34 时
   frame = (w+28)×(h+28)，与 SVG 的 viewBox 完全吻合 → SVG 1:1，装饰沿气泡边缘一圈。

   z-index 5：气泡 .nine 无 z-index（redesign 页为 4），文字层是 6/7 —— 装饰贴在气泡之上、文字之下。

   ⚠ 教训（2026-09-20，两个方向都错过一次，别再反复）：
   · 写成 -14（且漏掉 svg 的 width/height:100%）→ 装饰整圈偏右下 20px；
   · 写成 -15 → frame 比 viewBox 小，SVG 被**非等比压扁**（实测横向 91%、纵向 66%），
     装饰缩在气泡里 —— 那是渲染错误，不是"观感基线"；
   · 判据是游戏：`ChatBubbleDrawing.cs` 的注释原文是「装饰边框贴在气泡外侧一圈」，
     游戏截图 artifacts/visual-tests/bubble-f9-v1/bubble-f9.png 里装饰也确实探到气泡外。 */
.bubble-box { position: absolute; }
.bubble-frame { position: absolute; z-index: 5; pointer-events: none; user-select: none; line-height: 0; }
.bubble-frame svg { display: block; width: 100%; height: 100%; overflow: visible; image-rendering: pixelated; }
.bubble-badge { position: absolute; width: 24px; height: 24px; }
.bubble-badge svg { width: 24px; height: 24px; display: block; image-rendering: pixelated; }
.bubble-line { position: absolute; white-space: pre; }
.bubble-name { position: absolute; white-space: pre; }

.notes { margin-top: 30px; display: grid; gap: 18px; }
.card { border: 1px solid var(--line); border-radius: 6px; background: var(--surface); padding: 18px 20px; }
.card h2 { margin: 0 0 12px; font-size: .86rem; font-weight: 600; color: var(--soft); }
.card h3 { margin: 16px 0 8px; font-size: .76rem; font-weight: 600; color: var(--muted); }
.card p { margin: 0 0 10px; color: var(--muted); font-size: .74rem; line-height: 1.85; }
table { width: 100%; border-collapse: collapse; font-size: .7rem; }
th, td { padding: 6px 9px; border-bottom: 1px solid #2c313c; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 500; white-space: nowrap; }
td code, .card code { color: #d8c9a0; font-family: ui-monospace, Consolas, monospace; font-size: .68rem; }
ul.plain { margin: 0; padding-left: 18px; color: var(--muted); font-size: .74rem; line-height: 1.9; }
ul.plain b { color: #f0b58a; font-weight: 600; }
.flag { color: #f0b58a; font-weight: 700; }
/* 表格里标「已确证真实值」的单元格（与 .flag 的「仍是近似」对照） */
.done { color: #9ccf7a; font-weight: 700; }
</style>
</head>
<body data-page="ui-preview">
<main class="page">
  <header>
    <div class="eyebrow">Bridge / UI Preview</div>
    <h1>游戏内聊天界面 · 浏览器复刻稿</h1>
    <p class="subtitle">
      三个界面的整体外观复刻：<b>F8 私聊</b>、<b>F9 群聊</b>、<b>群聊中心（邀约列表）</b>。
      几何与配色来自 <code>smapi/</code> 下的布局规则类，气泡渲染复用群聊回放页的
      <code>characterFrameSvg</code>。原版贴图（输入框、菜单九宫格）已按真实 PNG 内联，
      不再靠截图反推；带 <span class="flag">⚠</span> 的仍是近似值或尚未查明，请以页面底部清单为准与实机核对。
    </p>
  </header>

  <div class="toolbar">
    <div class="field">
      <span>界面</span>
      <div class="seg" id="seg-view" role="group" aria-label="界面切换">
        <button type="button" data-view="chat">F8 · 私聊（ChatInputMenu）</button>
        <button type="button" data-view="group">F9 · 群聊（GroupDialogueMenu）</button>
        <button type="button" data-view="hub">群聊中心（GroupDialogueHubMenu）</button>
      </div>
    </div>
    <div class="field">
      <span>窗口尺寸（UI 视口）</span>
      <div class="seg" id="seg-size" role="group" aria-label="窗口尺寸切换">
        <button type="button" data-size="1280x720">1280 × 720</button>
        <button type="button" data-size="1600x900">1600 × 900</button>
        <button type="button" data-size="1920x1080">1920 × 1080</button>
        <button type="button" data-size="1024x600">1024 × 600</button>
      </div>
    </div>
    <div class="field">
      <span>叠加</span>
      <label class="check"><input type="checkbox" id="toggle-guides"> 显示布局参考线（矩形来自规则类）</label>
    </div>
    <div class="toolbar-note">
      舞台按容器宽度自动缩放，内部坐标始终是游戏像素<br>
      <span id="scale-readout"></span>
    </div>
  </div>

  <div class="statusbar" id="statusbar"></div>
  <div class="stage-wrap" id="stage-wrap"><div class="stage" id="stage"></div></div>

  <section class="notes">
    <div class="card">
      <h2>本稿复刻了哪些部分</h2>
      <table>
        <thead><tr><th>界面</th><th>组成部分</th><th>几何来源</th></tr></thead>
        <tbody>
          <tr>
            <td>F8 私聊</td>
            <td>面板 + 全屏压暗底、标题带（角色强调色竖条 + 「和 X 聊聊」+ 好感度状态字 + 发丝分隔线）、
                消息区气泡（玩家靠右 / NPC 靠左带徽章与装饰边框）、
                右侧角色面板（立绘位、名字、好感度、好感度条）、底部输入框与四个按钮、消息区提示行。
                <b>一点是实现的真实样子，不是本稿省略</b>：720p 下消息区只放得下一条消息，
                其余要靠滚动才能看到（<code>ChatTextLayoutRules.SelectLatestThatFit</code> 的取窗逻辑）；
                换到 1920×1080 就能看到玩家与 NPC 各一条。</td>
            <td><code>ChatLayoutRules.Calculate</code>、<code>ChatInputMenu.draw</code>、
                <code>MenuSkinDrawing.DrawTitleBand</code></td>
          </tr>
          <tr>
            <td>F9 群聊</td>
            <td>面板、标题、参与者条、消息区气泡（含同角色重复发言的构图轮换）、
                输入框与发送 / 重试 / 关闭按钮、底部提示行</td>
            <td><code>GroupDialogueLayoutRules.Calculate</code>、<code>GroupDialogueMenu.draw</code></td>
          </tr>
          <tr>
            <td>群聊中心</td>
            <td>面板、标题、四张邀约卡（标题+参与者 / 主题 / 状态）、卡上的接受·稍后·忽略按钮、关闭按钮、底部提示行。
                卡片第三行的「状态」会压到卡片底边框上——这是游戏原样：实机截图
                <code>artifacts/visual-tests/20260910-group-hub-r11/group-hub.png</code>
                里同样如此（文字 y=row+66、卡片高 92 与 12px 边框内沿 row+80 相撞）。</td>
            <td><code>GroupDialogueHubLayoutRules.Calculate</code>、<code>GroupDialogueHubMenu.draw</code>、
                <code>GroupInvitationActionLayoutRules.cs:15-67</code></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>关键常量与出处（页面里的每个数字都按这些写）</h2>
      <table>
        <thead><tr><th>量</th><th>值</th><th>出处</th></tr></thead>
        <tbody>
          <tr><td>面板安全边距</td><td>24</td><td><code>MenuPanelRules.cs:17</code> SafeMargin</td></tr>
          <tr><td>面板居中</td><td>floorOriginAtZero：群聊/中心 true，私聊 false</td><td><code>MenuPanelRules.cs:26-52</code></td></tr>
          <tr><td>私聊面板</td><td>w=clamp(视口宽×0.68, min(760,可用), 可用)；h=clamp(视口高×0.55, min(420,可用), 可用)</td><td><code>ChatLayoutRules.cs:43-60</code></td></tr>
          <tr><td>私聊 header / footer</td><td>header 高 min(92, max(48, h/4))；footer 高 min(112, max(72, h/3))，贴底</td><td><code>ChatLayoutRules.cs:62-71</code></td></tr>
          <tr><td>私聊消息区 / 角色面板</td><td>消息区高 max(40, footer.Y-header.Bottom-16)；宽≥240+280+8 时右侧开 280×min(112,高) 的角色面板</td><td><code>ChatLayoutRules.cs:72-93</code></td></tr>
          <tr><td>私聊按钮</td><td>footer 宽≥600 → gap 8，发送 96、找话题 128、物品 104、结束 96，全部同高贴底</td><td><code>ChatLayoutRules.cs:95-130</code></td></tr>
          <tr><td>私聊 header 画不画</td><td>两个开关都返回 true（2026-09-20 外壳重构后）</td><td><code>ChatLayoutRules.cs:188,191</code></td></tr>
          <tr><td>私聊标题带</td><td>竖条 <code>(header.X+12, header.Y+12, 4, 20)</code> 取角色强调色（<code>AccentFor</code>，查不到角色回退默认紫 <code>(176,146,242)</code>）；标题 <code>(header.X+24, header.Y+9)</code> 走 <code>Ink</code>；状态字 <code>(header.X+40+⌈标题宽⌉, header.Y+11)</code> 走 <code>InkSoft</code>；发丝线 <code>(header.X+12, header.Bottom-14, header.W-24, 2)</code>，色 <code>(150,96,48)×0.55f</code> ——
              ⚠ 那是 XNA 的预乘写法（RGB 与 alpha 一起乘），实际是 <code>Color(82,52,26,140)</code>，
              网页上的等价写法是 <code>rgba(82,52,26,140/255)</code>（见页面里 <code>RULE_COLOR_CSS</code> 的推导）</td><td><code>MenuSkinDrawing.DrawTitleBand</code>、<code>MenuSkinRules.cs:71-123</code>（令牌 TitleBarInset 12 / TitleBarWidth 4 / TitleBarHeight 20 / TitleTextGap 12 / StatusTextGap 16 / TitleTextOffsetY −3 / StatusTextOffsetY −1 / RuleInset 12 / RuleBottomOffset 14 / RuleHeight 2、Ink / InkSoft / RuleColor）</td></tr>
          <tr><td>三个界面的遮罩</td><td>三处都画整屏 <code>Color.Black * ScrimAlpha</code>，实测把底下的游戏画面压暗到 72%（改前 F8 是 0.42f、F9 与中心<b>完全没有</b>遮罩）</td><td><code>MenuSkinDrawing.DrawScrim</code>、<code>MenuSkinRules.cs:69</code>（ScrimAlpha = 0.28f）；调用点 <code>ChatInputMenu.cs:635</code>、<code>GroupDialogueMenu.cs:162</code>、<code>GroupDialogueHubMenu.cs:119</code></td></tr>
          <tr><td>标题带的强调色来源</td><td>角色强调色与气泡、徽章同一份数据：<code>NpcBubbleStyle.Accent</code>（由 <code>npc_bubble_elements.py</code> 的 <code>palette.accent</code> 导出）。Sophia = <code>#f292d2</code></td><td><code>MenuSkinDrawing.AccentFor</code> / <code>NpcBubbleStyle.cs:11-22,54</code></td></tr>
          <tr><td>群聊面板</td><td>w=min(1120, max(680, 视口宽-48))；h=min(720, max(430, 视口高-48))</td><td><code>GroupDialogueLayoutRules.cs:32-35</code></td></tr>
          <tr><td>群聊 header / footer</td><td>header 高 min(118, 面板高)；footer 高 min(104, 面板高) 贴底、左右内缩 20</td><td><code>GroupDialogueLayoutRules.cs:42-44</code></td></tr>
          <tr><td>群聊参与者条</td><td>(header.X+20, header.Bottom-48, header.W-40, min(32, header.H-20))</td><td><code>GroupDialogueLayoutRules.cs:45-49</code></td></tr>
          <tr><td>群聊消息区</td><td>(panel.X+20, header.Bottom, panel.W-40, footer.Y-header.Bottom-12)，一次最多 10 条</td><td><code>GroupDialogueLayoutRules.cs:28,50-54</code></td></tr>
          <tr><td>群聊按钮</td><td>发送 / 重试 / 关闭 各 88 宽、gap 8，贴 footer 右端</td><td><code>GroupDialogueLayoutRules.cs:56-66</code></td></tr>
          <tr><td>群聊标题 / 参与者文字</td><td>标题走与私聊<b>同一句</b> <code>DrawTitleBand(layout.Header, "线上多人对话", null, AccentFor(participants[0].NpcId))</code> → 竖条 <code>(header.X+12, header.Y+12, 4, 20)</code>、标题 <code>(header.X+24, header.Y+9)</code>、发丝线 <code>(header.X+12, header.Bottom-14, header.W-24, 2)</code>；参与者行 <code>(participantStrip.X, participantStrip.Y)</code> 走 <code>InkSoft</code></td><td><code>GroupDialogueMenu.cs:170-176</code>、<code>MenuSkinDrawing.DrawTitleBand</code>（改前标题只在 <code>(header.X+12, header.Y+10)</code> 一行裸文字）</td></tr>
          <tr><td>群聊底部提示</td><td>(messageArea.X+12, messageArea.Bottom-28)</td><td><code>GroupDialogueMenu.draw</code>（提示行分支）</td></tr>
          <tr><td>推送气泡的起点</td><td>左 = messageArea.X+12，右 = messageArea.Right-12，首条 y = messageArea.Y+12</td><td><code>GroupDialogueMenu.draw</code>（bubbleLeft / bubbleRight）</td></tr>
          <tr><td>中心面板</td><td>w=min(1080, max(680, 视口宽-48))；h=min(680, max(440, 视口高-48))</td><td><code>GroupDialogueHubLayoutRules.cs:15-16</code></td></tr>
          <tr><td>中心标题 / 首行 / 行距</td><td>标题同样走 <code>DrawTitleBand</code>，header 是 <code>new Rectangle(panel.X, panel.Y, panel.W, HubTitleBandHeight = 74)</code> → 竖条 <code>(panel.X+12, panel.Y+12, 4, 20)</code>、标题 <code>(panel.X+24, panel.Y+9)</code>、发丝线 <code>(panel.X+12, panel.Y+60, panel.W-24, 2)</code>（74 − 14）；首行 y=panel.Y+94；每行 92 高、步进 104</td><td><code>GroupDialogueHubMenu.cs:126-131</code>、<code>MenuSkinRules.cs:237</code>（改前标题只在 <code>(panel.X+32, panel.Y+24)</code> 一行裸文字）</td></tr>
          <tr><td>中心卡片文字</td><td>(row.X+18, row.Y+14/42/66)：标题·参与者为黑、主题为 DarkSlateGray、状态为 DimGray</td><td><code>GroupDialogueHubMenu.draw</code></td></tr>
          <tr><td>中心按钮</td><td>接受 / 稍后 / 忽略 各 64×52、gap 6、行长 18 处对齐右端；关闭 148×56 贴右下</td><td><code>GroupInvitationActionLayoutRules.cs:15-18</code>、<code>GroupDialogueHubLayoutRules.cs:26-29</code></td></tr>
          <tr><td>中心底部提示 / 空态</td><td>hint (panel.X+32, panel.Bottom-112)；空态 (panel.X+40, panel.Y+94)</td><td><code>GroupDialogueHubMenu.draw</code></td></tr>
          <tr><td>最多少张邀约卡</td><td>4</td><td><code>GroupInvitationRules.cs:18</code> MaxVisibleInvitations</td></tr>
          <tr><td>气泡内边距 / 行间 / 间距 / 安全边距 / 最小宽</td><td>12 / 4 / 20 / 8 / 180</td><td><code>ChatBubbleDrawing.cs:20,23,29,32,35</code></td></tr>
          <tr><td>气泡换行宽 / 高度</td><td>ContentWidth = max(80, 可用宽-24-8)；高 = 24 + LineSpacing + 4 + n×LineSpacing + (n-1)×4</td><td><code>ChatBubbleDrawing.ContentWidth / MeasureHeight</code></td></tr>
          <tr><td>气泡宽度</td><td>clamp(ceil(文本宽+24), min(180, 可用宽), 可用宽)</td><td><code>ChatBubbleDrawing.Draw</code>（宽度 clamp）</td></tr>
          <tr><td>玩家 / NPC 兜底气泡色</td><td>(226,239,246) / (239,231,244) —— 这是**设计色**（最终色）；两者走未着色面板 <code>Maps\MenuTilesUncolored</code> 的同一九宫格，tint 由 <code>ToPanelTint</code> 按基色 (248,248,248) 反推为 (232,246,253) / (246,238,251)，回乘即还原设计色</td><td><code>ChatBubbleDrawing.cs:50-60,178-193</code></td></tr>
          <tr><td>角色气泡色</td><td>46 个角色各一份配色，<code>palette.bubble</code> 是**设计色**（回放页直接铺的最终色）；画进彩色面板前按基色 <code>#fdbc6e</code> 反推 <code>tint = 设计色 × 255 ÷ 基色</code>，回乘即还原设计色（Abigail (65,44,109) → tint (66,60,253)）；设计色直接当 tint 会再乘一次木纹 → (64,32,47)，整体暗一档</td><td><code>npc_bubble_tint.py</code>（与 C# 导出、<code>/test/ui-redesign</code> 共用同一份公式）</td></tr>
          <tr><td>深色气泡上的正文色</td><td>(243,240,252)</td><td><code>ChatBubbleDrawing.DarkBubbleText</code></td></tr>
          <tr><td>说话人文字色</td><td>玩家 DarkSlateBlue；NPC 用该角色的 Accent</td><td><code>ChatBubbleDrawing.Draw</code>（说话人 DrawString）</td></tr>
          <tr><td>装饰边框外扩</td><td>Pad = 14；三套构图按 (发言次序 + kind 字符码和) % 3 轮换</td><td><code>NpcBubbleFrame.cs:21,308-317</code></td></tr>
          <tr><td>换行方式</td><td>逐**字符**断行（不按词），超宽即换行</td><td><code>ChatTextLayoutRules.cs:8-42</code></td></tr>
          <tr><td>角色面板底色 / 立绘</td><td>drawTextureBox(Color(248,240,224))；立绘 64×64，外框再放大 6</td><td><code>ChatInputMenu.DrawProfile</code></td></tr>
          <tr><td>好感度条</td><td>高 10、底 (206,195,180)、填充 (181,137,191)，按 心数/10 比例</td><td><code>ChatInputMenu.DrawProfile</code>（好感度条）</td></tr>
          <tr><td>四个按钮的 tint</td><td>发送 (235,246,236)、找话题 (239,231,244)、物品 (235,240,246)、结束 (247,232,227)</td><td><code>ChatInputMenu.DrawFooter</code></td></tr>
          <tr><td>按钮绘制</td><td>drawTextureBox(tint 或 Gray) + 居中标签，禁用时文字改 DimGray</td><td><code>MenuButtonDrawing.cs:22-36</code></td></tr>
          <tr><td>输入框</td><td>原版 <code>LooseSprites\textBox</code>（192×48）横向三片：左 16px + 中 (W-32) + 右 16px；源矩形高写的是 Height，H&gt;48 的部分被采样 clamp 到贴图末行 (57,54,65,66)，那片半透明冷阴影与面板底色相乘就是下半的米褐色</td><td class="done">2026-09-20 真贴图原样内联（base64），与游戏截图 y434-473 逐行同值</td></tr>
          <tr><td>菜单九宫格纹理（按钮 / 气泡 / F9 / Hub）</td><td><code>Maps\MenuTiles</code> 的 (0,256,60,60) 切 20px：四角 20×20 原样、四边拉伸、中心拉伸到 (w-40)×(h-40)；投影是同一套再画一遍、黑色 40%、整体偏移 (-8,+8)</td><td class="done">2026-09-20 真贴图原样内联，与游戏截图面板/按钮逐像素同值</td></tr>
          <tr><td>气泡的描边变体</td><td>同一块 (0,256,60,60)，但<b>描边像素的色相被归一到填充基准色</b>（逐像素保留亮度）。原贴图的描边是红橙色 <code>#b14e05</code>（B 通道只有 5）：白 tint 的面板/按钮是木框本色，可角色气泡的 tint 是紫红/靛蓝，描边乘完 B 通道仍 ≈2 —— 底色上就围了一圈橙红的边（实测边框 <code>rgb(73,13,2)</code> vs 填充 <code>rgb(104,32,36)</code>）</td><td class="done">2026-09-20 归一后边框恒为「底色的暗版本」：<code>rgb(52,16,18)</code>，边框÷填充 = (.50,.50,.50)；面板 / 按钮 / 凹槽仍用原版贴图</td></tr>
          <tr><td>F8 面板边框</td><td>走 <code>Game1.drawDialogueBox</code>：<b>同一张</b> <code>Maps\MenuTiles</code>，但取 (0,0) 起的 <b>64px</b> 九宫格（四角 64×64、中心另画在 (x+28,y+28)），而且<b>没有投影</b></td><td class="done">2026-09-20 真贴图原样内联；「两套九宫格的关系」已查清</td></tr>
          <tr><td>颜色合成规则</td><td>最终色 = 纹理色 × tint ÷ 255（逐通道）；页面用 <code>mix-blend-mode: multiply</code> 对真贴图做同一条乘法</td><td class="done">IClickableMenu.drawTextureBox / Game1.drawDialogueBox</td></tr>
          <tr><td>游戏字体行高</td><td>LineSpacing ≈ 28px；中文全角字宽 ≈ 17.5px</td><td class="flag">⚠ 由 bubble-f9.png 三个单行气泡高度同为 84px 反推</td></tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>不确定 / 与游戏可能不一致的地方（请拿去核对）</h2>
      <ul class="plain">
        <li><b>菜单九宫格纹理（已换成真贴图）</b>：三个界面底下的框都来自 <code>Maps\MenuTiles.xnb</code> ——
            按钮 / 气泡 / F9 / Hub 取 (0,256,60,60) 切 20px，F8 私聊面板取 (0,0) 起 64px 九宫格。
            <b>同图、不同源矩形</b>，这就是此前「这两套的关系未查明」的答案。贴图以 base64 内联，页面不依赖游戏目录。</li>
        <li><b>面板中央的横向明暗（已不再是手画渐变）</b>：原版是中央格被拉伸到 (w-40)×(h-40) 的结果，
            真贴图里那 20px 自带 4/8/4/4 的明暗分段，页面交给 border-image 拉伸，比例自动正确。</li>
        <li><b>输入框下半那条带（已按源码规则重画）</b>：它不是贴图里画好的第二段，也不是黑色 ——
            是 <code>TextBox.Draw</code> 的源矩形高写成 <code>Height</code> 后，H&gt;48 的采样被 clamp 到贴图末行
            <code>(57,54,65,66)</code>，那层 26% 的冷灰与暖橙面板相乘得到的米褐色。页面照抄这条规则，
            底色用同一条 rgba 叠在面板上。</li>
        <li><b>游戏字体</b>：游戏是位图 SpriteFont，本页面用系统中文黑体近似，字形宽度与断行位置会与原版有差；
            <code>LineSpacing ≈ 28</code> 是从「三个单行气泡高度都是 84px」反推的，不是从代码读到的常量。</li>
        <li><b>F8 面板边框（已查清）</b>：私聊走 <code>Game1.drawDialogueBox</code>，用 <code>Maps\MenuTiles</code> 的
            <b>64px</b> 九宫格、且<b>没有投影</b>；F9 / Hub 走 <code>IClickableMenu.drawTextureBox</code>，
            用同一张图的 (0,256,60,60) 切 <b>20px</b>、带投影。</li>
        <li><b>阴影（仍是近似）</b>：参数已按原版（偏移 (-8,+8)、<code>Color.Black * 0.4f</code>），但原版是
            「九宫格逐块再画一遍」，其中中心块还会向外放大 num/2 = 10px；页面用一层 drop-shadow 近似，
            框体轮廓一致，紧贴边框内侧那 10px 的差看不出来、但确实存在。</li>
        <li><b>F8 面板框与内容的相对位置（已知差异，未改）</b>：<code>Game1.drawDialogueBox</code> 内部把九宫格
            画在 <code>y - 64 * addedTileHeightForQuestions</code>；聊天菜单里
            <code>addedTileHeightForQuestions</code> 恒为 -1，也就是<b>整个框相对传入矩形下移 64px</b>
            （Game1.cs:15927-15943）。页面按 <code>layout.Panel</code> 直接画，所以实机里输入框几乎贴到面板底边，
            页面上则留了 24px 的安全边距。要看实机那种紧凑感就得把框下移 64px，但那会牵动三个界面的所有坐标，
            本次未改。</li>
        <li><b>面板框的底边位置（同上一条的延伸，未查明）</b>：实机截图量到面板可见底边在 y=553、
            顶边图案在 y=230，两个数无法用「传入矩形 + 64px 偏移」同时解释；可能与 title-safe 裁剪有关，
            没有继续深挖。贴图本身的边框段已逐段对齐。</li>
        <li><b>输入框下半的合成方式（仍是近似）</b>：浏览器用 sRGB 的 alpha 合成，游戏由 GPU 在
            clamp 采样后混合，理论上同一公式；实测色阶有 ±1 的舍入偏差。</li>
        <li><b>光标</b>：原版是 500ms 周期闪烁的 4×32 竖条（<code>Rectangle(X+16+文字宽+2, Y+8, 4, 32)</code>），
            页面画静态不闪烁版本，位置取空文本时。</li>
        <li><b>NPC 立绘</b>：页面没有游戏素材，角色面板里的 64×64 位置用角色徽章占位并标注。</li>
        <li><b>滚动条</b>：F8 在消息超出时才画（<code>ChatInputMenu.UpdateScrollBar / DrawScrollBar</code>）；示例消息放得下，所以看不到它。</li>
        <li><b>示例文案</b>：三个界面的对话与邀约卡都是本页面编的示例，只有<em>结构</em>来自代码；
            邀约卡的标题取自 <code>GroupInvitationThemes.cs</code> 的真实主题名。</li>
        <li><b>气泡间距</b>：代码里 <code>Gap = NpcBubbleFrame.Pad + 6 = 20</code>（<code>ChatBubbleDrawing.cs:29</code>），
            但 2026-09-20 那张 F9 截图量出来相邻气泡顶部间距只有约 12px（气泡高 84 + 间距 8）。
            页面按<em>代码</em>的 20 画，若实机看着更挤，说明截图对应的 DLL 比当前源码旧。</li>
        <li><b>F9 的可见条数</b>：代码是「最多 10 条」+「画到底部就 break」两条规则，页面照抄；
            但真实游戏里超出时不会滚动，只能靠继续说话推进。</li>
        <li><b>视口取值</b>：游戏取 <code>Game1.uiViewport</code>（<code>MenuViewportRules.cs:7-26</code>），
            页面把所选分辨率直接当作 UI 视口，未复刻 zoom / UI 缩放。</li>
      </ul>
    </div>
  </section>
</main>

<script id="ui-preview-data" type="application/json">__DATA__</script>
<script>
(() => {
  const DATA = JSON.parse(document.getElementById("ui-preview-data").textContent);
  const NPC_STYLES = DATA.styles;
  const SPEAKER_GLYPHS = DATA.glyphs;
  const CHARACTER_ORNAMENTS = DATA.ornaments;
  const NPC_ALIASES = DATA.aliases;

  const canonicalNpcId = (id) => Object.hasOwn(NPC_ALIASES, id) ? NPC_ALIASES[id] : id;
  const ornamentFor = (id) => Object.hasOwn(CHARACTER_ORNAMENTS, canonicalNpcId(id)) ? CHARACTER_ORNAMENTS[canonicalNpcId(id)] : null;
  const glyphFor = (id) => Object.hasOwn(SPEAKER_GLYPHS, canonicalNpcId(id)) ? SPEAKER_GLYPHS[canonicalNpcId(id)] : "";
  const styleFor = (id) => Object.hasOwn(NPC_STYLES, canonicalNpcId(id))
    ? NPC_STYLES[canonicalNpcId(id)]
    : { icon: "•", tone: "参与者", className: "guest", accent: "#a990ff", accentSoft: "#79d9db", bubble: "rgb(239,231,244)", border: "#576246" };

  // ── 回放页那套装饰边框（group_dialogue_review_page.py 的 _CHARACTER_FRAME_SCRIPT，原样复用）
__FRAME_SCRIPT__

  // ═══════════════════════════════════════════════════════════════════════
  // 原版贴图（base64 内联，页面自包含，不依赖游戏目录）
  //
  // 2026-09-20：这三块从本机游戏解包目录（StardewXnbHack 1.1.2 的只读产物）原样裁出，
  // 替换掉此前「按截图分四段反推」的色值。真伪由游戏内截图
  // artifacts/visual-tests/chat-bubble-v1/chat-bubble.png 逐像素交叉验证：
  //   · MenuTiles (0,276,20,20) 的横向 4px 段 (133,54,5)/(220,123,5)/(177,78,5)
  //     与截图面板左边缘 x221-236 完全同值；
  //   · textBox 的 4/4/32/4 行结构与截图输入框 y434-473 逐行同值。
  //
  //   textBox       ← LooseSprites\textBox.xnb                192×48
  //   menuPanel     ← Maps\MenuTiles.xnb  (0,0,256,256)       Game1.drawDialogueBox 的 64×64 九宫格
  //   menuButton    ← Maps\MenuTiles.xnb  (0,256,60,60)       IClickableMenu.drawTextureBox 的 60×60 九宫格
  //
  // tint 的合成规则「最终色 = 纹理色 × tint ÷ 255」不变，只是现在真的对纹理做了乘法
  // （tintFilter() 的 feColorMatrix），不再用「基色 × tint」手算：
  //     · 玩家气泡 tint(226,239,246) × 面 → 截图同值
  //     · Emily   tint(35,87,78)     × 面 → 截图同值
  //     · 角色面板 tint(248,240,224) 的边框 → 截图同值
  // ═══════════════════════════════════════════════════════════════════════
  const GAME_TEX = {
    textBox: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAMAAAAAwCAYAAABHTnUeAAABHUlEQVR42u3dMWoCQRiA0VlJoaBFSpuIkFjZGhK7WOQWOYCtF/AGOUUO4AVMSkFby8BCmpQWBoKd7ewEAmKz677X/Qs2gx+z28xk4Y9eM57GD7fTeO7vv18DVFTe6c7iuWFJqDMBIACoqyx98Hj/NInnl8FhGc/PvY1Vo7Lmizs7AAgABEDdXZ36g3Z/VJivb4ZWkdLYfW0L80++sQOAAEAAcOY3gHd+yiz9f/oGAAGAAEAAIAAQAAgAAYAAQAAgABAACAAEAAIAAYAAQAAgABAACAAEAAKAcOHnAqVnLzoniFDis0HtACAAEACc/g3w9tmaFZ/8JvcEb60iJTZK7gluuScYBAACILgn+H/pvcFQZav1x7sdAAQAAqDmjpgpJCQp8OlWAAAAAElFTkSuQmCC",
    menuPanel: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAYAAABS3GwHAAAC60lEQVR42u3doU5bURjA8XMJqKFISKowy0xbJNgJINkDkG0JT4GlAlWN5gFwEzwACJIpkNCaOVQTEhSOlTN9jrgdpWztPb+fu2FhGff+892P27UhAAAAAAAAAAAAAAAAi6Z677/goNOOfsxM62wwfNdrdMmPmJIJAAFAqZZn/Q372yvJPX+39av2z3c267/fRstJKsn9KD1uf0ivp971c2UCgABAABD+63OA/Pf8Xz+m9/x32T1d1z09NTvg4Lb+68fnn8IsnxOYALgFAgFA8Bxg5vJ7/nwnoGz59fBtzwQAAYAAYNF3gPz3uPk93+fdHWehYFcXl+E1zwFMABAACADmfweYZG19NTluH/6onJbFNTzZT14b9vjwZAKAAEAAYAegwfId7ufRl2gCgABAACAAEAAIAAQAAgABgABAACAAEAAIAAQAAgABgABAACAAEAAIAAQAwfsC/aV404sl//urrX5lAoAAQABgByjKy4urwAQAAYAAwA5QkrEdwAQAAYAAwA5Q1g4QXQUmAAgABAB2gFDSS4HsACYACAAEAHaAokQ7gAkAAgABgB2gJOPf/j+ACQACAAGAHSAU9VogO4AJAAIAAYAdoCTRCmACgABAAGAHCJ4DYAKAAEAAYAewA2ACgABAAGAHaILo8wFMABAACADsAMHnA2ACgABAAGAHaOwOMPZaIBMABAACADuA5wCYACAAEADYAYL3BsUEAAGAAMAO0ADr308rl4EJAAIAAYAAQAAgABAACAAEAAIAAYAAQAAgABAACAAEAAIAAYAAQAAgABAACAAEAAIAAUAo8L1BHx+ekuPhyb4P7WqQ/PyaACAAEAA0fwcY3NZ//eri0llg6uvHBAABgABg/naAu1F63G2lx53N9Hij5aQ02f2o/h5/0vViAoAAQADwZjP/jNz+9kr8l/dwNFu+E/SunysTAAQAAoD52gFyB5221/cztbPBsDIBQAAgAAAAAAAAAAAAAAAAAAr3B6B8evCSlPuTAAAAAElFTkSuQmCC",
    menuButton: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAABFklEQVR42u3bLw7CMBTH8ZZAuAIKuZAAlhsgMBCuwRXQuwKWhAsQMAg0BksmQKJ2AMJG9gd0K7aQiq7b97ltWfI+ef2lE50UJeVPOl/hUK2viSx63hINK8B1r7Z+4zBXMzubugUa9dT+F0c10yxpwHXLsL7P6pk9nd0C6f37oepjSQOu+z78DItf8JarSgEe+81f/bOkAdc9w2U18LpWG74HLyYMGDBgwIAbuw/nUWy14TTNmDBgwIABA27sPhx/pNWGk4wJAwZskmEh3nY7zlMmDBiwSYYtR1gkkgkDBmyQ4Uja/ZZOJRMGDNgkw5fdlgkDBlydkmXnpYdj9Xm/Vy2Afi4ruKnXnJcG3LQMC/5bYkkDdql+JmI5UzeHc48AAAAASUVORK5CYII=",
  };

  /**
   * MenuTiles (0,256,60,60) —— drawTextureBox 的默认源矩形，num = 60/3 = 20。
   *
   * 按钮（MenuButtonDrawing.DrawButton）、F9 群聊面板（GroupDialogueMenu.draw）、
   * Hub 面板与卡片行（GroupDialogueHubMenu.draw）走这一套。投影 = 同一套九宫格再画一遍、
   * `Color.Black * 0.4f`、整体偏移 (-8, +8)。
   *
   * ⚠ 角色气泡不直接用这一套：它另用一份描边色相归一过的变体 BUBBLE_MENU_TEX
   * （原来那圈红边就是这块贴图的描边被深色 tint 乘出来的）；玩家与兜底气泡则换掉整块贴图，
   * 走下面那份未着色的 PLAIN_MENU_TEX（ChatBubbleDrawing.Draw 的 DrawPanel 分支）。
   */
  const MENU_TEX = {
    src: GAME_TEX.menuButton,
    slice: 20,
    shadow: "drop-shadow(-8px 8px 0 rgba(0,0,0,.4))",
  };

  /**
   * 气泡专用九宫格 —— 切法与 MENU_TEX 完全一致，只换了**描边的色相**。
   *
   * 这块贴图自带的描边是红橙色（#b14e05，饱和度 0.97、B 通道只有 5）：白 tint 的面板 /
   * 按钮是木框本色，没问题；但角色气泡的 tint 是紫红 / 靛蓝这类深色，描边的 B 通道乘完
   * 仍 ≈2 —— 于是底色上围了一圈橙红的边（截图实测：边框 rgb(73,13,2) vs 填充 rgb(104,32,36)）。
   *
   * 服务端把描边像素的色相归一到填充基准色、逐像素保留亮度（见 npc_bubble_texture.py），
   * 边框于是恒等于「底色的暗版本」，四档明暗与圆角形状一个像素没动。
   * ⚠ 只有**角色气泡**用这一份；面板 / 按钮 / 凹槽继续用 MENU_TEX，玩家与兜底气泡用
   *   PLAIN_MENU_TEX，三者别对调。
   */
  const BUBBLE_MENU_TEX = {
    src: "__BUBBLE_MENU_TEX__",
    slice: MENU_TEX.slice,
    shadow: MENU_TEX.shadow,
  };

  /**
   * 玩家 / NPC 兜底气泡的九宫格 —— Maps\MenuTilesUncolored (0,256,60,60)。
   *
   * 切法与 MENU_TEX 完全一致，换的是**整块贴图**：未着色面板是彩色 MenuTiles 的去色版，
   * alpha 轮廓逐像素相同，底板色区从 #fdbc6e 换成近白 (248,248,248)、描边也从红橙换成冷灰紫。
   *
   * 这两个气泡为什么必须换：彩色面板的基色 #fdbc6e 只有 G 188 / B 110，而玩家气泡的浅蓝
   * (226,239,246) 与兜底气泡的浅紫 (239,231,244) 在 G / B 上比基色还高（反推要 324 / 570）——
   * 乘法 tint 最多到 1.0 倍，那些颜色根本乘不出来，直接当 tint 只会被橙黄木纹染成橙棕。
   * 换成近白面板后，两个设计色反推出来的 tint 是 (232,246,253) / (246,238,251)，全在界内。
   *
   * ⚠ 只有这两个用它（ChatBubbleDrawing.cs:126-141 的 DrawPanel 分支）；角色气泡继续用
   *   彩色贴图的描边变体 BUBBLE_MENU_TEX —— 那些专属配色本来就在基准色域内。
   */
  const PLAIN_MENU_TEX = {
    src: "__PLAIN_MENU_TEX__",
    slice: MENU_TEX.slice,
    shadow: MENU_TEX.shadow,
  };

  /**
   * 上面两个设计色反推出来的 tint（ChatBubbleDrawing.cs:57,60 的
   * PlayerBubbleTint / NpcFallbackBubbleTint，公式见 :178-193）。
   */
  const PLAYER_BUBBLE_TINT = [__PLAYER_BUBBLE_TINT__];
  const NPC_FALLBACK_BUBBLE_TINT = [__NPC_FALLBACK_BUBBLE_TINT__];

  /**
   * MenuTiles (0,0,256,256) —— Game1.drawDialogueBox 的 64×64 九宫格。
   *
   * 只有 F8 私聊面板用它（ChatInputMenu.draw 里的 MenuSkinDrawing.DrawPanel），而且**没有投影**
   * （drawDialogueBox 里没有任何阴影绘制）。它与上面那套不是同一张切片 ——
   * 这正是页面前一版把「两套的关系」列为未查明的答案：同图不同源矩形。
   *
   * inner = 16：这张九宫格的每一格都在外沿留了 16px 透明（图案从 x16 起）。
   * drawDialogueBox 在四角四边之前还会把中心格单独画一份、范围比 CSS 的 fill 大
   * （Game1.cs:15924 画在 (x+28, y+28)、(w-64)×(h-64)），所以那些透明处透出的是中心格。
   * CSS 的 fill 只覆盖 padding box，补不到边框区，面板内侧会露出一圈背景色；
   * 因此额外垫一层只含中心格的内衬（见 nineSlice）。
   */
  const DIALOGUE_TEX = {
    src: GAME_TEX.menuPanel,
    slice: 64,
    inner: 16,
    shadow: null,
  };
  const GAME_BLACK = [0, 0, 0];
  const GAME_GRAY = [128, 128, 128];
  const DARK_SLATE_GRAY = [47, 79, 79];    // Color.DarkSlateGray
  const DIM_GRAY = [105, 105, 105];        // Color.DimGray
  const DARK_SLATE_BLUE = [72, 61, 139];   // Color.DarkSlateBlue
  const DARK_BUBBLE_TEXT = [243, 240, 252]; // ChatBubbleDrawing.DarkBubbleText
  const METER_BG = [206, 195, 180];        // ChatInputMenu.DrawProfile（好感度条底）
  const METER_FILL = [181, 137, 191];      // ChatInputMenu.DrawProfile（好感度条填充）
  const DEFAULT_ACCENT = [176, 146, 242];  // MenuSkinDrawing.DefaultAccent（查不到角色时的系统默认紫）

  /**
   * 标题带底部那条发丝分隔线的颜色。
   *
   * C# 是 `MenuSkinRules.RuleColor = new Color(150, 96, 48) * 0.55f`。
   * **XNA 的 `Color * float` 把 RGB 与 alpha 一起乘**（Color.cs 的 operator*）：
   * (150,96,48,255) × 0.55 → Color(82, 52, 26, 140)。
   * 而 SpriteBatch 的 AlphaBlend 是 `src = One / dst = InverseSourceAlpha`，
   * tint 又是直接乘在 1×1 白纹理（Game1.fadeToBlackRect）上的 ——
   * 于是「预乘过的颜色 + alpha 140/255」在网页上的等价写法就是下面这条 rgba。
   *
   * ⚠ 不要写成 `rgba(150,96,48,.55)` —— 那是「原色 + 55% 透明」，没有把预乘算进去：
   * 叠在 #ffc576 面板上得 rgb(197,141,80)，比 C# 的 rgb(160,117,68) 亮 37 个色阶。
   * 本页按 C# 语义实测合成色 rgb(160,118,67)，与上面的换算吻合。
   * （设计页 ui_preview_redesign_page.py 的 SKIN.rule / ruleAlpha 用的是未预乘的写法；
   * 两边对不上时以 C# 为准 —— 本页的定位是现状复刻。）
   */
  const RULE_COLOR_CSS = "rgba(82,52,26,0.549)";

  const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
  // 「纹理色 × tint ÷ 255」这条乘法现在由 tintFilter() 的 feColorMatrix 真正作用在贴图上，
  // 不再需要手算基色，所以这里不再保留 JS 版的 tint()。
  /**
   * 把 npc_bubble_elements 里的颜色写法转成 RGB 三元组。
   *
   * palette 里同时存在 `#b092f2`（hex）和 `rgba(65, 44, 109, .92)`（CSS 函数）两种写法；
   * 游戏侧用的是不透明 Color（NpcBubbleStyle.cs:47-93），所以 rgba 只取 RGB 分量。
   */
  const parseColor = (value, fallback) => {
    const text = String(value == null ? "" : value).trim();
    const hex = text.match(/^#([0-9a-fA-F]{6})$/);
    if (hex) {
      const s = hex[1];
      return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
    }
    const fn = text.match(/(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    return fn ? [Number(fn[1]), Number(fn[2]), Number(fn[3])] : fallback;
  };

  // ── 布局规则（逐条照抄 smapi/ 下的规则类） ──────────────────────────────

  // MenuPanelRules.CenteredInViewport —— smapi/MenuPanelRules.cs:26-52
  function centeredInViewport(vw, vh, pw, ph, floorOriginAtZero) {
    let x = Math.trunc((vw - pw) / 2);
    let y = Math.trunc((vh - ph) / 2);
    if (floorOriginAtZero) { x = Math.max(0, x); y = Math.max(0, y); }
    return { x, y, w: pw, h: ph };
  }

  // ChatLayoutRules.Calculate —— smapi/ChatLayoutRules.cs:31-143
  function chatLayout(vw, vh) {
    const SafeMargin = 24;            // MenuPanelRules.cs:17
    const MinimumPanelWidth = 760;    // ChatLayoutRules.cs:22
    const MinimumPanelHeight = 420;   // :23
    const FooterHeight = 112;         // :24
    const HeaderHeight = 92;          // :25
    const ActionGap = 8;              // :26
    const ProfileWidth = 280;         // :27
    const ProfileHeight = 112;        // :28
    const MinimumConversationWidth = 240; // :29

    const availableWidth = Math.max(1, vw - SafeMargin * 2);   // :43
    const availableHeight = Math.max(1, vh - SafeMargin * 2);  // :44
    const minimumWidth = Math.min(MinimumPanelWidth, availableWidth);   // :45
    const minimumHeight = Math.min(MinimumPanelHeight, availableHeight); // :46
    const panelWidth = clamp(Math.round(vw * 0.68), minimumWidth, availableWidth);   // :47-50
    const panelHeight = clamp(Math.round(vh * 0.55), minimumHeight, availableHeight); // :51-54
    const panel = centeredInViewport(vw, vh, panelWidth, panelHeight, false);         // :55-60

    const header = {                                   // :62-66
      x: panel.x + SafeMargin, y: panel.y + SafeMargin,
      w: panel.w - SafeMargin * 2,
      h: Math.min(HeaderHeight, Math.max(48, Math.trunc(panel.h / 4))),
    };
    const footer = {                                   // :67-71
      x: panel.x + SafeMargin,
      y: panel.y + panel.h - SafeMargin - Math.min(FooterHeight, Math.max(72, Math.trunc(panel.h / 3))),
      w: panel.w - SafeMargin * 2,
      h: Math.min(FooterHeight, Math.max(72, Math.trunc(panel.h / 3))),
    };
    const messageArea = {                              // :72-76
      x: panel.x + SafeMargin, y: header.y + header.h + ActionGap,
      w: panel.w - SafeMargin * 2,
      h: Math.max(40, footer.y - (header.y + header.h) - ActionGap * 2),
    };
    const showProfile = messageArea.w >= MinimumConversationWidth + ProfileWidth + ActionGap; // :78-79
    const profilePanel = showProfile ? {               // :80-86
      x: messageArea.x + messageArea.w - ProfileWidth, y: messageArea.y,
      w: ProfileWidth, h: Math.min(ProfileHeight, messageArea.h),
    } : null;
    const conversationArea = {                         // :87-93
      x: messageArea.x, y: messageArea.y,
      w: showProfile ? messageArea.w - ProfileWidth - ActionGap : messageArea.w,
      h: messageArea.h,
    };

    const compactActions = footer.w < 600;         // :95
    const veryCompactActions = footer.w < 420;     // :96
    const buttonGap = veryCompactActions ? 4 : compactActions ? 6 : ActionGap;  // :97-101
    const sendWidth = veryCompactActions ? 56 : compactActions ? 72 : 96;       // :102
    const topicWidth = veryCompactActions ? 72 : compactActions ? 96 : 128;     // :103
    const inventoryWidth = veryCompactActions ? 62 : compactActions ? 84 : 104; // :104
    const closeWidth = veryCompactActions ? 56 : compactActions ? 72 : 96;      // :105
    const closeButton = { x: footer.x + footer.w - closeWidth, y: footer.y, w: closeWidth, h: footer.h };      // :106-110
    const inventoryButton = { x: closeButton.x - buttonGap - inventoryWidth, y: footer.y, w: inventoryWidth, h: footer.h }; // :111-115
    const topicButton = { x: inventoryButton.x - buttonGap - topicWidth, y: footer.y, w: topicWidth, h: footer.h };          // :116-120
    const sendButton = { x: topicButton.x - buttonGap - sendWidth, y: footer.y, w: sendWidth, h: footer.h };                  // :121-125
    const inputBox = {                                 // :126-130
      x: footer.x, y: footer.y,
      w: Math.max(120, sendButton.x - footer.x - buttonGap), h: footer.h,
    };
    return { panel, header, footer, messageArea, conversationArea, profilePanel, inputBox, sendButton, topicButton, inventoryButton, closeButton };
  }

  // GroupDialogueLayoutRules.Calculate —— smapi/GroupDialogueLayoutRules.cs:30-77
  function groupLayout(vw, vh) {
    const SafeMargin = 24;      // :17
    const FooterHeight = 104;   // :18
    const HeaderHeight = 118;   // :19
    const ActionGap = 8;        // :20

    let panelWidth = Math.min(1120, Math.max(680, vw - SafeMargin * 2));   // :32
    let panelHeight = Math.min(720, Math.max(430, vh - SafeMargin * 2));   // :33
    panelWidth = Math.min(panelWidth, Math.max(1, vw - SafeMargin * 2));   // :34
    panelHeight = Math.min(panelHeight, Math.max(1, vh - SafeMargin * 2)); // :35
    const panel = centeredInViewport(vw, vh, panelWidth, panelHeight, true); // :36-41

    const header = { x: panel.x, y: panel.y, w: panel.w, h: Math.min(HeaderHeight, panel.h) }; // :42
    const footerY = Math.max(header.y + header.h, panel.y + panel.h - Math.min(FooterHeight, panel.h)); // :43
    const footer = { x: panel.x + 20, y: footerY, w: Math.max(1, panel.w - 40), h: Math.max(1, panel.y + panel.h - footerY) }; // :44
    const participantStrip = {                      // :45-49
      x: header.x + 20, y: header.y + header.h - 48, w: Math.max(1, header.w - 40),
      h: Math.min(32, Math.max(1, header.h - 20)),
    };
    const messageArea = {                           // :50-54
      x: panel.x + 20, y: header.y + header.h, w: Math.max(1, panel.w - 40),
      h: Math.max(1, footer.y - (header.y + header.h) - 12),
    };
    const closeWidth = 88, retryWidth = 88, sendWidth = 88;  // :56-58
    const closeButton = { x: footer.x + footer.w - closeWidth, y: footer.y, w: closeWidth, h: footer.h };              // :59
    const retryButton = { x: closeButton.x - ActionGap - retryWidth, y: footer.y, w: retryWidth, h: footer.h };        // :60
    const sendButton = { x: retryButton.x - ActionGap - sendWidth, y: footer.y, w: sendWidth, h: footer.h };           // :61
    const inputBox = { x: footer.x, y: footer.y, w: Math.max(120, sendButton.x - footer.x - ActionGap), h: footer.h }; // :62-66
    return { panel, header, footer, participantStrip, messageArea, inputBox, sendButton, retryButton, closeButton };
  }

  // GroupDialogueHubLayoutRules.Calculate —— smapi/GroupDialogueHubLayoutRules.cs:13-30
  function hubLayout(vw, vh) {
    const SafeMargin = 24;  // :11
    let panelWidth = Math.min(1080, Math.max(680, vw - SafeMargin * 2));   // :15
    let panelHeight = Math.min(680, Math.max(440, vh - SafeMargin * 2));   // :16
    panelWidth = Math.min(panelWidth, Math.max(1, vw - SafeMargin * 2));   // :17
    panelHeight = Math.min(panelHeight, Math.max(1, vh - SafeMargin * 2)); // :18
    const panel = centeredInViewport(vw, vh, panelWidth, panelHeight, true); // :19-24
    const buttonY = panel.y + panel.h - 76;                                  // :26
    return { panel, closeButton: { x: panel.x + panel.w - 180, y: buttonY, w: 148, h: 56 } };  // :27-30
  }

  // MenuSkinRules.HubTitleBandHeight —— smapi/MenuSkinRules.cs:237
  // 群聊中心标题带的固定高度；C# 用它当 DrawTitleBand 的 header 矩形：
  //   new Rectangle(panel.X, panel.Y, panel.Width, HubTitleBandHeight)
  // 分隔线因此落在 panel.Y + 74 - 14 = panel.Y + 60（TitleRule 的 RuleBottomOffset）。
  // listTop 与首行 y 也同值（panel.Y + 74 / panel.Y + 94），三处引用同一个数。
  const HUB_TITLE_BAND_HEIGHT = 74;

  // GroupInvitationActionLayoutRules —— smapi/GroupInvitationActionLayoutRules.cs:15-67
  const INVITATION_BUTTON = { width: 64, gap: 6, height: 52, topOffset: 18 };  // :15-18
  const actionRowX = (row) => row.x + row.w - INVITATION_BUTTON.width * 3 - INVITATION_BUTTON.gap * 2;  // :21-24
  const actionButtonAt = (row, index) => ({                                                              // :60-67
    x: actionRowX(row) + (INVITATION_BUTTON.width + INVITATION_BUTTON.gap) * index,
    y: row.y + INVITATION_BUTTON.topOffset, w: INVITATION_BUTTON.width, h: INVITATION_BUTTON.height,
  });

  // ── 文本度量 ───────────────────────────────────────────────────────────
  // ⚠ 游戏用 Game1.smallFont.MeasureString（位图字体）；网页没有同款字体，
  //   这里用 canvas 按页面实际使用的字体测量，保证「断行结果」与「DOM 渲染宽度」一致，
  //   从而不会溢出气泡。字号 17.5px 是从 bubble-f9.png 反推的中文全角字宽。
  const GAME_FONT_CSS = '17.5px "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif';
  const measureCtx = (() => {
    try {
      const ctx = document.createElement("canvas").getContext("2d");
      ctx.font = GAME_FONT_CSS;
      return ctx;
    } catch (error) {
      return null;   // 极少数环境拿不到 canvas，退回等宽估算
    }
  })();
  const measureText = (value) => {
    const text = String(value);
    if (measureCtx) return measureCtx.measureText(text).width;
    let w = 0;
    for (const ch of text) w += /[\u2E80-\uFFE6]/.test(ch) ? 17.5 : 8.75;
    return w;
  };

  // ChatTextLayoutRules.Wrap —— smapi/ChatTextLayoutRules.cs:8-42（逐字符换行）
  function wrapText(text, maxWidth) {
    const lines = [];
    for (const paragraph of String(text).replace(/\r\n/g, "\n").split("\n")) {
      let current = "";
      for (const ch of paragraph) {
        const candidate = current + ch;
        if (current.length > 0 && measureText(candidate) > maxWidth) { lines.push(current); current = ch; }
        else current = candidate;
      }
      lines.push(current);
    }
    return lines;
  }

  // ── 盒模型工具 ─────────────────────────────────────────────────────────
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);

  /** 一个绝对定位的矩形。 */
  function rectEl(parent, r, cls) {
    const el = document.createElement("div");
    el.className = "abs" + (cls ? " " + cls : "");
    el.style.left = r.x + "px";
    el.style.top = r.y + "px";
    el.style.width = r.w + "px";
    el.style.height = r.h + "px";
    parent.append(el);
    return el;
  }

  /**
   * 原版给九宫格着色：`SpriteBatch.Draw(tex, ..., tint)` 的最终色是
   * 「纹理色 × tint ÷ 255」（逐通道），alpha 不变 —— 所以贴图的透明处保持透明。
   *
   * border-image 只能原样贴图、不能着色，这里用 feColorMatrix 做同一条对角乘法：
   * 它按 sRGB 逐通道相乘、保留 alpha，透明区不会被染出一层底。
   * （试过 `::after { background: tint; mix-blend-mode: multiply }`：在 backdrop 为
   *   透明的像素上，multiply 会退化成直接画源色，于是贴图的所有透明留白变成纯 tint 色，
   *   面板外圈和角部会多出一圈白边。）
   *
   * 白色 tint 是恒等变换，直接跳过，省掉一层 filter。
   */
  const tintFilterCache = new Map();
  function tintFilter(tintColor) {
    if (!tintColor || (tintColor[0] === 255 && tintColor[1] === 255 && tintColor[2] === 255)) {
      return "";
    }
    const key = tintColor.join("-");
    const cached = tintFilterCache.get(key);
    if (cached !== undefined) {
      return cached;
    }
    const id = "tint-" + key;
    if (!document.getElementById(id)) {
      const ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");
      svg.setAttribute("width", "0");
      svg.setAttribute("height", "0");
      svg.setAttribute("aria-hidden", "true");
      svg.style.position = "absolute";
      const filter = document.createElementNS(ns, "filter");
      filter.setAttribute("id", id);
      filter.setAttribute("color-interpolation-filters", "sRGB");
      const matrix = document.createElementNS(ns, "feColorMatrix");
      matrix.setAttribute("type", "matrix");
      matrix.setAttribute("values", [
        tintColor[0] / 255, 0, 0, 0, 0,
        0, tintColor[1] / 255, 0, 0, 0,
        0, 0, tintColor[2] / 255, 0, 0,
        0, 0, 0, 1, 0,
      ].join(" "));
      filter.append(matrix);
      svg.append(filter);
      document.body.append(svg);
    }
    const value = `url(#${id})`;
    tintFilterCache.set(key, value);
    return value;
  }

  /**
   * 九宫格面板：与 IClickableMenu.drawTextureBox 逐块同构。
   *
   * 原版（IClickableMenu.cs:803-842，默认源 (0,256,60,60)、num = sourceRect.Width / 3 = 20）：
   *   四角 20×20 原样；上下边拉伸到 (w-40)×20；左右边 20×(h-40)；
   *   中心从 (x+20, y+20) 拉伸到 (w-40)×(h-40)。
   * CSS border-image 的 slice / width / stretch 语义与这套切法一一对应，所以这里
   * 直接用真实贴图切，不再用「4px 三段 + 线性渐变」近似。
   *
   * 着色走 feColorMatrix（见 tintFilter）；投影用 drop-shadow(-8px 8px) 复刻原版偏移，
   * 形状跟随贴图 alpha，而不是把一个整矩形压暗 —— 原版阴影是逐块画的，
   * 露在框外的只有边框轮廓。
   */
  function nineSlice(parent, r, tintColor, texture) {
    const tex = texture || MENU_TEX;
    const tint = tintColor || [255, 255, 255];
    const filter = [tintFilter(tint), tex.shadow].filter(Boolean).join(" ");

    // 内衬：贴图的九宫格在外沿留了 tex.inner 的透明，drawDialogueBox 会额外补一整块中心格，
    // 让它透出面色。CSS 的 fill 只到 padding box，所以这里先用同图取「中心格」铺一层底，
    // 位置缩进 tex.inner —— 外沿仍保持透明（游戏里那里确实是背景）。
    // 先 append ⇒ 在 DOM 里排在 .nine 之前 ⇒ 画在它下面。
    if (tex.inner) {
      const inner = rectEl(parent, {
        x: r.x + tex.inner,
        y: r.y + tex.inner,
        w: Math.max(0, r.w - tex.inner * 2),
        h: Math.max(0, r.h - tex.inner * 2),
      });
      inner.style.backgroundImage = `url("${tex.src}")`;
      // 3×3 里取正中那一格：图像是元素的 3 倍，50% 定位正好落在中心格
      inner.style.backgroundSize = "300% 300%";
      inner.style.backgroundPosition = "50% 50%";
      if (filter) {
        inner.style.filter = filter;
      }
    }

    const el = rectEl(parent, r, "nine");
    el.style.borderStyle = "solid";
    el.style.borderWidth = tex.slice + "px";
    el.style.borderImage = `url("${tex.src}") ${tex.slice} fill stretch`;
    if (filter) {
      el.style.filter = filter;
    }
    return el;
  }

  /** MenuButtonDrawing.DrawButton —— smapi/MenuButtonDrawing.cs:22-36 */
  function button(parent, r, label, enabled, tintColor) {
    const el = nineSlice(parent, r, enabled ? (tintColor || [255, 255, 255]) : GAME_GRAY, MENU_TEX);
    el.style.zIndex = "3";
    // 标签画在按钮之外（同级绝对定位）：原版标签是 drawTextureBox 之后单独 DrawString 的，
    // 不带投影；若放进 nineSlice 内部，会被 filter 的 drop-shadow 一起投出去。
    const text = document.createElement("div");
    text.className = "g abs";
    text.style.left = r.x + "px";
    text.style.top = (r.y + r.h / 2) + "px";
    text.style.width = r.w + "px";
    text.style.transform = "translateY(-50%)";
    text.style.textAlign = "center";
    text.style.color = rgb(enabled ? GAME_BLACK : DIM_GRAY);
    text.style.zIndex = "6";
    text.textContent = label;
    parent.append(text);
    return el;
  }

  function textAt(parent, x, y, value, color, extraClass) {
    const el = document.createElement("div");
    el.className = "g abs nowrap" + (extraClass ? " " + extraClass : "");
    el.style.left = x + "px";
    el.style.top = y + "px";
    el.style.color = rgb(color);
    el.textContent = value;
    parent.append(el);
    return el;
  }

  /**
   * 标题带：`MenuSkinDrawing.DrawTitleBand`（ChatInputMenu.DrawHeader 唯一的调用点）。
   *
   * 2026-09-20 外壳重构后 `ChatLayoutRules.ShouldDrawHeaderTitle / ShouldDrawHeaderStatus`
   * 都返回 true，实机在 header 里画四样东西；本函数逐条照 `MenuSkinRules` 的设计令牌还原：
   *
   *   竖条   MenuSkinRules.TitleBar(header)         = (header.X+12, header.Y+12, 4, 20)，取角色强调色
   *   标题   MenuSkinRules.TitleTextPosition(header)= (header.X+24, header.Y+9)，颜色 Ink = Color.Black
   *   状态字 MenuSkinRules.StatusTextPosition(...)  = (header.X+40+ceil(标题宽), header.Y+11)，InkSoft = Color.DimGray
   *   分隔线 MenuSkinRules.TitleRule(header)        = (header.X+12, header.Bottom-14, header.W-24, 2)
   *
   * 令牌数值：TitleBarInset 12 / TitleBarWidth 4 / TitleBarHeight 20 / TitleTextGap 12 /
   * StatusTextGap 16 / TitleTextOffsetY -3 / StatusTextOffsetY -1 / RuleInset 12 /
   * RuleBottomOffset 14 / RuleHeight 2（MenuSkinRules.cs:71-123）。
   *
   * ⚠ 状态字的 x 依赖**标题的实测宽度**（C# 是 `Game1.smallFont.MeasureString(title).X` 再
   * `Math.Ceiling`），所以这里用页面同一套 canvas 度量 measureText —— 与断行用的是同一把尺子。
   *
   * @param header  C# 的 layout.Header（ChatLayoutRules.Calculate 的第 62-66 行）
   * @param accent  角色强调色：MenuSkinDrawing.AccentFor(npc.Name)，与气泡、徽章同源
   */
  function titleBand(parent, header, title, status, accent) {
    const barX = header.x + 12;                                   // TitleBarInset
    const barY = header.y + 12;                                   // TitleBarInset（与 x 同值）
    const bar = rectEl(parent, { x: barX, y: barY, w: 4, h: 20 }); // TitleBarWidth / TitleBarHeight
    bar.style.background = rgb(accent);
    bar.style.zIndex = "3";
    // data-band：给自动化核对（含 /test/ui-redesign 的同一套核对）留的锚点，
    // 值就是 MenuSkinRules 里的令牌名，页面渲染不受影响。
    bar.dataset.band = "bar";

    // TitleTextPosition：横 barX + TitleTextGap(12)，纵 barY + TitleTextOffsetY(-3)
    const titleEl = textAt(parent, barX + 12, barY - 3, title, GAME_BLACK);
    titleEl.style.zIndex = "3";
    titleEl.dataset.band = "title";

    if (status) {
      // StatusTextPosition：barX + TitleTextGap(12) + ceil(标题宽) + StatusTextGap(16)，纵 barY + StatusTextOffsetY(-1)
      const statusX = barX + 12 + Math.ceil(measureText(title)) + 16;
      const statusEl = textAt(parent, statusX, barY - 1, status, DIM_GRAY, "g-sm");
      statusEl.style.zIndex = "3";
      statusEl.dataset.band = "status";
    }

    // TitleRule：距 header 左右各内缩 RuleInset(12)、底边之上 RuleBottomOffset(14)、高 RuleHeight(2)
    const rule = rectEl(parent, {
      x: header.x + 12,
      y: header.y + header.h - 14,
      w: Math.max(1, header.w - 24),
      h: 2,
    });
    rule.style.background = RULE_COLOR_CSS;
    rule.style.zIndex = "3";
    rule.dataset.band = "rule";
  }

  // ── 气泡（ChatBubbleDrawing.Draw）──
  const BUBBLE = { padding: 12, lineSpacing: 4, gap: 20, safetyMargin: 8, minWidth: 180 }; // :20,23,29,32,35

  /** ChatBubbleDrawing.MeasureHeight —— 与 smapi 侧同名方法逐行对照 */
  function measureBubbleHeight(lineCount, lineSpacingPx) {
    const n = lineCount <= 0 ? 1 : lineCount;
    return BUBBLE.padding * 2 + lineSpacingPx + BUBBLE.lineSpacing + n * lineSpacingPx + (n - 1) * BUBBLE.lineSpacing;
  }

  /** ChatBubbleDrawing.ContentWidth —— 与 smapi 侧同名方法逐行对照 */
  const contentWidthFor = (available) => Math.max(80, available - BUBBLE.padding * 2 - BUBBLE.safetyMargin);

  /**
   * 画一个气泡，返回它占用的高度（与 C# 的返回值同义）。
   *
   * @param stage       舞台元素
   * @param left/right  C# 传入的左右边界（玩家靠右对齐到 right，NPC 靠左对齐到 left）
   * @param y           气泡顶部
   * @param speaker     说话人显示名
   * @param content     正文
   * @param npcId       角色 ID（玩家传 null）
   * @param isPlayer    玩家侧
   * @param occurrence  该角色在本场第几次发言（决定装饰边框构图）
   * @param lineSpacing 游戏字体行高（⚠ 反推值，见页面底部）
   */
  function drawBubble(stage, left, right, y, speaker, content, npcId, isPlayer, occurrence, lineSpacing) {
    const availableWidth = Math.max(BUBBLE.minWidth, right - left);         // Draw 的 availableWidth
    const lines = wrapText(content, contentWidthFor(availableWidth));       // Wrap 调用来自 ChatInputMenu.DrawMessages / GroupDialogueMenu.draw
    if (lines.length === 0) return 0;
    const textWidth = Math.max(...lines.map(measureText));                  // Draw 的 textWidth
    const width = clamp(Math.ceil(textWidth + BUBBLE.padding * 2), Math.min(BUBBLE.minWidth, availableWidth), availableWidth); // Draw 的宽度 clamp
    const height = measureBubbleHeight(lines.length, lineSpacing);          // Draw 的 height
    const bounds = { x: isPlayer ? right - width : left, y, w: width, h: height };  // Draw 的 bounds

    const style = isPlayer ? null : styleFor(npcId);                        // Draw 的 style
    // 玩家与「表里没有专属配色的 NPC」走未着色面板 + 反推 tint（Draw 的 DrawPanel 分支）；
    // 角色气泡仍是彩色贴图的描边变体 + 自己的 tint（NpcBubbleStyle.Bubble 已是反推值）。
    const plain = isPlayer || !Object.hasOwn(NPC_STYLES, canonicalNpcId(npcId));
    // 角色气泡的 tint 由服务端按设计色反推（npc_bubble_tint.py，与 C# 导出同一公式）：
    // 彩色面板画的是「纹理色 × tint ÷ 255」，设计色直接当 tint 会被木纹再乘一次，
    // 结果整体暗一档（Abigail (65,44,109) → (64,32,47)）。
    const bubbleTint = isPlayer
      ? PLAYER_BUBBLE_TINT
      : (plain ? NPC_FALLBACK_BUBBLE_TINT : style.bubbleTint); // Draw 的 PlayerBubbleTint / NpcFallbackBubbleTint
    // 贴图与 tint 必须配套：未着色面板配反推 tint，彩色变体配角色 tint（见两个常量的说明）。
    const el = nineSlice(stage, bounds, bubbleTint, plain ? PLAIN_MENU_TEX : BUBBLE_MENU_TEX);
    el.dataset.bubble = npcId || "player";
    el.style.zIndex = "2";

    // 装饰边框：与回放页同一套 characterFrameSvg（NpcBubbleFrame.cs:92-174 是它的游戏内复刻）
    const ornament = decorationFor(npcId, isPlayer);
    if (ornament) {
      const frame = document.createElement("span");
      frame.className = "bubble-frame";
      frame.setAttribute("aria-hidden", "true");
      // ⚠ 挂到 stage 上，不要 append 进 el：el 带 tint 的 feColorMatrix，filter 会连带后代一起
      //   乘，绿叶会被气泡 tint 染成暗紫红（详见 .bubble-frame 的 CSS 注释）。
      //   几何按 bounds 显式给出，与原来「padding box + inset -34px」逐像素等价。
      frame.style.left = (bounds.x - 14) + "px";
      frame.style.top = (bounds.y - 14) + "px";
      frame.style.width = (bounds.w + 28) + "px";
      frame.style.height = (bounds.h + 28) + "px";
      // ⚠ 用 bounds 而不是 getBoundingClientRect：舞台整体被 transform 缩放过
      frame.innerHTML = characterFrameSvg(bounds.w, bounds.h, ornament, occurrence);
      stage.append(frame);
    }

    // 徽章（NpcBubbleStyle.CellSize = 24，ChatBubbleDrawing.Draw 的徽章分支）
    const showBadge = Boolean(style && glyphFor(npcId));
    const textLeft = bounds.x + BUBBLE.padding;                             // Draw 的 textLeft
    let speakerLeft = textLeft;                                             // Draw 的 speakerLeft
    if (showBadge) {
      const badge = document.createElement("span");
      badge.className = "bubble-badge abs";
      badge.style.left = textLeft + "px";
      badge.style.top = (bounds.y + BUBBLE.padding) + "px";
      badge.style.color = rgb(parseColor(style.accent, [255, 255, 255]));
      badge.style.zIndex = "6";
      badge.innerHTML = glyphFor(npcId);
      stage.append(badge);
      speakerLeft = textLeft + 24 + 6;                                      // Draw 的徽章让位（CellSize + 6）
    }

    // 说话人（Draw 的说话人 DrawString）
    const nameEl = document.createElement("div");
    nameEl.className = "g bubble-name";
    nameEl.style.left = speakerLeft + "px";
    nameEl.style.top = (bounds.y + BUBBLE.padding) + "px";
    nameEl.style.color = rgb(isPlayer ? DARK_SLATE_BLUE : parseColor(style.accent, [255, 255, 255]));
    nameEl.style.zIndex = "6";
    nameEl.textContent = speaker;
    stage.append(nameEl);

    // 正文（Draw 的 bodyColor 与正文循环）
    const bodyColor = (isPlayer || !style) ? GAME_BLACK : DARK_BUBBLE_TEXT;
    let lineY = bounds.y + BUBBLE.padding + lineSpacing + BUBBLE.lineSpacing; // Draw 的 lineY 起点
    for (const line of lines) {
      const lineEl = document.createElement("div");
      lineEl.className = "g bubble-line";
      lineEl.style.left = textLeft + "px";
      lineEl.style.top = lineY + "px";
      lineEl.style.color = rgb(bodyColor);
      lineEl.style.zIndex = "6";
      lineEl.textContent = line;
      stage.append(lineEl);
      lineY += lineSpacing + BUBBLE.lineSpacing;                             // Draw 的 lineY 步进
    }
    return height;
  }

  /** 玩家没有装饰边框；NPC 取 ornaments 表（回放页 ornamentFor 同义）。 */
  function decorationFor(npcId, isPlayer) {
    if (isPlayer || !npcId) return null;
    return ornamentFor(npcId);
  }

  // ── 输入框（原版 LooseSprites\textBox，ChatInputMenu 构造函数里 new TextBox、DrawFooter 里 inputBox.Draw）──
  /**
   * 与 StardewValley.Menus.TextBox.Draw 同构。
   *
   * 原版把这个 192×48 的贴图当**横向三片**用（三次 spriteBatch.Draw）：
   *   b.Draw(tex, new Rectangle(X,          Y, 16,     H), new Rectangle(0,              0, 16, H), Color.White);
   *   b.Draw(tex, new Rectangle(X + 16,     Y, W - 32, H), new Rectangle(16,             0,  4, H), Color.White);
   *   b.Draw(tex, new Rectangle(X + W - 16, Y, 16,     H), new Rectangle(tex.Width - 16, 0, 16, H), Color.White);
   *
   * 关键在于**源矩形的高度写的是 Height，而不是贴图高度 48**：
   *   · H ≤ 48 时，屏幕第 n 行采样贴图第 n 行，1:1；
   *   · H > 48 时，多出来的采样点 v > 1 被 GPU clamp 到贴图最后一行 y=47 ——
   *     那一行是 (57,54,65,66) 的半透明冷阴影，于是整个下半部被它铺满，
   *     再和下面的面板底色相乘，得到实测的米褐色 rgb(190,140,93)。
   *
   * 所以「上半浅橙 + 下半一条灰褐带」不是贴图里画好的第二段，而是这一条 clamp 规则的产物；
   * 它也不是「黑色」——是 26% 的冷灰叠在暖橙面板上。
   * 页面前一版把它近似成一整块 rgb(197,148,92)、并加了一圈 4px rgb(91,43,42) 边框，
   * 于是底部多出一条原版并不存在的深色横线（H>48 时原版那里一直是阴影）。
   *
   * 这里照抄规则：底色铺贴图 y47 行那层 rgba(57,54,65,.2588)，上半 min(48,H) 用三片式贴图盖住。
   * 中块取 slice 的 x16..175；源码取的是 x16..19 那 4px，但贴图每一行在这段内同色，
   * 横向拉伸的结果逐像素相同。
   */
  function textBox(parent, r) {
    const el = rectEl(parent, r);
    el.style.zIndex = "3";
    // 贴图只盖到 cap 的高度；再往下的部分是同一条 clamp 阴影，所以底色从 cap 下沿才开始铺。
    // 否则 cap 里那 4px 半透明阴影行会再和底色叠一次，比原版暗一档。
    const capHeight = Math.min(48, r.h);
    // 横向也只在贴图真正有阴影的列上铺：贴图末行 x0..7 与 x188..191 是透明的，
    // 游戏里那两条 clamp 后仍然是透明（透出面板），所以底色从 8px 起、到 W-4 止。
    el.style.backgroundImage =
      `linear-gradient(to bottom, rgba(0,0,0,0) 0 ${capHeight}px, rgba(57,54,65,.2588) ${capHeight}px 100%)`;
    el.style.backgroundRepeat = "no-repeat";
    el.style.backgroundSize = "calc(100% - 12px) 100%";
    el.style.backgroundPosition = "8px 0";
    const cap = document.createElement("div");
    cap.className = "abs";
    cap.style.left = "0";
    cap.style.top = "0";
    cap.style.width = "100%";
    cap.style.height = capHeight + "px";
    cap.style.borderStyle = "solid";
    cap.style.borderWidth = "0 16px";
    cap.style.borderImage = `url("${GAME_TEX.textBox}") 0 16 0 16 fill stretch`;
    el.append(cap);
    return el;
  }

  /**
   * TextBox 里的光标：原版是 `Rectangle(X + 16 + textWidth + 2, Y + 8, 4, 32)`，
   * 颜色 _textColor（ChatInputMenu.cs:93 传的 Color.Black），且按 500ms 周期闪烁。
   * 这里取空文本时的位置、用静态不闪烁的版本（截图/比对用，闪起来反而看不清）。
   */
  function caret(parent, r) {
    const el = rectEl(parent, r);
    el.style.background = rgb(GAME_BLACK);
    el.style.zIndex = "4";
    return el;
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 三个界面的示例数据（结构来自代码，文案是本稿编的示例）
  // ═══════════════════════════════════════════════════════════════════════
  const SAMPLE = {
    chat: {
      npc: "Sophia",
      hearts: 6,
      hint: "",                                     // uiHint 为空时不画（ChatInputMenu.DrawMessages 的提示行分支）
      messages: [
        { role: "npc", text: "刚从葡萄架那边回来，手上全是泥。" },
        { role: "player", text: "辛苦了，我给你带了点东西。" },
        { role: "npc", text: "……你每次都这样。先放着吧，等我把这排绑完。" },
      ],
    },
    group: {
      participants: ["Abigail", "Emily"],
      hint: "线上群聊不会传送 NPC，也不会改变他们的日程。",
      messages: [
        { role: "player", npcId: "player", text: "你们最近都在忙什么？" },
        { role: "npc", npcId: "Abigail", text: "还那样，翻翻漫画打打游戏。地里的活也没少干就是了。" },
        { role: "npc", npcId: "Emily", text: "我在挑布料的颜色，春天适合宝石色调，比冬天大胆多了。" },
        { role: "npc", npcId: "Abigail", text: "（她插了一句）那你上次那块紫色呢，留着还是用了？" },
      ],
    },
    // 标题取自 GroupInvitationThemes.cs 的真实主题表；参与者与天数为例示值
    hub: [
      { title: "闲下来的消遣", participants: ["Abigail", "Emily"], topic: "闲下来的消遣", status: "未读", expires: 12 },
      { title: "手头的活计", participants: ["Robin", "Pierre"], topic: "手头的活计", status: "进行中", expires: 14 },
      { title: "往外面跑", participants: ["Sebastian", "Sam"], topic: "往外面跑", status: "稍后处理", expires: 9 },
      { title: "好看的东西", participants: ["Leah", "Haley"], topic: "好看的东西", status: "未读", expires: 15 },
    ],
    hubHint: "选择一张邀约卡参与群聊。",
  };

  // ═══════════════════════════════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════════════════════════════
  const stage = document.getElementById("stage");
  const stageWrap = document.getElementById("stage-wrap");
  const statusbar = document.getElementById("statusbar");
  const scaleReadout = document.getElementById("scale-readout");
  const guidesToggle = document.getElementById("toggle-guides");
  const state = { view: "chat", width: 1280, height: 720, guides: false };
  const LINE_SPACING = 28;   // ⚠ 反推值（见页面底部说明）

  function addGuides(rects) {
    if (!state.guides) return;
    rects.forEach(([name, r]) => {
      if (!r) return;
      const el = rectEl(stage, r, "guide");
      el.style.zIndex = "20";
      const tag = document.createElement("b");
      tag.textContent = name;
      el.append(tag);
    });
  }

  function renderChat(vw, vh) {
    const L = chatLayout(vw, vh);
    const s = SAMPLE.chat;

    // 面板：Game1.drawDialogueBox(..., drawOnlyBox: true, ignoreTitleSafe: true)
    // —— ChatInputMenu.draw；边框是对话盒纹理 ⚠
    nineSlice(stage, L.panel, [255, 255, 255], DIALOGUE_TEX).style.zIndex = "1";

    // 标题带（ChatInputMenu.DrawHeader → MenuSkinDrawing.DrawTitleBand）：
    // 角色强调色竖条 + 「和 X 聊聊」+ 好感度状态字 + 发丝分隔线。
    // 2026-09-20 外壳重构后 ShouldDrawHeaderTitle / ShouldDrawHeaderStatus 都是 true，
    // 这四样实机都画；标题与状态文案逐字照 DrawHeader：
    //   $"和 {npc.displayName} 聊聊" / hearts is null ? "好感度未知" : $"好感度 {hearts} 心"
    // 强调色走 MenuSkinDrawing.AccentFor(npc.Name) —— 与气泡、徽章同一个来源。
    titleBand(
      stage, L.header,
      `和 ${s.npc} 聊聊`,
      s.hearts === null || s.hearts === undefined ? "好感度未知" : `好感度 ${s.hearts} 心`,
      parseColor(styleFor(s.npc).accent, DEFAULT_ACCENT),
    );

    // 消息区（ChatInputMenu.DrawMessages）
    const area = L.conversationArea;
    const maxWidth = Math.max(80, area.w - 12 * 2 - 12 - 8);          // DrawMessages 的 maxWidth
    const fixedHeight = 12 * 2 + LINE_SPACING + 4;                    // DrawMessages 的 fixedHeight
    const availableHeight = Math.max(1, area.h - 12 * 2 - 8);         // DrawMessages 的 availableHeight
    // 从最新一条往前塞，直到放不下（ChatTextLayoutRules.SelectLatestThatFit）
    const selected = [];
    let remaining = availableHeight;
    for (let i = s.messages.length - 1; i >= 0; i--) {
      const lines = wrapText(s.messages[i].text, contentWidthFor(maxWidth));
      const h = fixedHeight + lines.length * LINE_SPACING + (lines.length - 1) * 4;
      const cost = selected.length === 0 ? h : h + BUBBLE.gap;
      if (selected.length > 0 && cost > remaining) break;
      selected.unshift(s.messages[i]);
      remaining -= cost;
    }
    // 逐条绘制，画到底就停（ChatInputMenu.DrawMessages 的绘制循环）
    let y = area.y + 12;
    for (const message of selected) {
      const isPlayer = message.role === "player";
      const drawn = drawBubble(
        stage, area.x + 12, area.x + area.w - 12, y,
        isPlayer ? "你" : s.npc,                       // Draw 的 speaker
        message.text, isPlayer ? null : s.npc, isPlayer, 0, LINE_SPACING,
      );
      if (!drawn) continue;
      if (y + drawn > area.y + area.h - 12) break;    // DrawMessages 的越界 break
      y += drawn + BUBBLE.gap;                        // DrawMessages 的 y 步进
    }
    // ⚠ 这不是 bug：F8 的消息区在 720p 下只够放一条（SelectLatestThatFit 从最新往
    //    前塞，放不下就停），其余消息要靠滚动（ChatInputMenu.UpdateScrollBar / DrawScrollBar）才能看到。
    const fitNote = `消息区可容纳 ${selected.length} / ${s.messages.length} 条（取窗逻辑 ChatTextLayoutRules.SelectLatestThatFit）`;

    // uiHint（ChatInputMenu.DrawMessages 的提示行分支）：非空才画在消息区左下的次级色小字
    if (s.hint) textAt(stage, area.x + 12, y, s.hint, DIM_GRAY, "g-sm");

    // 角色面板（ChatInputMenu.DrawProfile）
    if (L.profilePanel) {
      const p = L.profilePanel;
      nineSlice(stage, p, [248, 240, 224], MENU_TEX).style.zIndex = "2";   // DrawProfile 的角色卡（CardTint）
      const portraitFrame = { x: p.x + 12, y: p.y + Math.trunc((p.h - 64) / 2), w: 64, h: 64 }; // DrawProfile 的 portraitFrame
      nineSlice(stage, { x: portraitFrame.x - 6, y: portraitFrame.y - 6, w: portraitFrame.w + 12, h: portraitFrame.h + 12 }, [255, 255, 255], MENU_TEX).style.zIndex = "3"; // DrawProfile 的立绘白描边底板
      // ⚠ 页面没有游戏立绘素材，这里用该角色的徽章占位并标注
      const ph = document.createElement("div");
      ph.className = "abs";
      ph.style.left = portraitFrame.x + "px";
      ph.style.top = portraitFrame.y + "px";
      ph.style.width = portraitFrame.w + "px";
      ph.style.height = portraitFrame.h + "px";
      ph.style.display = "grid";
      ph.style.placeItems = "center";
      ph.style.background = rgb(parseColor(styleFor(s.npc).bubble, [239, 231, 244]));
      ph.style.color = rgb(parseColor(styleFor(s.npc).accent, [255, 255, 255]));
      ph.style.zIndex = "4";
      const holder = document.createElement("span");
      holder.style.cssText = "display:block;width:32px;height:32px";
      holder.innerHTML = glyphFor(s.npc);
      holder.firstElementChild.setAttribute("width", "32");
      holder.firstElementChild.setAttribute("height", "32");
      ph.append(holder);
      stage.append(ph);
      const infoX = portraitFrame.x + portraitFrame.w + 12;                 // DrawProfile 的 infoX
      textAt(stage, infoX, p.y + 22, s.npc, GAME_BLACK).style.zIndex = "4";  // DrawProfile 的 displayName
      textAt(stage, infoX, p.y + 22 + 28, `好感度 ${s.hearts} 心`, DIM_GRAY).style.zIndex = "4"; // DrawProfile 的关系文字（InkSoft）
      // 好感度条（DrawProfile 的 meter）
      const meter = { x: infoX, y: p.y + p.h - 12 - 10, w: p.x + p.w - infoX - 12, h: 10 };
      rectEl(stage, meter).style.cssText += `background:${rgb(METER_BG)};z-index:4`;
      const filled = Math.round(meter.w * clamp(s.hearts / 10, 0, 1));       // DrawProfile 的 filledWidth
      if (filled > 0) rectEl(stage, { x: meter.x, y: meter.y, w: filled, h: meter.h }).style.cssText += `background:${rgb(METER_FILL)};z-index:5`;
    }

    // 底部按钮与输入框（ChatInputMenu.DrawFooter）
    button(stage, L.sendButton, "发送", true, [235, 246, 236]);
    button(stage, L.topicButton, "找话题", true, [239, 231, 244]);
    button(stage, L.inventoryButton, "物品", true, [235, 240, 246]);
    button(stage, L.closeButton, "结束", true, [247, 232, 227]);
    textBox(stage, L.inputBox);
    caret(stage, { x: L.inputBox.x + 16, y: L.inputBox.y + 8, w: 4, h: 32 });

    addGuides([
      ["Panel", L.panel], ["Header", L.header], ["MessageArea", L.messageArea],
      ["ConversationArea", L.conversationArea], ["ProfilePanel", L.profilePanel],
      ["InputBox", L.inputBox], ["Send", L.sendButton], ["Topic", L.topicButton],
      ["Inventory", L.inventoryButton], ["Close", L.closeButton],
    ]);
    return fitNote;
  }

  function renderGroup(vw, vh) {
    const L = groupLayout(vw, vh);
    const s = SAMPLE.group;

    // 面板：MenuSkinDrawing.DrawPanel(Color.White) —— GroupDialogueMenu.draw
    nineSlice(stage, L.panel, [255, 255, 255], MENU_TEX).style.zIndex = "1";
    // 标题带（GroupDialogueMenu.draw:170-175 → MenuSkinDrawing.DrawTitleBand）：
    // 竖条 (header.X+12, header.Y+12, 4, 20) + 标题 (header.X+24, header.Y+9)
    // + 发丝线 (header.X+12, header.Bottom-14, header.W-24, 2)，强调色取第一位参与者
    // （C# 是 MenuSkinDrawing.AccentFor(participants[0].NpcId)）。
    // 改前这里只在 (header.X+12, header.Y+10) 画一行裸文字 —— 既没有竖条也没有分隔线。
    titleBand(
      stage, L.header, "线上多人对话", null,
      parseColor(styleFor(s.participants[0]).accent, DEFAULT_ACCENT),
    );
    textAt(stage, L.participantStrip.x, L.participantStrip.y, s.participants.join("、"), DIM_GRAY).style.zIndex = "3"; // draw 的参与者行（MenuSkinRules.InkSoft）

    // 消息区（GroupDialogueMenu.draw）
    const area = L.messageArea;
    const bubbleLeft = area.x + 12;        // draw 的 bubbleLeft
    const bubbleRight = area.x + area.w - 12; // draw 的 bubbleRight
    let y = area.y + 12;                   // draw 的首条 y
    const seen = new Map();                // draw 的 seenBySpeaker（按发言人计次）
    const visible = s.messages.slice(-10); // MaxVisibleMessages = 10（GroupDialogueLayoutRules.cs:28）
    let drawnCount = 0;
    for (const message of visible) {
      const speakerKey = message.npcId;
      const occurrence = seen.get(speakerKey) || 0;
      seen.set(speakerKey, occurrence + 1);
      const isPlayer = message.role === "player";
      const display = isPlayer ? "玩家" : speakerKey;    // draw 的 displayNames 回退
      const drawn = drawBubble(stage, bubbleLeft, bubbleRight, y, display, message.text, isPlayer ? null : speakerKey, isPlayer, occurrence, LINE_SPACING);
      if (!drawn) continue;
      drawnCount++;
      y += drawn + BUBBLE.gap;                           // draw 的 y 步进
      if (y > area.y + area.h - LINE_SPACING) break;     // draw 的画到底 break
    }

    button(stage, L.sendButton, "发送", true);
    button(stage, L.retryButton, "重试", false);   // session.CanRetry 为假时是灰的（MenuButtonDrawing.DrawButton）
    button(stage, L.closeButton, "关闭", true);
    textBox(stage, L.inputBox);
    caret(stage, { x: L.inputBox.x + 16, y: L.inputBox.y + 8, w: 4, h: 32 });
    textAt(stage, area.x + 12, area.y + area.h - 28, s.hint, DIM_GRAY, "g-sm").style.zIndex = "3"; // draw 的提示行分支（MenuSkinRules.InkSoft）

    addGuides([
      ["Panel", L.panel], ["Header", L.header], ["ParticipantStrip", L.participantStrip],
      ["MessageArea", L.messageArea], ["Footer", L.footer], ["InputBox", L.inputBox],
      ["Send", L.sendButton], ["Retry", L.retryButton], ["Close", L.closeButton],
    ]);
    return `一次最多 10 条气泡（GroupDialogueLayoutRules.cs:28），当前画了 ${drawnCount} 条`;
  }

  function renderHub(vw, vh) {
    const L = hubLayout(vw, vh);
    nineSlice(stage, L.panel, [255, 255, 255], MENU_TEX).style.zIndex = "1";   // GroupDialogueHubMenu.draw（面板）
    // 标题带（GroupDialogueHubMenu.draw:126-131 → MenuSkinDrawing.DrawTitleBand）：
    // C# 传的 header 是 panel 顶部那条固定高度的带
    //   new Rectangle(panel.X, panel.Y, panel.W, MenuSkinRules.HubTitleBandHeight = 74)，
    // 于是竖条 (panel.X+12, panel.Y+12, 4, 20)、标题 (panel.X+24, panel.Y+9)、
    // 发丝线 (panel.X+12, panel.Y+74-14, panel.W-24, 2)。
    // 强调色取第一张邀约卡的第一位参与者（C# 是 visibleInvitations[0].Participants.FirstOrDefault()）。
    // 改前这里只在 (panel.X+32, panel.Y+24) 画一行裸文字。
    titleBand(
      stage, { x: L.panel.x, y: L.panel.y, w: L.panel.w, h: HUB_TITLE_BAND_HEIGHT }, "线上多人对话", null,
      parseColor(styleFor(SAMPLE.hub[0].participants[0]).accent, DEFAULT_ACCENT),
    );

    let y = L.panel.y + 94;   // draw 的首行 y
    for (const invitation of SAMPLE.hub) {
      const row = { x: L.panel.x + 32, y, w: L.panel.w - 64, h: 92 };          // draw 的卡片行矩形
      nineSlice(stage, row, [255, 255, 255], MENU_TEX).style.zIndex = "2";     // draw 的卡片 drawTextureBox
      const names = invitation.participants.join("、");
      textAt(stage, row.x + 18, row.y + 14, `${invitation.title} · ${names}`, GAME_BLACK).style.zIndex = "3";      // draw 的标题行（Ink）
      textAt(stage, row.x + 18, row.y + 42, `主题：${invitation.topic}`, DIM_GRAY).style.zIndex = "3";      // draw 的主题行（InkSoft）
      textAt(stage, row.x + 18, row.y + 66, `状态：${invitation.status} · 到期第 ${invitation.expires} 天`, DIM_GRAY, "g-sm").style.zIndex = "3"; // draw 的状态行（InkSoft）
      ["接受", "稍后", "忽略"].forEach((label, i) => {                          // draw 的三个按钮（GroupInvitationActionLayoutRules）
        button(stage, actionButtonAt(row, i), label, true);
      });
      y += 104;                                                                // draw 的行步进
    }

    button(stage, L.closeButton, "关闭", true);                                  // draw 的关闭按钮
    textAt(stage, L.panel.x + 32, L.panel.y + L.panel.h - 112, SAMPLE.hubHint, DIM_GRAY, "g-sm").style.zIndex = "3"; // draw 的提示行（InkSoft）

    addGuides([["Panel", L.panel], ["CloseButton", L.closeButton]]);
    return `邀约卡 ${SAMPLE.hub.length} 张，显示上限 GroupInvitationRules.cs:18 = 4`;
  }

  // ── 自检：内容是否溢出容器（无需外部工具就能看到结论）─────────────────
  function selfCheck(vw, vh) {
    const issues = [];
    const stageRect = { x: 0, y: 0, w: vw, h: vh };
    let count = 0;
    for (const el of stage.querySelectorAll(".nine, .bubble-name, .bubble-line, .bubble-badge, .abs")) {
      if (el.classList.contains("guide")) continue;
      count++;
      const x = parseFloat(el.style.left || "0");
      const yy = parseFloat(el.style.top || "0");
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      if (x < stageRect.x - 1 || yy < stageRect.y - 1 || x + w > stageRect.x + stageRect.w + 1 || yy + h > stageRect.y + stageRect.h + 1) {
        issues.push(`${el.className.split(" ")[0]} 越出视口 (x=${Math.round(x)}, y=${Math.round(yy)}, w=${Math.round(w)}, h=${Math.round(h)})`);
      }
    }
    return { elements: count, issues };
  }

  function fitStage() {
    const available = stageWrap.clientWidth;
    const k = Math.min(1, available / state.width);
    stage.style.transform = `scale(${k})`;
    stageWrap.style.height = (state.height * k) + "px";
    scaleReadout.textContent = `缩放 ${Math.round(k * 100)}% · 舞台 ${state.width}×${state.height}`;
    return k;
  }

  // 三个界面都有一层 DrawScrim（改前只有 F8 有），类名只用来标注当前是哪个界面；
  // 遮罩本身写在 CSS 的 .stage.f8/.f9/.hub::before 上，三处同值。
  const VIEW_CLASS = { chat: "f8", group: "f9", hub: "hub" };

  function render() {
    stage.className = `stage ${VIEW_CLASS[state.view]}`;
    stage.style.width = state.width + "px";
    stage.style.height = state.height + "px";
    stage.replaceChildren();
    let note = "";
    if (state.view === "chat") note = renderChat(state.width, state.height);
    else if (state.view === "group") note = renderGroup(state.width, state.height);
    else note = renderHub(state.width, state.height);
    fitStage();
    updateStatus(note);
  }

  function updateStatus(note) {
    const result = selfCheck(state.width, state.height);
    const label = { chat: "F8 私聊", group: "F9 群聊", hub: "群聊中心" }[state.view];
    const items = [
      ["pill", `${label} · ${state.width}×${state.height}`],
      ["pill", `舞台内元素 ${result.elements}`],
      result.issues.length === 0
        ? ["pill ok", "内容未溢出视口 ✓"]
        : ["pill bad", `溢出 ${result.issues.length} 处：${result.issues.join("；")}`],
    ];
    if (note) items.push(["pill", note]);
    items.push(["pill ok", "✔ 输入框 / 菜单九宫格已用真实 PNG 贴图"]);
    statusbar.replaceChildren();
    for (const [cls, text] of items) {
      const el = document.createElement("span");
      el.className = cls;
      el.textContent = text;
      statusbar.append(el);
    }
    // 自检结果也挂到 window 上，便于自动化验证读取（不写 console.error）
    window.__UI_PREVIEW_SELFCHECK__ = { view: state.view, width: state.width, height: state.height, ...result };
    window.__UI_PREVIEW_READY__ = true;
  }

  document.getElementById("seg-view").addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-view]");
    if (!btn) return;
    state.view = btn.dataset.view;
    syncSegments();
    render();
  });
  document.getElementById("seg-size").addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-size]");
    if (!btn) return;
    const [w, h] = btn.dataset.size.split("x").map(Number);
    state.width = w;
    state.height = h;
    syncSegments();
    render();
  });
  guidesToggle.addEventListener("change", () => { state.guides = guidesToggle.checked; render(); });
  window.addEventListener("resize", fitStage);

  function syncSegments() {
    for (const btn of document.querySelectorAll("#seg-view button")) {
      btn.setAttribute("aria-pressed", String(btn.dataset.view === state.view));
    }
    for (const btn of document.querySelectorAll("#seg-size button")) {
      btn.setAttribute("aria-pressed", String(btn.dataset.size === `${state.width}x${state.height}`));
    }
  }

  syncSegments();
  render();
})();
</script>
</body>
</html>'''


def ui_preview_page() -> str:
    """返回 /test/ui 的完整页面。"""

    payload = {
        "styles": _styles_payload(),
        "glyphs": _glyphs_payload(),
        "ornaments": {
            npc: item["ornament"] for npc, item in NPC_BUBBLE_ELEMENTS.items()
        },
        "aliases": NPC_BUBBLE_ALIASES,
    }
    return (
        _UI_PREVIEW_BODY.replace("__DATA__", _json(payload))
        .replace("__FRAME_SCRIPT__", _CHARACTER_FRAME_SCRIPT)
        .replace("__BUBBLE_MENU_TEX__", BUBBLE_MENU_TEX_DATA_URI)
        .replace("__PLAIN_MENU_TEX__", PLAIN_MENU_TEX_DATA_URI)
        .replace("__PLAYER_BUBBLE_TINT__", _tint_literal(PLAYER_BUBBLE_TINT))
        .replace("__NPC_FALLBACK_BUBBLE_TINT__", _tint_literal(NPC_FALLBACK_BUBBLE_TINT))
    )
