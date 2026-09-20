"""三个游戏内聊天界面的「外壳重构」设计稿（/test/ui-redesign）。

与 :mod:`ui_preview_page`（/test/ui）的分工：

* ``/test/ui``  —— **现状**的忠实复刻，负责「游戏现在长什么样」。
* 本页面       —— **新设计**的对照稿，负责「外壳改成什么样」，并且把现状与新设计
  放在同一个坐标系里并排，方便一眼看出改了哪里。

三条硬约束（写在代码里，便于核对）：

1. **气泡一个像素都不动**：气泡的尺寸、换行、配色、徽章、装饰边框全部复用回放页那套
   （``_CHARACTER_FRAME_SCRIPT`` / ``npc_bubble_elements`` / ``npc_bubble_catalog``），
   本文件只决定「气泡画在哪」，不决定「气泡长什么样」。
2. **只能用游戏现有手段**：原版九宫格（``drawTextureBox`` / ``drawDialogueBox``）、
   纯色 tint（``Color`` 相乘）、原版位图字体、已有的气泡素材。页面里凡是靠网页特性
   近似的地方，都在下方说明区里标了「怎么近似」。
3. **几何常量从 ``smapi/`` 抄**，每个数字都跟着 ``文件.cs:行号``；本稿只改「画什么」，
   不动「画在哪」，除页面上明确标了「改点击坐标」的开关。

外壳的视觉基准是气泡：气泡是「浅色/深色实底 + 深色描边 + 装饰轮廓」，所以外壳统一成
「一块暖色纸面（面板）→ 内嵌一层凹陷纸面（内容区）→ 卡片与按钮浮在凹陷之上」，
全部用同一张 ``Maps\\MenuTiles`` 贴图的同一个源矩形，只靠 tint 分档。
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
from .ui_preview_redesign_assets import GAME_TEX, GAME_TEX_BAKED


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


def _ornaments_payload() -> dict[str, dict[str, object]]:
    """装饰边框素材（NpcBubbleFrame.cs 的游戏内实现读的是同一张表）。"""

    return {npc: item["ornament"] for npc, item in NPC_BUBBLE_ELEMENTS.items()}


def _sample_payload() -> dict[str, object]:
    """示例内容：只有**结构**来自代码，文案是本稿编的。

    现状侧与新设计侧用同一份，保证两边能逐条比对。
    邀约卡标题取自 ``GroupInvitationThemes.cs`` 的真实主题名。
    """

    return {
        "chat": {
            "npc": "Sophia",
            "hearts": 6,
            "hint": "",
            "messages": [
                {"role": "npc", "text": "刚从葡萄架那边回来，手上全是泥。"},
                {"role": "player", "text": "辛苦了，我给你带了点东西。"},
                {"role": "npc", "text": "……你每次都这样。先放着吧，等我把这排绑完。"},
            ],
        },
        "group": {
            "participants": ["Abigail", "Emily"],
            "hint": "线上群聊不会传送 NPC，也不会改变他们的日程。",
            "messages": [
                {"role": "player", "npcId": "player", "text": "你们最近都在忙什么？"},
                {"role": "npc", "npcId": "Abigail", "text": "还那样，翻翻漫画打打游戏。地里的活也没少干就是了。"},
                {"role": "npc", "npcId": "Emily", "text": "我在挑布料的颜色，春天适合宝石色调，比冬天大胆多了。"},
                {"role": "npc", "npcId": "Abigail", "text": "（她插了一句）那你上次那块紫色呢，留着还是用了？"},
            ],
        },
        "hub": {
            "hint": "选择一张邀约卡参与群聊。",
            "empty": "目前没有未处理的邀约卡。",
            "cards": [
                {"title": "闲下来的消遣", "participants": ["Abigail", "Emily"], "topic": "闲下来的消遣", "status": "未读", "expires": 12},
                {"title": "手头的活计", "participants": ["Robin", "Pierre"], "topic": "手头的活计", "status": "进行中", "expires": 14},
                {"title": "往外面跑", "participants": ["Sebastian", "Sam"], "topic": "往外面跑", "status": "稍后处理", "expires": 9},
                {"title": "好看的东西", "participants": ["Leah", "Haley"], "topic": "好看的东西", "status": "未读", "expires": 15},
            ],
        },
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


_UI_REDESIGN_BODY = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>外壳重构设计稿 · Stardew AI NPC</title>
<style>
:root {
  color-scheme: dark;
  --bg: #14161c;
  --surface: #1d2028;
  --line: #39404f;
  --text: #eceef4;
  --muted: #a3abbd;
  --soft: #cfd5e2;
  --gold: #e5bf7c;
  --green: #b3ce91;
  --warn: #f0b58a;
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; color: var(--text); background: var(--bg); }
a { color: inherit; }
button, select, input { font: inherit; }
.page { width: min(1560px, calc(100% - 40px)); margin: 0 auto; padding: 26px 0 64px; }
.eyebrow { color: var(--green); font-size: .67rem; letter-spacing: .18em; text-transform: uppercase; font-weight: 700; }
h1 { margin: 9px 0 10px; font-size: clamp(1.4rem, 2.4vw, 1.95rem); font-weight: 650; }
.subtitle { max-width: 1000px; margin: 0; color: var(--muted); font-size: .78rem; line-height: 1.85; }
.subtitle b { color: var(--soft); font-weight: 400; }
.subtitle code { color: #d8c9a0; font-family: ui-monospace, Consolas, monospace; font-size: .72rem; }

.toolbar { display: flex; flex-wrap: wrap; gap: 16px 22px; align-items: flex-end; margin: 18px 0 12px; padding: 13px 15px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }
.field { display: grid; gap: 6px; }
.field > span { color: var(--muted); font-size: .65rem; letter-spacing: .06em; }
.seg { display: flex; gap: 4px; padding: 3px; border: 1px solid var(--line); border-radius: 5px; background: #191c24; }
.seg button { border: 1px solid transparent; border-radius: 3px; padding: 6px 11px; color: var(--muted); background: transparent; cursor: pointer; font-size: .72rem; white-space: nowrap; }
.seg button:hover { color: var(--text); background: #262b36; }
.seg button[aria-pressed="true"] { color: #1b1d24; background: var(--gold); border-color: var(--gold); font-weight: 600; }
.opts { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; }
.check { display: flex; align-items: center; gap: 6px; color: var(--soft); font-size: .72rem; cursor: pointer; }
.check input { accent-color: var(--gold); }
.check.risk { color: var(--warn); }
.toolbar-note { margin-left: auto; color: var(--muted); font-size: .67rem; line-height: 1.7; text-align: right; }

.statusbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; font-size: .71rem; color: var(--muted); }
.pill { border: 1px solid var(--line); border-radius: 999px; padding: 4px 10px; background: var(--surface); }
.pill.ok { color: var(--green); border-color: #47593b; }
.pill.bad { color: #f0a08a; border-color: #7a4234; }
.pill.warn { color: var(--gold); border-color: #6d5c36; }

/* ── 舞台组：现状 / 新设计可单显或并排 ───────────────────────────────── */
.stage-wrap { display: flex; gap: 16px; align-items: flex-start; width: 100%; }
.stage-col { flex: 1 1 0; min-width: 0; }
.stage-col[hidden] { display: none; }
.stage-head { display: flex; align-items: baseline; gap: 8px; margin: 0 0 7px; }
.stage-head h2 { margin: 0; font-size: .8rem; font-weight: 600; color: var(--soft); }
.stage-head em { color: var(--muted); font-size: .67rem; font-style: normal; }
.stage-head.legacy h2 { color: #cbb083; }
.stage-head.design h2 { color: var(--green); }
.stage-holder { position: relative; width: 100%; overflow: hidden; }
.stage {
  position: absolute; left: 0; top: 0; transform-origin: top left;
  overflow: hidden; border: 1px solid var(--line); border-radius: 3px;
  /* 游戏画面示意底：真实游戏里菜单叠在场景画面上 */
  background: radial-gradient(120% 90% at 20% 8%, #4b6b45 0%, #35513a 42%, #243528 100%);
}
.stage::after {
  content: "此处为游戏画面示意"; position: absolute; left: 9px; bottom: 7px;
  color: rgba(255,255,255,.3); font-size: 12px; pointer-events: none;
}
/* 整屏遮罩：F8 / F9 / 中心三处都画 MenuSkinDrawing.DrawScrim
   （Color.Black * MenuSkinRules.ScrimAlpha = 0.28f）；改前只有 F8 有，且是 0.42f */
.scrim { position: absolute; inset: 0; background: #000; }

/* 游戏字体近似：字号 17.5px 来自 bubble-f9.png 实测的中文全角字宽（与 /test/ui 同源） */
.g { font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif; font-size: 17.5px; line-height: 21px; }
.g-sm { font-size: 17.5px; line-height: 21px; }
.abs { position: absolute; }
.nowrap { white-space: nowrap; }

/* 九宫格：border-image 切图 + feColorMatrix 做 tint 的逐通道乘法（与 /test/ui 同法） */
.nine { position: absolute; border-style: solid; }
.guide { position: absolute; border: 1px dashed rgba(255,255,255,.5); pointer-events: none; }
.guide > b { position: absolute; left: 0; top: -15px; padding: 0 4px; color: #0d0f14; background: rgba(255,255,255,.72); font-size: 10px; line-height: 14px; font-weight: 600; white-space: nowrap; }
/* 「会改点击坐标」的元素：新设计里用红色虚线标出 */
.risk { position: absolute; border: 1px dashed rgba(255,138,110,.95); pointer-events: none; }
.risk > b { position: absolute; right: 0; top: -15px; padding: 0 4px; color: #2a0f08; background: rgba(255,138,110,.92); font-size: 10px; line-height: 14px; font-weight: 700; white-space: nowrap; }
/* 现状侧的「这里有问题」标注：蓝色虚线 */
.risk.note { border-color: rgba(122,196,255,.95); }
.risk.note > b { left: 0; right: auto; color: #04202f; background: rgba(122,196,255,.92); font-weight: 600; }

/* 气泡：与 /test/ui 同一套语义（group_dialogue_review_page.py:345-352）。

   ⚠⚠ 装饰必须挂在 stage 上，不能 append 进气泡元素（2026-09-20 修，别再放回去）：
   气泡元素带 tint 用的 feColorMatrix（见 tintFilter / GAME_TEX_BAKED 的回退分支），
   CSS filter 作用于**整棵子树** —— 装饰一旦成为它的后代，绿色茎叶会被气泡 tint 逐通道
   乘成暗紫红（实测 Sophia 那档 tint 下绿叶 #7ea466 → #341c22，tint 越深只会越紫）。
   所以几何改由 drawBubble 按气泡 bounds 显式给出，与原来的 padding-box inset -34px 等价：
     left = bounds.x - 14, top = bounds.y - 14, width = bounds.w + 28, height = bounds.h + 28

   ⚠ 换算依据（勿改数）：绝对定位的 inset 相对的是包含块的 **padding box**，
     而气泡是 border-box + 20px border 的九宫格 → padding box 比气泡矩形内缩 20px。
     想让 SVG 的 viewBox（w+28, h+28）**1:1** 铺在「气泡外扩 14px」的位置上，
     就等价于 -(20 + 14) = **-34px**（容器 = (w-40)+68 = w+28 ✓ 与 viewBox 完全吻合）。

   z-index 5：气泡 .nine 自身是 4，文字层是 7 —— 装饰贴在气泡之上、文字之下。

   ⚠ 曾经写成 inset:-15px：frame 变成 (w-10)×(h-10)，SVG 被**非等比**压进这个框
     —— 403×84 的气泡对应 393×74 的 frame，横向缩到 91%、纵向缩到 66%，
     装饰整圈收进气泡内 14~18px 且被压扁，观感就是「边框比气泡小了一圈」。

   判据来自游戏截图（不是我们的偏好）：artifacts/visual-tests/bubble-f9-v1/bubble-f9.png 里
     Abigail / Emily 的装饰**沿气泡边缘、并且左右上下都探到气泡外面**；
     .tmp/ui-preview/game-f9-abigail-bubble-2x.png 是裁出来的放大图。
     所以「装饰收在气泡内部」不是基线，是渲染错误。 */
.bubble-frame { position: absolute; z-index: 5; pointer-events: none; user-select: none; line-height: 0; }
.bubble-frame svg { display: block; width: 100%; height: 100%; overflow: visible; image-rendering: pixelated; }
.bubble-badge { position: absolute; width: 24px; height: 24px; }
.bubble-badge svg { width: 24px; height: 24px; display: block; image-rendering: pixelated; }
.bubble-line, .bubble-name { position: absolute; white-space: pre; }

.notes { margin-top: 26px; display: grid; gap: 16px; }
.card { border: 1px solid var(--line); border-radius: 6px; background: var(--surface); padding: 16px 18px; }
.card h2 { margin: 0 0 11px; font-size: .85rem; font-weight: 600; color: var(--soft); }
.card h3 { margin: 14px 0 7px; font-size: .75rem; font-weight: 600; color: var(--muted); }
.card p { margin: 0 0 9px; color: var(--muted); font-size: .73rem; line-height: 1.85; }
table { width: 100%; border-collapse: collapse; font-size: .7rem; }
th, td { padding: 6px 9px; border-bottom: 1px solid #2c313c; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 500; white-space: nowrap; }
td code, .card code { color: #d8c9a0; font-family: ui-monospace, Consolas, monospace; font-size: .67rem; }
ul.plain { margin: 0; padding-left: 18px; color: var(--muted); font-size: .73rem; line-height: 1.9; }
ul.plain b { color: var(--soft); font-weight: 600; }
.flag { color: var(--warn); font-weight: 700; }
.ok { color: var(--green); font-weight: 600; }
</style>
</head>
<body data-page="ui-redesign">
<main class="page">
  <header>
    <div class="eyebrow">Bridge / UI Redesign</div>
    <h1>外壳重构设计稿 · 三个聊天界面统一视觉语言</h1>
    <p class="subtitle">
      左「现状」＝ <code>/test/ui</code> 的复刻逻辑，右「新设计」＝ 本稿。
      <b>气泡保持原样</b>（尺寸、换行、配色、徽章、装饰边框全部复用回放页那套，本页一行未改），
      重构的是它外面的壳：面板、标题栏、消息区、输入框、按钮、卡片、间距、配色。
      所有改动都落到原版手段上（九宫格 + tint + 位图字体），逐项对应见页面底部。
    </p>
  </header>

  <div class="toolbar">
    <div class="field">
      <span>界面</span>
      <div class="seg" id="seg-view" role="group" aria-label="界面切换">
        <button type="button" data-view="chat">F8 · 私聊</button>
        <button type="button" data-view="group">F9 · 群聊</button>
        <button type="button" data-view="hub">群聊中心</button>
      </div>
    </div>
    <div class="field">
      <span>尺寸（UI 视口）</span>
      <div class="seg" id="seg-size" role="group" aria-label="尺寸切换">
        <button type="button" data-size="1280x720">1280 × 720</button>
        <button type="button" data-size="1600x900">1600 × 900</button>
        <button type="button" data-size="1920x1080">1920 × 1080</button>
        <button type="button" data-size="1024x600">1024 × 600</button>
      </div>
    </div>
    <div class="field">
      <span>对比</span>
      <div class="seg" id="seg-mode" role="group" aria-label="对比模式">
        <button type="button" data-mode="legacy">现状</button>
        <button type="button" data-mode="design">新设计</button>
        <button type="button" data-mode="side">并排</button>
      </div>
    </div>
    <div class="field">
      <span>叠加</span>
      <div class="opts">
        <label class="check"><input type="checkbox" id="toggle-guides"> 布局参考线</label>
        <label class="check risk"><input type="checkbox" id="toggle-risk"> 标出改动点</label>
      </div>
    </div>
    <div class="field">
      <span>设计开关（只影响新设计）</span>
      <div class="opts">
        <label class="check"><input type="checkbox" id="opt-scrim" checked> 统一轻遮罩</label>
        <label class="check risk"><input type="checkbox" id="opt-f8frame"> F8 照切原版 64px 框（会画错，见说明）</label>
        <label class="check"><input type="checkbox" id="opt-title" checked> 标题带 + 分隔线</label>
        <label class="check"><input type="checkbox" id="opt-inset" checked> 内容区凹槽</label>
        <label class="check"><input type="checkbox" id="opt-input" checked> 输入区重做</label>
        <label class="check"><input type="checkbox" id="opt-card" checked> 卡片文字并两行</label>
      </div>
    </div>
    <div class="toolbar-note">
      舞台按列宽自动缩放，内部坐标始终是游戏像素<br>
      <span id="scale-readout"></span>
    </div>
  </div>

  <div class="statusbar" id="statusbar"></div>

  <div class="stage-wrap">
    <div class="stage-col" id="col-legacy">
      <div class="stage-head legacy"><h2>现状</h2><em>现在游戏里画出来的样子</em></div>
      <div class="stage-holder" id="holder-legacy"><div class="stage" id="stage-legacy"></div></div>
    </div>
    <div class="stage-col" id="col-design">
      <div class="stage-head design"><h2>新设计</h2><em>外壳重构后</em></div>
      <div class="stage-holder" id="holder-design"><div class="stage" id="stage-design"></div></div>
    </div>
  </div>

  <section class="notes">
    <div class="card">
      <h2>一、新设计改了什么，为什么这么改</h2>
      <p>基准是气泡：气泡是「实底 + 深色描边 + 装饰轮廓」的三层结构。外壳照这个结构重排——
         面板是一张纸，内容区是纸上压出来的一层浅凹，卡片与按钮浮在凹上，全部走<b>同一张
         <code>Maps\MenuTiles</code> 贴图的同一个源矩形</b>，只靠 tint 分档。这样三个界面不需要
         各记一套颜色，也不会再出现「米黄面板 vs 深色面板」的割裂。</p>
      <table>
        <thead><tr><th>部位</th><th>现状</th><th>新设计</th><th>为什么</th></tr></thead>
        <tbody>
          <tr>
            <td>面板</td>
            <td>F8 走 <code>drawDialogueBox</code>（<code>MenuTiles</code> 的 <b>64px</b> 九宫格、无投影）；
                F9 / 中心走 <code>drawTextureBox</code>（同图 <b>20px</b> 九宫格、带投影）</td>
            <td>三个界面统一 <code>drawTextureBox(Color.White)</code>（20px 九宫格）</td>
            <td>两套九宫格的<b>描边厚度与色阶不同</b>（64px vs 20px），这正是「F8 与 F9 看着不是一套」
                的直接原因；统一到 20px 后与气泡、按钮同族。附带消掉 <code>drawDialogueBox</code>
                的 title-safe 裁切隐患</td>
          </tr>
          <tr>
            <td>标题栏</td>
            <td><b>改前</b>：F8 的 header 算得出 92px 高，但两个开关都是 false，<b>什么都不画</b>——面板顶部留一条空白；
                F9 的标题在 <code>(header.X+12, header.Y+10)</code>；中心的标题在 <code>(panel.X+32, panel.Y+24)</code>。
                <br>本项 2026-09-20 已落地：三处现在都走 <code>DrawTitleBand</code>，
                本页左右两栏画法一致（竖条 + 标题 + 发丝线，几何见下方第二节第 3 项）</td>
            <td>三处统一：角色强调色竖条 + 标题 + 右侧状态字，标题下一条<b>发丝分隔线</b></td>
            <td>F8 顶部那条空白是「脏」的主要来源之一；加上标题后三个界面的第一眼结构一致，
                竖条让「现在跟谁说话」有个视觉锚点</td>
          </tr>
          <tr>
            <td>消息区</td>
            <td>没有自己的底，气泡直接贴在面板上</td>
            <td>加一层<b>内嵌凹槽</b>（同图九宫格 × <code>Inset</code> tint、不投影）</td>
            <td>气泡是浅色/深色块，浮在与自己明度接近的橙面板上会「糊」；凹槽压暗一档后气泡立刻跳出来，
                也给 F8 的角色卡、中心的邀约卡一个统一的落点</td>
          </tr>
          <tr>
            <td>输入框</td>
            <td>本体只有 <b>48px</b> 高，下面跟着一条 ~64px 的米褐色带</td>
            <td>输入区做成凹槽，输入框 48px 在其中<b>垂直居中</b>；深色带消失</td>
            <td>那条带的成因见下方第二节第 4 行——它不是贴图里画好的第二段，是
                <code>TextBox.Draw</code> 源矩形高度写成 <code>Height</code> 后采样被 clamp 到贴图末行的产物。
                把 <code>Height</code> 设成 48 就自然消失，且 48 正是原版这套素材的设计高度</td>
          </tr>
          <tr>
            <td>按钮</td>
            <td>F8 四个按钮四种 tint（淡绿 / 淡紫 / 淡蓝 / 淡粉）；F9 与中心是白 tint</td>
            <td>统一成两档：<b>主按钮</b> = 白 tint，<b>次按钮</b> = 暗一档的暖色 tint，禁用 = <code>Color.Gray</code></td>
            <td>四种淡色调在橙底上产生的是<b>难以名状的偏色</b>（实测 <code>e9b566</code> / <code>edaa69</code> /
                <code>e9b16a</code> / <code>f5ab62</code>），彼此差异小到看不出含义，只留下「脏」。
                改成两档后「发送」自然突出，其余退到后面</td>
          </tr>
          <tr>
            <td>卡片</td>
            <td>中心的邀约卡与面板<b>同色</b>（都是白 tint），只靠一圈描边区分；第三行「状态」压在卡片底边框上</td>
            <td>卡片保持白 tint（浮在凹槽上就分层了）；三行文字<b>并成两行</b>，卡片几何一点不动</td>
            <td>同色叠同色是「糊成一片」的根因；用「底色分档」比「给卡片刷个颜色」更稳。
                文字那一项是<b>量出来的</b>：九宫格 slice 20 → 下内沿 = 高 − 20 = 72，
                现状第三行在 +66、行高 28 → 文字底 <b>+94</b>，比卡片本身（92）还低 2px，
                等于被下边框切断；并成两行后第二行底正好 +72，不出框也不动几何</td>
          </tr>
          <tr>
            <td>提示行</td>
            <td>hint 画在 <code>messageArea.Bottom - 28</code>，而气泡也排到同一块高度的底部 ——
                气泡一多，提示行就压在气泡上（F9 现状截图里能看到）</td>
            <td>消息区凹槽；提示行<b>优先</b>移到 header 右侧、与参与者条同一行（右对齐、气泡区零损失）；
                只有放不下 header 的长提示（排障串）才落到底部留白，那时气泡区减 30px</td>
            <td>「状态提示」和「对话内容」是两种信息，共用一块高度必然打架。分开后提示行位置稳定，
                气泡也不会被它压住</td>
          </tr>
          <tr>
            <td>间距</td>
            <td>按钮之间的 gap 8、卡片步进 104、F8 header 与消息区只隔 8——标题带起来后这条太挤</td>
            <td>不改任何几何常量：靠凹槽的 20px 内边距 + 标题分隔线制造呼吸感</td>
            <td>几何一动就会改点击坐标；本稿只在明确标了风险的开关上动几何</td>
          </tr>
          <tr>
            <td>配色</td>
            <td>三档文字色混用：<code>Color.Black</code> / <code>DarkSlateGray</code>(47,79,79) / <code>DimGray</code>(105,105,105)；
                <b>改前</b> F8 有 42% 黑遮罩，F9 与中心没有（本项已落地：三处都走
                <code>MenuSkinDrawing.DrawScrim</code>，同一个 <code>ScrimAlpha = 0.28f</code>）</td>
            <td>文字收敛为两档（<code>Black</code> + <code>DimGray</code>）；三处遮罩统一成 28%</td>
            <td><code>DarkSlateGray</code> 偏青，压在暖橙底上会发灰发脏；两档足够表达层次。
                遮罩统一后三个界面「浮在画面上的高度」一致，这是风格割裂里最容易被忽略的一条</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>二、每一项在 C# 里怎么实现</h2>
      <table>
        <thead><tr><th>改动</th><th>手段</th><th>近似程度</th></tr></thead>
        <tbody>
          <tr>
            <td>1. 面板统一</td>
            <td><code>IClickableMenu.drawTextureBox(b, x, y, w, h, Color.White)</code>，
                F8 把 <code>Game1.drawDialogueBox(...)</code> 换成这一句</td>
            <td><span class="ok">精确</span>：与 F9 / 中心现在用的完全同一条调用。
                <br><span class="flag">现状侧的一点保留</span>：<code>drawDialogueBox</code> 用的是
                <code>Maps\MenuTiles</code> 里<b>另一套切法</b>（64px 九宫格、中心块还另有
                <code>(x+28, y+28)</code> 的偏移），与 CSS border-image 的九宫格语义不同，
                在网页上照切会画出一圈原版并不存在的装饰花纹。所以本页现状侧只保留它
                可确定的那一项差异（<b>没有投影</b>），轮廓花纹请对照
                <code>/test/ui</code> 与游戏截图</td>
          </tr>
          <tr>
            <td>2. 内容区凹槽</td>
            <td><code>drawTextureBox(b, area.X, area.Y, area.Width, area.Height, new Color(232, 228, 224), 1f, drawShadow: false)</code>
                —— 同一个源矩形，只换 tint、关掉投影</td>
            <td><span class="ok">精确</span>：tint 相乘是原版既有机制（实测面板填充 <code>#ffc576</code> × tint 即得凹槽色）</td>
          </tr>
          <tr>
            <td>3. 标题带</td>
            <td>① 强调竖条：<code>b.Draw(Game1.fadeToBlackRect, new Rectangle(x, y, 4, 20), accentColor)</code>；
                ② 标题 / 状态：<code>b.DrawString(Game1.smallFont, ..., Color.Black / Color.DimGray)</code>；
                ③ 分隔线：<code>b.Draw(Game1.fadeToBlackRect, new Rectangle(x, y, w, RuleHeight), new Color(150, 96, 48) * 0.55f)</code>
                —— 高度是 <code>MenuSkinRules.RuleHeight = 2</code>（<code>MenuSkinRules.cs:99</code>），<b>不是 1</b></td>
            <td><span class="ok">精确</span>：<code>fadeToBlackRect</code> 是 1×1 白纹理，原版到处用它画纯色矩形。
                <br><span class="flag">颜色要按预乘读</span>：XNA 的 <code>Color * float</code> 把 RGB 与 alpha
                <b>一起乘</b>（逐通道相乘后取整），所以 <code>new Color(150, 96, 48) * 0.55f</code> 实际是
                <code>Color(82, 52, 26, 140)</code>；网页上的等价写法因此是
                <code>rgba(82,52,26,140/255)</code>，而不是 <code>rgba(150,96,48,.55)</code> —— 后者叠在
                <code>#ffc576</code> 面板上得 <code>rgb(197,141,80)</code>，比 C# 的 <code>rgb(160,117,68)</code>
                亮 37 个色阶（换算与实测见 <code>SKIN.rule</code> 的注释）</td>
          </tr>
          <tr>
            <td>4. 输入框去深色带</td>
            <td>把 <code>inputBox.Height</code> 设成 <b>48</b>（视觉矩形），位置在输入区凹槽内居中；
                <b>点击判定继续用 <code>layout.InputBox</code></b>，不动</td>
            <td><span class="ok">精确</span>：深色带的成因是源矩形高 <code>Height</code> &gt; 贴图高 48 时采样被 clamp 到末行
                <code>(57,54,65,66)</code>（26% 冷灰）。<code>Height ≤ 48</code> 时 1:1 采样，那条带不存在；
                48 也正好是原版为这套素材设计的框高（实测游戏输入框本体就是 y434–473 共 40+4+4）
                <br><span class="flag">注意</span>：改用自绘输入框（不用 <code>TextBox.Draw</code>）也能去掉，
                但要自己实现光标与选区；本稿采用改 <code>Height</code> 的方案，改动最小</td>
          </tr>
          <tr>
            <td>5. 按钮两档 tint</td>
            <td><code>MenuButtonDrawing.DrawButton(b, bounds, label, enabled, tint)</code> 已经在；
                把调用点的 tint 改成 <code>Color.White</code>（主）/ <code>new Color(238, 226, 208)</code>（次），
                禁用沿用现有的 <code>Color.Gray</code></td>
            <td><span class="ok">精确</span>：只是换了传进去的颜色值，函数本身不动</td>
          </tr>
          <tr>
            <td>6. 卡片浮起</td>
            <td>卡片调用点<b>保持 <code>Color.White</code></b>；它之所以现在看不出层次，是因为底层也是白 tint。
                加了第 2 项的凹槽之后自动分层，无需新增绘制</td>
            <td><span class="ok">精确</span>：零改动</td>
          </tr>
          <tr>
            <td>7. 文字两档</td>
            <td>把 <code>Color.DarkSlateGray</code> 的调用点改成 <code>Color.DimGray</code>（F8 状态行、头像旁好感度、
                F9 参与者条、中心卡片「主题」行）</td>
            <td><span class="ok">精确</span>：换枚举值</td>
          </tr>
          <tr>
            <td>8. 统一轻遮罩</td>
            <td>抽一句 <code>MenuSkinDrawing.DrawScrim</code>（<code>b.Draw(Game1.fadeToBlackRect,
                viewportRect, Color.Black * MenuSkinRules.ScrimAlpha)</code>），三处界面各调一次；
                F8 原来的 <code>0.42f</code> 一并收敛到这个常量</td>
            <td><span class="ok">精确</span>：F8 现有代码就是这个写法，照搬；常量
                <code>ScrimAlpha = 0.28f</code>（<code>MenuSkinRules.cs:69</code>）三处同值，
                调用点 <code>ChatInputMenu.cs:635</code> / <code>GroupDialogueMenu.cs:162</code> /
                <code>GroupDialogueHubMenu.cs:119</code></td>
          </tr>
          <tr>
            <td>9. 卡片文字并两行</td>
            <td>第二行改为 <code>b.DrawString(Game1.smallFont, $"主题：{topic} · {status} · 到期第 {n} 天", new Vector2(row.X + 18, row.Y + 44), Color.DimGray)</code>；
                第三行的 <code>DrawString</code> 调用删除。卡片矩形、行步进、按钮命中区<b>一个都不动</b></td>
            <td><span class="ok">精确</span>：只改了文字的坐标与拼接，<code>invitationRows</code> /
                <code>GroupInvitationActionLayoutRules</code> / harness 的 <code>VisualTestAcceptButton</code> 全部不受影响。
                <br><span class="flag">本稿试过但放弃的一条路</span>：把卡片从 92 加高到 116 也能让三行都不出框，
                但九宫格 slice 20 意味着「面板 20 + 凹槽 20 + 卡片 20」三层边框，加高后 1280×720 与 1600×900
                每屏只能放 <b>3 张</b>（现在 4 张）—— 拿「少看一张邀约」换一行字的位置，不值得</td>
          </tr>
          <tr>
            <td>10. 网页侧的近似</td>
            <td>① 九宫格用 <code>border-image … fill stretch</code> 切真贴图；② 外壳的 tint
                <b>在服务端预乘进贴图</b>（`GAME_TEX_BAKED`），页面里这些框<b>不带任何滤镜</b>；
                ③ 投影用 <code>drop-shadow(-8px 8px 0 rgba(0,0,0,.4))</code></td>
            <td><span class="flag">近似</span>：① ② 与游戏同构（就是同一条乘法、同一套切法）。
                ② 之所以预乘：滤镜在部分浏览器 / GPU 合成路径下会被忽略或按 linearRGB 计算，
                表现就是「颜色不对」，配合 transform 缩放还可能有边框重采样错位 ——
                预乘之后任何浏览器渲染出的都是同一组像素。气泡的 tint 是按角色动态的，仍走滤镜
                （角色气泡另用一份服务端预处理过的描边变体，玩家 / 兜底气泡另用一张未着色面板，
                见 <code>npc_bubble_texture.py</code> 与 <code>npc_bubble_panel_plain.py</code>）；
                ③ 原版投影是<b>九宫格逐块再画一遍</b>，页面用一层滤镜近似，框体轮廓一致、
                紧贴边框内侧约 10px 的差看不出来但确实存在</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>三、一个必须写下来的坑：F8 的 64px 框，用错贴图会整片错位</h2>
      <p>这条是本稿踩过、也最容易被误读成「新设计坏了」的地方，单独列出来。</p>
      <ul class="plain">
        <li><b>现象</b>：勾上右上的「F8 照切原版 64px 框」，面板<b>外框整体错位</b> ——
            边框跑到面板中间、还多出一大片竖条，颜色也跟着乱。<b>关掉就正常</b>。</li>
        <li><b>根因（2026-09-20 逐像素量过）</b>：本稿一开始是把
            <code>Maps\MenuTiles (0,0,256,256)</code> <b>原样</b>拿去按 64px 九宫格切，
            而这一块<b>不是九宫格素材，是一整张画好的对话气泡图形</b>：
            框体在 <code>(16,16)-(239,239)</code>、框外还有 16px 透明；内部 <code>y84–107</code>
            是一条标题分隔带、<code>y128–187</code> 是带纵向渐变的填充（<code>#ffcb7b → #eba867</code>）、
            底部中间 <code>(88..103, 240)</code> 还有气泡尾巴。九宫格的「中心块」正好取到那条分隔带与渐变，
            被拉伸铺满整个面板 —— 于是「外框偏移 + 颜色不对」同时出现。</li>
        <li><b>对照（重要）</b>：<code>/test/ui</code> 的 F8 面板<b>也是</b> 64px 九宫格，
            但它内联的是<b>另一张 192×192 的图</b>（内联 base64 长度 1094，本稿那块是 2210），
            所以它渲染正常。<b>所以问题不是「浏览器切不出 64px 框」，是贴图用错了</b> ——
            现状的像素级复刻请以 <code>/test/ui</code> 为准，本稿不重复造这一块。</li>
        <li><b>本稿的处置</b>：新设计三个界面统一走 <code>(0,256,60,60)</code> 的 20px 九宫格
            —— 那是一块<b>规整的九宫格素材</b>，与气泡、按钮同族，顺带消掉
            <code>drawDialogueBox</code> 的 title-safe 裁切隐患。开关默认关闭，留着只为让这个坑可复现。</li>
        <li><b>落 C# 时完全不存在这个问题</b>：F8 本来就是一句现成的
            <code>Game1.drawDialogueBox(...)</code>，不需要自己切图。</li>
      </ul>
    </div>

    <div class="card">
      <h2>四、我的推荐（<span class="ok">本页默认值就是这一套</span>，可直接否决）</h2>
      <p>「美不美」我不想只给感觉，所以拆成四条可检验的判据：<b>层级是否一眼可读</b>（面板 / 内容区 /
         卡片三层要能分清）、<b>对比是否够用</b>（文字与底色的明度差）、<b>是否自洽</b>（同一层用同一种画法）、
         <b>有没有多余元素</b>（读不出含义的颜色、悬空的留白）。下面每条都按这四条给结论。</p>
      <table>
        <thead><tr><th>选择</th><th>我的推荐</th><th>为什么</th><th>备选</th></tr></thead>
        <tbody>
          <tr>
            <td>遮罩强度</td>
            <td><b>统一 28%</b></td>
            <td>比改前 F8 的 42% 轻（不压抑），但给了 F9 与中心「浮起来」的感觉（改前完全没有遮罩）。
                同一个数、三个界面 —— 最省事也最自洽。本稿最初写 26%，落地时定为
                <code>MenuSkinRules.ScrimAlpha = 0.28f</code>，本页已按落地值改齐</td>
            <td>按介入深度分档（F8 34% / 中心 26% / F9 18%）：更讲究，但多一个需要解释的规则</td>
          </tr>
          <tr>
            <td>F9 提示行</td>
            <td><b>优先挪到 header 右侧</b>，放不下才落底部留白</td>
            <td>header 右侧本来就是空的，提示行放那儿是「填空」而不是「占地」，
                <b>气泡区一点不损失</b>；底部留白那条带看起来像漏画了什么</td>
            <td>固定在底部留白（气泡区减 30px）：排障串一定放得下，代价是可见气泡少一条</td>
          </tr>
          <tr>
            <td>卡片「状态行被切断」</td>
            <td><b>三行并成两行，卡片几何一点不动</b></td>
            <td>这是四条判据里唯一「现状明确不合格」的一项：第三行文字底 +94 比卡片本身（92）还低，
                被下边框切断 —— 是缺陷不是风格。并成两行后第二行底 +72 正好落在内沿上</td>
            <td><b>卡片加高到 116 + 步进 128</b>：文字能保持三行，但 1280×720 与 1600×900 下
                每屏只能放 3 张（现在 4 张），而且 <code>invitationRows</code> 与按钮命中区全变
                —— 拿「少看一张邀约 + 点击坐标风险」换一行字的位置，我认为不划算</td>
          </tr>
          <tr>
            <td>F8 标题带高度</td>
            <td><b>92 → 56</b></td>
            <td>标题带只有一行字 + 一条线，92px 会让面板上半部分明显空虚；
                降到 56 后消息区上移 36px，720p 下能多放一条气泡 —— 又好看又实用</td>
            <td>保持 92：零风险，但那片空白会一直在</td>
          </tr>
          <tr>
            <td>F8 角色卡位置</td>
            <td><b>浮在右侧凹槽上</b>（当前）</td>
            <td>与中心界面的卡片是同一套语言：卡片浮在凹上。移出去会让 F8 多出一种别处没有的层次</td>
            <td>移出凹槽贴面板右侧，做成「面板上的第二张纸」</td>
          </tr>
          <tr>
            <td>次按钮文字色</td>
            <td><b>保持 <code>Color.Black</code></b></td>
            <td><code>DimGray</code> 在原版里是<b>禁用态</b>的语言（<code>MenuButtonDrawing.cs:35</code>），
                次按钮借用它会被误读成「点不了」。次按钮已经靠底色暗一档退后了</td>
            <td>用 DimGray —— 更弱，但会与禁用态混淆</td>
          </tr>
        </tbody>
      </table>
      <p><b>现状 vs 新设计，新设计赢在哪、输在哪</b>：赢在层级、自洽与噪音控制（凹槽让气泡跳出来、
        按钮两档让人知道该点哪个、标题带让结构完整）；<b>唯一输的是</b>原版 64px 切法的面板有一圈
        更厚的手绘木质边框，质感更足 —— 但那个质感只属于 F8，与另外两个界面不一致，所以值得牺牲。</p>
    </div>

    <div class="card">
      <h2>五、哪些是纯视觉，哪些会动点击坐标</h2>
      <table>
        <thead><tr><th>类别</th><th>改动</th><th>风险</th></tr></thead>
        <tbody>
          <tr>
            <td><span class="ok">纯视觉</span><br>布局与点击坐标都不动</td>
            <td>1 面板换绘制方式 · 2 内容区凹槽 · 3 标题带与分隔线 · 4 输入框高度与位置
                （<b>不改 <code>layout.InputBox</code></b>，只改 <code>inputBox</code> 的绘制矩形）·
                5 按钮 tint · 6 卡片分层 · 7 文字色 · 8 遮罩 · <b>9 卡片文字并两行</b>（只改
                <code>DrawString</code> 的坐标与拼接，卡片矩形与按钮命中区一个都不动）</td>
            <td>低。全部是「多画一层」「换一个颜色值」或「挪一行字」，所有 <code>Rectangle</code> 常量、
                所有 <code>Contains()</code> 判定用的矩形都保持原值</td>
          </tr>
          <tr>
            <td><span class="flag">改布局、不改点击坐标</span></td>
            <td>F9 提示行分离：只有当提示放不进 header 时，消息区可用高度才减 30px
                （<code>GroupDialogueMenu.draw</code> 的 break 条件）</td>
            <td>中低。短提示走 header 时气泡区<b>零影响</b>；长提示（排障串）时可见气泡少一条左右</td>
          </tr>
          <tr>
            <td><span class="flag">可选，会动点击坐标</span></td>
            <td>F8 的 <code>HeaderHeight</code> 92 → 56（第三节第 4 条）</td>
            <td>中。<code>messageArea.Y</code> 会上移 36px，气泡起点跟着上移。
                消息区本身不接收点击，所以只影响观感与滚动条轨道，但仍建议实机确认一次</td>
          </tr>
          <tr>
            <td><span class="ok">顺带发现，本次不动</span></td>
            <td>现状在 <b>1024×600</b> 下，中心界面第 4 张卡的底边在 y=522，而关闭按钮在 y=500
                —— <b>本来就压在按钮上</b>（实测，非本次引入）</td>
            <td>本次不处理，以免把「零几何改动」的干净边界弄脏。建议单独修：把可见张数改成由
                <code>closeButton.Y</code> 与行步进算出，上限仍是 4</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>六、与另一端的关系（不要重复劳动）</h2>
      <ul class="plain">
        <li>本页面<b>只画新设计</b>，不负责「现状的像素级真实」——那是 <code>/test/ui</code> 的职责，
            它那边正在把贴图换成解包出来的真实像素。本页的现状侧用同一套逻辑做<b>可比</b>复刻，
            数值以 <code>/test/ui</code> 为准。</li>
        <li>气泡：两侧共用回放页的 <code>_CHARACTER_FRAME_SCRIPT</code> 与
            <code>npc_bubble_elements</code> 表，本页<b>没有</b>任何气泡相关的尺寸或配色常量。
            气泡的九宫格贴图与 <code>/test/ui</code> 同源：<b>角色</b>取自
            <code>npc_bubble_texture.py</code>（描边色相已归一到填充色，否则深色 tint 下会围出
            一圈橙红的边），<b>玩家与兜底</b>取自 <code>npc_bubble_panel_plain.py</code>
            （未着色面板 + 反推 tint，否则浅蓝 / 浅紫会被木纹乘成橙棕）。
            角色的 <b>tint</b> 同样不在页面里算：服务端 <code>npc_bubble_tint.py</code> 按设计色
            反推后随 styles payload 下发（与 C# 导出同一公式），现状栏与新设计栏取同一个值 ——
            游戏侧画出来的就是设计色本身，两栏在这里没有差别。</li>
        <li>贴图：本页自带的原版贴图（<code>textBox</code> / <code>MenuTiles (0,256,60,60)</code> /
            <code>MenuTiles (0,0,256,256)</code>）从本机解包目录裁出后 base64 内联，
            气泡那两张与 <code>/test/ui</code> 一样<b>从服务端模块 import</b>、不各自复制一份，
            <b>不 import</b> <code>ui_preview_page.py</code>，两条线互不覆盖。</li>
      </ul>
    </div>
  </section>
</main>

<script id="ui-redesign-data" type="application/json">__DATA__</script>
<script>
(() => {
  const DATA = JSON.parse(document.getElementById("ui-redesign-data").textContent);
  const NPC_STYLES = DATA.styles;
  const SPEAKER_GLYPHS = DATA.glyphs;
  const CHARACTER_ORNAMENTS = DATA.ornaments;
  const NPC_ALIASES = DATA.aliases;
  const SAMPLE = DATA.sample;
  const GAME_TEX = DATA.tex;
  const GAME_TEX_BAKED = DATA.texBaked;

  const canonicalNpcId = (id) => Object.hasOwn(NPC_ALIASES, id) ? NPC_ALIASES[id] : id;
  const ornamentFor = (id) => Object.hasOwn(CHARACTER_ORNAMENTS, canonicalNpcId(id)) ? CHARACTER_ORNAMENTS[canonicalNpcId(id)] : null;
  const glyphFor = (id) => Object.hasOwn(SPEAKER_GLYPHS, canonicalNpcId(id)) ? SPEAKER_GLYPHS[canonicalNpcId(id)] : "";
  const styleFor = (id) => Object.hasOwn(NPC_STYLES, canonicalNpcId(id))
    ? NPC_STYLES[canonicalNpcId(id)]
    : { icon: "•", tone: "参与者", className: "guest", accent: "#a990ff", accentSoft: "#79d9db", bubble: "rgb(239,231,244)", border: "#576246" };

  // ── 回放页那套装饰边框（group_dialogue_review_page.py 的 _CHARACTER_FRAME_SCRIPT，原样复用）
__FRAME_SCRIPT__

  // ═══════════════════════════════════════════════════════════════════════
  // 原版贴图与颜色常量
  // ═══════════════════════════════════════════════════════════════════════
  const MENU_TEX = {
    src: GAME_TEX.menuButton,   // Maps\MenuTiles (0,256,60,60)，num = 20
    slice: 20,
    shadow: "drop-shadow(-8px 8px 0 rgba(0,0,0,.4))",
  };
  /**
   * 气泡专用九宫格 —— 切法与 MENU_TEX 完全一致，只换了**描边的色相**
   * （服务端预处理，见 npc_bubble_texture.py）。
   *
   * 原贴图的描边是红橙色（#b14e05，B 通道只有 5）：白 tint 的面板 / 按钮是木框本色，
   * 但角色气泡的 tint 是紫红 / 靛蓝这类深色，描边的 B 通道乘完仍 ≈2 —— 底色上就围了
   * 一圈橙红的边（截图实测：边框 rgb(73,13,2) vs 填充 rgb(104,32,36)）。
   * 归一后描边恒等于「填充最终色 × 同一亮度比例」，四档明暗与圆角形状一个像素没动。
   *
   * ⚠ 只有气泡用这一份；面板 / 按钮 / 凹槽继续用 MENU_TEX。
   * ⚠ 它没有预乘 tint 的版本（气泡 tint 按角色动态，命中不了 GAME_TEX_BAKED），
   *   调用处要显式传 `noBake: true`，否则万一 tint 撞上表里的 key 会取错贴图。
   */
  const BUBBLE_MENU_TEX = {
    src: DATA.bubbleTex,
    slice: MENU_TEX.slice,
    shadow: MENU_TEX.shadow,
  };

  /**
   * 玩家 / NPC 兜底气泡的九宫格 —— Maps\MenuTilesUncolored (0,256,60,60)。
   *
   * 切法与 MENU_TEX 完全一致，换的是**整块贴图**：未着色面板是彩色 MenuTiles 的去色版
   * （alpha 轮廓逐像素相同，底板色区从 #fdbc6e 换成近白 (248,248,248)）。
   *
   * 这两个气泡为什么必须换：彩色面板的基色 #fdbc6e 只有 G 188 / B 110，而浅蓝 (226,239,246) /
   * 浅紫 (239,231,244) 的 G / B 比基色还高（反推要 324 / 570）—— 乘法 tint 最多到 1.0 倍，
   * 乘不出来，直接当 tint 只会被橙黄木纹染成橙棕。近白面板下反推值落在 255 以内。
   *
   * ⚠ 只有这两个用它（ChatBubbleDrawing.cs:126-141 的 DrawPanel 分支）；角色气泡继续用
   *   BUBBLE_MENU_TEX。它同样没有预乘 tint 的版本，调用处一律传 noBake。
   */
  const PLAIN_MENU_TEX = {
    src: DATA.plainTex,
    slice: MENU_TEX.slice,
    shadow: MENU_TEX.shadow,
  };
  /** 两个设计色反推出来的 tint（ChatBubbleDrawing.cs:57,60，公式见 :178-193）。 */
  const PLAYER_BUBBLE_TINT = DATA.playerBubbleTint;
  const NPC_FALLBACK_BUBBLE_TINT = DATA.npcFallbackBubbleTint;
  /**
   * Maps\MenuTiles (0,0,256,256) —— F8 现状 `Game1.drawDialogueBox` 用的那一块。
   *
   * ⚠ 2026-09-20 逐像素量过：这一块**不是九宫格素材**，而是一整张画好的对话气泡 ——
   * 框体在 (16,16)-(239,239)，内部 y84–107 有一条标题分隔带、y128–187 是带纵向渐变的填充、
   * 底部中间 (88..103, 240) 还有气泡尾巴。所以它在浏览器里**没法被忠实切出来**：
   * 按 64px 九宫格切，四角会把框外那 16px 透明一起带上，画出来四角是缺的。
   * 这里保留它只是为了「与 /test/ui 的现状可比」，不宣称像素级一致 —— 落 C# 时
   * F8 本来就是一句现成的 `Game1.drawDialogueBox(...)`，不存在切图问题。
   */
  const DIALOGUE_TEX = {
    src: GAME_TEX.menuPanel,
    slice: 64,
    shadow: null,               // drawDialogueBox 不画投影
  };
  const GAME_BLACK = [0, 0, 0];
  const GAME_GRAY = [128, 128, 128];            // Color.Gray —— 按钮禁用 tint
  const DARK_SLATE_GRAY = [47, 79, 79];         // Color.DarkSlateGray —— **改前**的次级文字色（现状已统一到 InkSoft，这里只作记录）
  const DIM_GRAY = [105, 105, 105];             // Color.DimGray —— 新设计统一后的次级文字色
  const DARK_SLATE_BLUE = [72, 61, 139];
  const DARK_BUBBLE_TEXT = [243, 240, 252];     // ChatBubbleDrawing.DarkBubbleText
  const METER_BG = [206, 195, 180];             // ChatInputMenu.DrawProfile（好感度条底）
  const METER_FILL = [181, 137, 191];           // ChatInputMenu.DrawProfile（好感度条填充）

  // ── 外壳重构的「设计令牌」：全部是 tint（与纹理色逐通道相乘） ─────────────
  //
  // 基准：MenuTiles (0,256,60,60) 中心块的**主色**是 #fdbc6e（该块另有近邻色
  // #ffc576 / #f5b56f / #f5b565，下面几条是截图里逐点实测的采样值）、描边是 #b14e05（实测游戏截图）。
  // tint 只能让颜色变暗（相乘 ≤ 1），所以层级靠「向下分档」：
  //   面板（白 tint，最亮） → 内容区凹槽（暗一档） → 卡片/按钮回到白 tint（浮起来）
  const SKIN = {
    panel: [255, 255, 255],
    inset: [232, 228, 224],        // 凹槽：填充 → #e8b068，描边 → #a14604
    card: [255, 255, 255],
    btnPrimary: [255, 255, 255],
    btnSecondary: [238, 226, 208], // 次按钮：填充 → #eeb066
    btnDisabled: GAME_GRAY,
    ink: GAME_BLACK,
    inkSoft: DIM_GRAY,
    /**
     * 标题带底部的发丝分隔线。
     *
     * C# 是 `MenuSkinRules.RuleColor = new Color(150, 96, 48) * 0.55f`。
     * ⚠ **XNA 的 `Color * float` 把 RGB 与 alpha 一起乘**（Color.cs 的 operator*，逐通道
     * 相乘后 `(int)` 截断）：(150,96,48,255) × 0.55 → **Color(82, 52, 26, 140)**。
     * 而 SpriteBatch 的 AlphaBlend 是 `src = One / dst = InverseSourceAlpha`，
     * 且 tint 直接乘在 1×1 白纹理（Game1.fadeToBlackRect）上 ——
     * 所以网页上的等价写法是「**预乘后的 RGB** + alpha 140/255」，也就是下面的值。
     *
     * ⚠ 不要写成 `rgba(150,96,48,.55)` —— 那是「原色 + 55% 透明」，没把预乘算进去：
     * 叠在 #ffc576 面板上得 rgb(197,141,80)，比 C# 的 rgb(160,117,68) 亮 37 个色阶。
     * 写法与推导与 /test/ui 的 RULE_COLOR_CSS 同源（那边已按同一份换算写下）。
     */
    rule: [82, 52, 26], ruleAlpha: 140 / 255,
    // 整屏遮罩强度：C# 落地值是 MenuSkinRules.ScrimAlpha = 0.28f（三处 ChatInputMenu /
    // GroupDialogueMenu / GroupDialogueHubMenu 共用一句 DrawScrim）。
    // 本稿最初推荐 26%，落地时定为 28% —— 以 C# 为准，页面跟着改成同一个数。
    scrim: 0.28,
    // 卡片几何**一点不动**（92 / 104）。原本想让卡片加高到 116 来避开下边框，
    // 实测发现这条路走不通：九宫格 slice 20 意味着「面板 20 + 凹槽 20 + 卡片 20」三层边框，
    // 1280×720 下加高后每屏只能放 3 张（现在 4 张），1600×900 也一样 —— 拿「少看一张邀约」
    // 换一行字的位置，不值。改成**把三行压成两行**：行 1 在 +14（和现状一样压着上边框的
    // 图案，但那一行现在就不难看），行 2 在 +44，文字底 +72 正好等于九宫格内沿（92 − 20），
    // 于是「最后一行被下边框切断」这个真正的毛病消失，而几何与点击坐标零改动。
    cardHeight: 92, cardStep: 104,
    cardRow1Y: 14,
    cardStatusYLegacy: 66,      // 现状第三行：底 +94 > 卡片高 92 —— 文字直接画到卡片外面
    cardRow2YDesign: 44,        // 新设计第二行（主题 + 状态并成一行）：底 +72 = 内沿，刚好
  };

  const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
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

  // ═══════════════════════════════════════════════════════════════════════
  // 布局规则（逐条照抄 smapi/ 下的规则类；与 /test/ui 同源，本页不新增常数）
  // ═══════════════════════════════════════════════════════════════════════
  function centeredInViewport(vw, vh, pw, ph, floorOriginAtZero) {   // MenuPanelRules.cs:26-52
    let x = Math.trunc((vw - pw) / 2);
    let y = Math.trunc((vh - ph) / 2);
    if (floorOriginAtZero) { x = Math.max(0, x); y = Math.max(0, y); }
    return { x, y, w: pw, h: ph };
  }

  function chatLayout(vw, vh) {                                     // ChatLayoutRules.cs:31-143
    const SafeMargin = 24, MinimumPanelWidth = 760, MinimumPanelHeight = 420;
    const FooterHeight = 112, HeaderHeight = 92, ActionGap = 8;
    const ProfileWidth = 280, ProfileHeight = 112, MinimumConversationWidth = 240;
    const availableWidth = Math.max(1, vw - SafeMargin * 2);
    const availableHeight = Math.max(1, vh - SafeMargin * 2);
    const minimumWidth = Math.min(MinimumPanelWidth, availableWidth);
    const minimumHeight = Math.min(MinimumPanelHeight, availableHeight);
    const panelWidth = clamp(Math.round(vw * 0.68), minimumWidth, availableWidth);
    const panelHeight = clamp(Math.round(vh * 0.55), minimumHeight, availableHeight);
    const panel = centeredInViewport(vw, vh, panelWidth, panelHeight, false);
    const header = {
      x: panel.x + SafeMargin, y: panel.y + SafeMargin, w: panel.w - SafeMargin * 2,
      h: Math.min(HeaderHeight, Math.max(48, Math.trunc(panel.h / 4))),
    };
    const footer = {
      x: panel.x + SafeMargin,
      y: panel.y + panel.h - SafeMargin - Math.min(FooterHeight, Math.max(72, Math.trunc(panel.h / 3))),
      w: panel.w - SafeMargin * 2,
      h: Math.min(FooterHeight, Math.max(72, Math.trunc(panel.h / 3))),
    };
    const messageArea = {
      x: panel.x + SafeMargin, y: header.y + header.h + ActionGap,
      w: panel.w - SafeMargin * 2,
      h: Math.max(40, footer.y - (header.y + header.h) - ActionGap * 2),
    };
    const showProfile = messageArea.w >= MinimumConversationWidth + ProfileWidth + ActionGap;
    const profilePanel = showProfile ? {
      x: messageArea.x + messageArea.w - ProfileWidth, y: messageArea.y,
      w: ProfileWidth, h: Math.min(ProfileHeight, messageArea.h),
    } : null;
    const conversationArea = {
      x: messageArea.x, y: messageArea.y,
      w: showProfile ? messageArea.w - ProfileWidth - ActionGap : messageArea.w,
      h: messageArea.h,
    };
    const compactActions = footer.w < 600, veryCompactActions = footer.w < 420;
    const buttonGap = veryCompactActions ? 4 : compactActions ? 6 : ActionGap;
    const sendWidth = veryCompactActions ? 56 : compactActions ? 72 : 96;
    const topicWidth = veryCompactActions ? 72 : compactActions ? 96 : 128;
    const inventoryWidth = veryCompactActions ? 62 : compactActions ? 84 : 104;
    const closeWidth = veryCompactActions ? 56 : compactActions ? 72 : 96;
    const closeButton = { x: footer.x + footer.w - closeWidth, y: footer.y, w: closeWidth, h: footer.h };
    const inventoryButton = { x: closeButton.x - buttonGap - inventoryWidth, y: footer.y, w: inventoryWidth, h: footer.h };
    const topicButton = { x: inventoryButton.x - buttonGap - topicWidth, y: footer.y, w: topicWidth, h: footer.h };
    const sendButton = { x: topicButton.x - buttonGap - sendWidth, y: footer.y, w: sendWidth, h: footer.h };
    const inputBox = { x: footer.x, y: footer.y, w: Math.max(120, sendButton.x - footer.x - buttonGap), h: footer.h };
    return { panel, header, footer, messageArea, conversationArea, profilePanel, inputBox, sendButton, topicButton, inventoryButton, closeButton };
  }

  function groupLayout(vw, vh) {                                    // GroupDialogueLayoutRules.cs:30-77
    const SafeMargin = 24, FooterHeight = 104, HeaderHeight = 118, ActionGap = 8;
    let panelWidth = Math.min(1120, Math.max(680, vw - SafeMargin * 2));
    let panelHeight = Math.min(720, Math.max(430, vh - SafeMargin * 2));
    panelWidth = Math.min(panelWidth, Math.max(1, vw - SafeMargin * 2));
    panelHeight = Math.min(panelHeight, Math.max(1, vh - SafeMargin * 2));
    const panel = centeredInViewport(vw, vh, panelWidth, panelHeight, true);
    const header = { x: panel.x, y: panel.y, w: panel.w, h: Math.min(HeaderHeight, panel.h) };
    const footerY = Math.max(header.y + header.h, panel.y + panel.h - Math.min(FooterHeight, panel.h));
    const footer = { x: panel.x + 20, y: footerY, w: Math.max(1, panel.w - 40), h: Math.max(1, panel.y + panel.h - footerY) };
    const participantStrip = {
      x: header.x + 20, y: header.y + header.h - 48, w: Math.max(1, header.w - 40),
      h: Math.min(32, Math.max(1, header.h - 20)),
    };
    const messageArea = {
      x: panel.x + 20, y: header.y + header.h, w: Math.max(1, panel.w - 40),
      h: Math.max(1, footer.y - (header.y + header.h) - 12),
    };
    const closeWidth = 88, retryWidth = 88, sendWidth = 88;
    const closeButton = { x: footer.x + footer.w - closeWidth, y: footer.y, w: closeWidth, h: footer.h };
    const retryButton = { x: closeButton.x - ActionGap - retryWidth, y: footer.y, w: retryWidth, h: footer.h };
    const sendButton = { x: retryButton.x - ActionGap - sendWidth, y: footer.y, w: sendWidth, h: footer.h };
    const inputBox = { x: footer.x, y: footer.y, w: Math.max(120, sendButton.x - footer.x - ActionGap), h: footer.h };
    return { panel, header, footer, participantStrip, messageArea, inputBox, sendButton, retryButton, closeButton };
  }

  function hubLayout(vw, vh) {                                      // GroupDialogueHubLayoutRules.cs:13-30
    const SafeMargin = 24;
    let panelWidth = Math.min(1080, Math.max(680, vw - SafeMargin * 2));
    let panelHeight = Math.min(680, Math.max(440, vh - SafeMargin * 2));
    panelWidth = Math.min(panelWidth, Math.max(1, vw - SafeMargin * 2));
    panelHeight = Math.min(panelHeight, Math.max(1, vh - SafeMargin * 2));
    const panel = centeredInViewport(vw, vh, panelWidth, panelHeight, true);
    return { panel, closeButton: { x: panel.x + panel.w - 180, y: panel.y + panel.h - 76, w: 148, h: 56 } };
  }

  // MenuSkinRules.HubTitleBandHeight —— smapi/MenuSkinRules.cs:237
  // 群聊中心标题带的固定高度，C# 直接拿它当 DrawTitleBand 的 header 高：
  //   new Rectangle(panel.X, panel.Y, panel.Width, HubTitleBandHeight)
  // 分隔线因此落在 panel.Y + 74 − 14 = panel.Y + 60（TitleRule 的 RuleBottomOffset）。
  const HUB_TITLE_BAND_HEIGHT = 74;

  // MenuSkinRules.MessageBubbleAreaHeight —— smapi/MenuSkinRules.cs
  // F9 长提示（"无可用回复(fb=… n=… spk=[…])" 那种排障串）放不下 header，回落到消息区下方并
  // 占用 HintFallbackReserve = 30px，气泡区因此矮 30；短提示放 header 右侧，气泡区零损失。
  // 与 /test/ui 同一份实现（两页必须逐值相同，否则凹槽底边对不上）。
  function messageBubbleAreaHeight(messageAreaHeight, hintInHeader) {
    return hintInHeader
      ? messageAreaHeight
      : Math.min(messageAreaHeight, Math.max(60, messageAreaHeight - 30));
  }

  // MenuSkinRules.HubListArea —— smapi/MenuSkinRules.cs
  // 邀约列表凹槽：卡片浮在它上面，靠底色分档分层（卡片自身的 tint 不动）。
  // 凹槽矩形与底部参考线共用这一处定义（此前两处各写一遍，参考线那份还漏了 max(40,…)）。
  function hubListArea(panel, closeButton) {
    const top = panel.y + HUB_TITLE_BAND_HEIGHT;   // HubListTopOffset = 74
    const bottom = closeButton.y - 44;             // HubListBottomGap = 44
    return {
      x: panel.x + 24,                             // HubListMargin = 24
      y: top,
      w: Math.max(1, panel.w - 48),
      h: Math.max(40, bottom - top),               // HubListMinimumHeight = 40
    };
  }

  const INVITATION_BUTTON = { width: 64, gap: 6, height: 52, topOffset: 18 };   // GroupInvitationActionLayoutRules.cs:15-18
  const actionRowX = (row) => row.x + row.w - INVITATION_BUTTON.width * 3 - INVITATION_BUTTON.gap * 2;
  const actionButtonAt = (row, index) => ({
    x: actionRowX(row) + (INVITATION_BUTTON.width + INVITATION_BUTTON.gap) * index,
    y: row.y + INVITATION_BUTTON.topOffset, w: INVITATION_BUTTON.width, h: INVITATION_BUTTON.height,
  });

  // ── 文本度量（与 /test/ui 同一套：canvas 按页面字体量，保证断行与 DOM 一致）──
  const GAME_FONT_CSS = '17.5px "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif';
  const measureCtx = (() => {
    try {
      const ctx = document.createElement("canvas").getContext("2d");
      ctx.font = GAME_FONT_CSS;
      return ctx;
    } catch (error) { return null; }
  })();
  const measureText = (value) => {
    const text = String(value);
    if (measureCtx) return measureCtx.measureText(text).width;
    let w = 0;
    for (const ch of text) w += /[\u2E80-\uFFE6]/.test(ch) ? 17.5 : 8.75;
    return w;
  };

  function wrapText(text, maxWidth) {                               // ChatTextLayoutRules.cs:8-42
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

  // ── 盒模型与着色工具 ───────────────────────────────────────────────────
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
   * 原版的 tint 是 `SpriteBatch.Draw(tex, ..., tint)`，最终色 = 纹理色 × tint ÷ 255（逐通道、alpha 不变）。
   * border-image 不能着色，用 feColorMatrix 做同一条对角乘法（与 /test/ui 同法：
   * 试过 mix-blend-mode: multiply，但贴图透明处会退化成纯 tint 色，边角多出一圈白边）。
   */
  const tintFilterCache = new Map();
  function tintFilter(tintColor) {
    if (!tintColor || (tintColor[0] === 255 && tintColor[1] === 255 && tintColor[2] === 255)) return "";
    const key = tintColor.join("-");
    const cached = tintFilterCache.get(key);
    if (cached !== undefined) return cached;
    const id = "rtint-" + key;
    if (!document.getElementById(id)) {
      const ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");
      svg.setAttribute("width", "0"); svg.setAttribute("height", "0");
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

  /** IClickableMenu.drawTextureBox 的逐块同构：四角 20×20 原样、边与中心拉伸。 */
  function nineSlice(parent, r, tintColor, texture, options) {
    const tex = texture || MENU_TEX;
    const opts = options || {};
    const tint = tintColor || [255, 255, 255];
    const el = rectEl(parent, r, "nine");
    el.style.borderWidth = tex.slice + "px";
    // 外壳的 tint 是固定的三四个值，贴图在服务端就把 tint 乘进像素了（GAME_TEX_BAKED），
    // 所以这些框**不带任何 filter** —— 滤镜在部分浏览器 / GPU 合成路径下会被忽略或按
    // linearRGB 计算（表现为颜色不对），配合 transform 缩放还可能有边框重采样错位。
    // 只有气泡那种按角色动态的 tint 找不到预乘贴图，才回退到 feColorMatrix；
    // 气泡另用 BUBBLE_MENU_TEX（描边色相已归一），调用处传 noBake 以免误取这里的预乘贴图。
    const baked = opts.noBake ? null : GAME_TEX_BAKED[tint.join(",")];
    el.style.borderImage = `url("${baked || tex.src}") ${tex.slice} fill stretch`;
    // 凹槽不投影（drawTextureBox 的 drawShadow: false）—— 这是「干净」的关键：
    // 凹陷的纸面不该有影子，只有浮起来的东西才投影。
    const shadow = opts.noShadow ? null : tex.shadow;
    const filter = [baked ? "" : tintFilter(tint), shadow].filter(Boolean).join(" ");
    if (filter) el.style.filter = filter;
    if (opts.z !== undefined) el.style.zIndex = String(opts.z);
    return el;
  }

  /** MenuButtonDrawing.DrawButton —— smapi/MenuButtonDrawing.cs:22-36 */
  function button(parent, r, label, enabled, tintColor) {
    const el = nineSlice(parent, r, enabled ? (tintColor || SKIN.btnPrimary) : SKIN.btnDisabled, MENU_TEX, { z: 3 });
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

  /** 输入区凹槽（新设计）：输入框浮在其中的一层凹陷纸面。 */
  function inputWell(parent, r) {
    return nineSlice(parent, r, SKIN.inset, MENU_TEX, { noShadow: true, z: 2 });
  }

  // ── 气泡（ChatBubbleDrawing.Draw）：尺寸、换行、几何一律不动 ─────────
  const BUBBLE = { padding: 12, lineSpacing: 4, gap: 20, safetyMargin: 8, minWidth: 180 };
  const LINE_SPACING = 28;   // 游戏字体行高（⚠ 由气泡高度反推，与 /test/ui 同值）

  // 角色气泡的 tint 由服务端反推好（npc_bubble_tint.py，与 C# 导出同一公式），
  // 页面只消费 payload 里的 bubbleTint，不再自留公式与基准色。
  //
  // 气泡底色 = `drawTextureBox(MenuTiles, tint)` 的「纹理色 × tint ÷ 255」。
  // `npc_bubble_elements.py` 的 `palette.bubble` 是**设计色**（回放页直接铺的最终色），
  // 直接当 tint 用会被橙黄木纹再乘一次 —— Sophia 的品红 (105,43,84) 渲染成暗红 (104,32,36)
  // （色相从 hue 320 偏到 ≈355），Abigail 的 (65,44,109) 渲染成 (64,32,47)。
  // 游戏侧（NpcBubbleStyle.Bubble）用的就是反推值，所以现状栏与新设计栏都跟着用同一个值 ——
  // 「现状栏保持原样」的旧做法会让本页两栏自相矛盾，也会与 /test/ui 不一致。

  function measureBubbleHeight(lineCount, lineSpacingPx) {          // ChatBubbleDrawing.MeasureHeight
    const n = lineCount <= 0 ? 1 : lineCount;
    return BUBBLE.padding * 2 + lineSpacingPx + BUBBLE.lineSpacing + n * lineSpacingPx + (n - 1) * BUBBLE.lineSpacing;
  }
  const contentWidthFor = (available) => Math.max(80, available - BUBBLE.padding * 2 - BUBBLE.safetyMargin);

  function drawBubble(stage, left, right, y, speaker, content, npcId, isPlayer, occurrence) {
    const availableWidth = Math.max(BUBBLE.minWidth, right - left);
    const lines = wrapText(content, contentWidthFor(availableWidth));
    if (lines.length === 0) return 0;
    const textWidth = Math.max(...lines.map(measureText));
    const width = clamp(Math.ceil(textWidth + BUBBLE.padding * 2), Math.min(BUBBLE.minWidth, availableWidth), availableWidth);
    const height = measureBubbleHeight(lines.length, LINE_SPACING);
    const bounds = { x: isPlayer ? right - width : left, y, w: width, h: height };

    const style = isPlayer ? null : styleFor(npcId);
    // 玩家与「表里没有专属配色的 NPC」走未着色面板 + 反推 tint（ChatBubbleDrawing.cs:126-141
    // 的 DrawPanel 分支）：彩色面板的基色 #fdbc6e 只有 G 188 / B 110，乘不出这两个浅色
    // （见 PLAIN_MENU_TEX）。这一条与「现状 / 新设计」无关 —— 游戏侧本来就这么画，两栏都照做。
    const plain = isPlayer || !Object.hasOwn(NPC_STYLES, canonicalNpcId(npcId));
    // 角色专属配色：palette.bubble 是**设计色**，喂给彩色面板的是 payload 里反推好的 tint
    // （见上面的说明）。两栏取同一个值 —— 游戏侧画出来的就是设计色本身。
    const bubbleTint = plain
      ? (isPlayer ? PLAYER_BUBBLE_TINT : NPC_FALLBACK_BUBBLE_TINT)
      : style.bubbleTint;
    // 贴图与 tint 必须配套（见两个常量的说明）。
    // noBake：这两张都没有预乘 tint 的版本，不能落进 GAME_TEX_BAKED 的分支。
    const el = nineSlice(stage, bounds, bubbleTint, plain ? PLAIN_MENU_TEX : BUBBLE_MENU_TEX, { z: 4, noBake: true });
    el.dataset.bubble = npcId || "player";

    const ornament = (isPlayer || !npcId) ? null : ornamentFor(npcId);
    if (ornament) {
      const frame = document.createElement("span");
      frame.className = "bubble-frame";
      frame.setAttribute("aria-hidden", "true");
      // ⚠ 挂到 stage 上，不要 append 进 el：el 带 tint 的 feColorMatrix（动态气泡 tint 命中不了
      //   GAME_TEX_BAKED，走 tintFilter 回退），filter 会连带后代一起乘，绿叶会被染成暗紫红。
      //   几何按 bounds 显式给出，与原来「padding box + inset -34px」逐像素等价。
      frame.style.left = (bounds.x - 14) + "px";
      frame.style.top = (bounds.y - 14) + "px";
      frame.style.width = (bounds.w + 28) + "px";
      frame.style.height = (bounds.h + 28) + "px";
      frame.innerHTML = characterFrameSvg(bounds.w, bounds.h, ornament, occurrence);
      stage.append(frame);
    }

    const showBadge = Boolean(style && glyphFor(npcId));
    const textLeft = bounds.x + BUBBLE.padding;
    let speakerLeft = textLeft;
    if (showBadge) {
      const badge = document.createElement("span");
      badge.className = "bubble-badge abs";
      badge.style.left = textLeft + "px";
      badge.style.top = (bounds.y + BUBBLE.padding) + "px";
      badge.style.color = rgb(parseColor(style.accent, [255, 255, 255]));
      badge.style.zIndex = "7";
      badge.innerHTML = glyphFor(npcId);
      stage.append(badge);
      speakerLeft = textLeft + 24 + 6;
    }

    const nameEl = document.createElement("div");
    nameEl.className = "g bubble-name";
    nameEl.style.left = speakerLeft + "px";
    nameEl.style.top = (bounds.y + BUBBLE.padding) + "px";
    nameEl.style.color = rgb(isPlayer ? DARK_SLATE_BLUE : parseColor(style.accent, [255, 255, 255]));
    nameEl.style.zIndex = "7";
    nameEl.textContent = speaker;
    stage.append(nameEl);

    const bodyColor = (isPlayer || !style) ? GAME_BLACK : DARK_BUBBLE_TEXT;
    let lineY = bounds.y + BUBBLE.padding + LINE_SPACING + BUBBLE.lineSpacing;
    for (const line of lines) {
      const lineEl = document.createElement("div");
      lineEl.className = "g bubble-line";
      lineEl.style.left = textLeft + "px";
      lineEl.style.top = lineY + "px";
      lineEl.style.color = rgb(bodyColor);
      lineEl.style.zIndex = "7";
      lineEl.textContent = line;
      stage.append(lineEl);
      lineY += LINE_SPACING + BUBBLE.lineSpacing;
    }
    return height;
  }

  // ── 输入框 ─────────────────────────────────────────────────────────────
  /**
   * 现状：原版 TextBox.Draw 的横向三片 + 「源矩形高写成 Height」的 clamp 产物。
   * H > 48 时，v > 1 的采样被 GPU clamp 到贴图末行 (57,54,65,66) —— 26% 冷灰，
   * 与暖橙面板相乘就是实测的米褐色 rgb(190,140,93)。这就是「那条深色带」。
   */
  function textBoxLegacy(parent, r) {
    const el = rectEl(parent, r);
    el.style.zIndex = "3";
    el.style.background = "rgba(57,54,65,.2588)";
    const cap = document.createElement("div");
    cap.className = "abs";
    cap.style.cssText = "left:0;top:0;width:100%;height:" + Math.min(48, r.h) + "px;border-style:solid;border-width:0 16px;";
    cap.style.borderImage = `url("${GAME_TEX.textBox}") 0 16 0 16 fill stretch`;
    el.append(cap);
    el.dataset.legacyInput = "1";
    return el;
  }

  /**
   * 新设计：输入框本体只画 48px（= 贴图高度，1:1 采样，clamp 不触发），
   * 在输入区凹槽里垂直居中。
   *
   * C# 落法：`inputBox.Height = 48; inputBox.Y = layout.InputBox.Y + 32;`
   * —— 只动 TextBox 的**绘制**矩形，`receiveLeftClick` 仍用 `layout.InputBox.Contains`。
   */
  function textBoxDesign(parent, wellRect) {
    const h = 48;
    const r = {
      x: wellRect.x + 12,
      y: wellRect.y + Math.trunc((wellRect.h - h) / 2),
      w: Math.max(80, wellRect.w - 24),
      h,
    };
    const el = rectEl(parent, r);
    el.style.zIndex = "3";
    el.style.borderStyle = "solid";
    el.style.borderWidth = "0 16px";
    el.style.borderImage = `url("${GAME_TEX.textBox}") 0 16 0 16 fill stretch`;
    return { el, rect: r };
  }

  /** TextBox 的光标：Rectangle(X + 16 + textWidth + 2, Y + 8, 4, 32)，静态版。 */
  function caret(parent, r) {
    const el = rectEl(parent, r);
    el.style.background = rgb(GAME_BLACK);
    el.style.zIndex = "5";
    return el;
  }

  /** 标题带：强调色竖条 + 标题 + 右侧状态 + 发丝分隔线（三个界面同一套）。 */
  function titleBand(stage, header, title, status, accent) {
    const barX = header.x + 12, barY = header.y + 12;
    const bar = rectEl(stage, { x: barX, y: barY, w: 4, h: 20 });
    bar.style.background = rgb(accent);
    bar.style.zIndex = "5";
    // data-band：与 /test/ui 同一套锚点，用来逐值核对两个页面（值就是 MenuSkinRules 的令牌名）
    bar.dataset.band = "bar";
    const titleEl = textAt(stage, barX + 12, barY - 3, title, SKIN.ink);
    titleEl.style.zIndex = "5";
    titleEl.dataset.band = "title";
    if (status) {
      const statusEl = textAt(stage, barX + 12 + Math.ceil(measureText(title)) + 16, barY - 1, status, SKIN.inkSoft, "g-sm");
      statusEl.style.zIndex = "5";
      statusEl.dataset.band = "status";
    }
    // 发丝分隔线 MenuSkinRules.TitleRule(header) = (header.X+12, header.Bottom-14,
    // header.W-24, RuleHeight = 2)；颜色取上面预乘过的 SKIN.rule / ruleAlpha。
    const rule = rectEl(stage, { x: header.x + 12, y: header.y + header.h - 14, w: Math.max(1, header.w - 24), h: 2 });
    rule.style.background = `rgba(${SKIN.rule[0]},${SKIN.rule[1]},${SKIN.rule[2]},${SKIN.ruleAlpha})`;
    rule.style.zIndex = "5";
    rule.dataset.band = "rule";
  }

  /** 遮罩（MenuSkinDrawing.DrawScrim：Color.Black * MenuSkinRules.ScrimAlpha）。 */
  function scrim(stage, vw, vh, alpha) {
    if (alpha <= 0) return;
    const el = document.createElement("div");
    el.className = "scrim";
    el.style.opacity = String(alpha);
    el.style.zIndex = "0";
    stage.append(el);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════════════════════════════
  const OPT = {};
  const state = { view: "chat", width: 1280, height: 720, mode: "side", guides: false, risk: false };
  const guides = [];

  function addGuides(parent, rects) {
    if (!state.guides) return;
    for (const [name, r] of rects) {
      if (!r) continue;
      const el = rectEl(parent, r, "guide");
      el.style.zIndex = "30";
      const tag = document.createElement("b");
      tag.textContent = name;
      el.append(tag);
    }
  }

  function addRisk(parent, r, label) {
    if (!state.risk) return;
    const el = rectEl(parent, r, "risk");
    el.style.zIndex = "31";
    const tag = document.createElement("b");
    tag.textContent = label;
    el.append(tag);
  }

  /** 现状侧的「这里有问题」标注（蓝色虚线，跟随「标出会改点击坐标」那个开关）。 */
  function addNote(parent, r, label) {
    if (!state.risk || !r) return;
    const el = rectEl(parent, r, "risk note");
    el.style.zIndex = "29";
    const tag = document.createElement("b");
    tag.textContent = label;
    el.append(tag);
  }

  // ── F8 私聊 ────────────────────────────────────────────────────────────
  function renderChat(stage, vw, vh, design) {
    const L = chatLayout(vw, vh);
    const s = SAMPLE.chat;
    guides.length = 0;

    // 遮罩：F8（ChatInputMenu.DrawBackdrop）、F9、中心三处**都画**同一层
    // MenuSkinDrawing.DrawScrim（Color.Black * MenuSkinRules.ScrimAlpha = 0.28f）；
    // 改前 F8 是 0.42f、F9 与中心完全没有遮罩。
    // 「统一轻遮罩」开关只作用在新设计栏，关掉 = 不做这一层（仅用于对照）。
    scrim(stage, vw, vh, (!design || OPT.scrim) ? SKIN.scrim : 0);
    // F8 用哪套框：
    //   · 现状侧（左侧那栏）—— 用规整的 20px 九宫格 + 关掉投影，表现「drawDialogueBox 没有投影」
    //     这一条可确定的差异。**不**照切 (0,0,256,256)，因为那块不是九宫格素材、切出来会整片错位
    //     （见下方第三节）。现状的像素级复刻请对照 /test/ui。
    //   · 新设计侧 —— 跟随开关；默认同样 20px。勾上开关才切 64px，只为把那个坑复现出来。
    const useDialogueFrame = Boolean(design && OPT.f8frame);
    nineSlice(stage, L.panel, SKIN.panel,
      useDialogueFrame ? DIALOGUE_TEX : MENU_TEX,
      useDialogueFrame ? { z: 1, noShadow: true, noBake: true } : { z: 1, noShadow: !design });

    // 标题带（ChatInputMenu.DrawHeader → MenuSkinDrawing.DrawTitleBand）：
    // 竖条 (header.X+12, header.Y+12, 4, 20) + 标题 (header.X+24, header.Y+9)
    // + 状态字 + 发丝线 (header.X+12, header.Bottom-14, header.W-24, 2)。
    // ChatLayoutRules 的两个开关现在都是 true，所以**现状栏也照实机画**；
    // 新设计栏跟随「标题带 + 分隔线」开关。
    if (!design || OPT.title) {
      titleBand(stage, L.header, `和 ${s.npc} 聊聊`,
        s.hearts ? `好感度 ${s.hearts} 心` : "好感度未知",
        parseColor(styleFor(s.npc).accent, [176, 146, 242]));
    }

    // 内容区凹槽（MenuSkinDrawing.DrawInset(b, layout.MessageArea)）：整个 messageArea
    // （含右侧角色卡）是一层凹陷纸面，气泡与角色卡浮在它上面。
    // ⚠ 现状栏也画：C# 已落地这一层，现状栏是「照实机」的（与遮罩、标题带同一条规矩）；
    //   「内容区凹槽」开关只关新设计栏的那一层，用于对照。
    if (!design || OPT.inset) {
      nineSlice(stage, L.messageArea, SKIN.inset, MENU_TEX, { noShadow: true, z: 2 })
        .dataset.inset = "message";
    }

    const area = L.conversationArea;
    const maxWidth = Math.max(80, area.w - 12 * 2 - 12 - 8);          // ChatInputMenu.DrawMessages 的 maxWidth
    const fixedHeight = 12 * 2 + LINE_SPACING + 4;
    const availableHeight = Math.max(1, area.h - 12 * 2 - 8);
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
    let y = area.y + 12;
    for (const message of selected) {
      const isPlayer = message.role === "player";
      const drawn = drawBubble(stage, area.x + 12, area.x + area.w - 12, y,
        isPlayer ? "你" : s.npc, message.text, isPlayer ? null : s.npc, isPlayer, 0);
      if (!drawn) continue;
      if (y + drawn > area.y + area.h - 12) break;
      y += drawn + BUBBLE.gap;
    }
    if (s.hint) textAt(stage, area.x + 12, y, s.hint, GAME_GRAY, "g-sm").style.zIndex = "5";

    if (L.profilePanel) {
      const p = L.profilePanel;
      nineSlice(stage, p, design ? SKIN.card : [248, 240, 224], MENU_TEX, { z: 3 });
      const portraitFrame = { x: p.x + 12, y: p.y + Math.trunc((p.h - 64) / 2), w: 64, h: 64 };
      nineSlice(stage, { x: portraitFrame.x - 6, y: portraitFrame.y - 6, w: portraitFrame.w + 12, h: portraitFrame.h + 12 },
        SKIN.panel, MENU_TEX, { z: 4 });
      const ph = document.createElement("div");
      ph.className = "abs";
      ph.style.cssText = `left:${portraitFrame.x}px;top:${portraitFrame.y}px;width:64px;height:64px;`
        + "display:grid;place-items:center;z-index:5;"
        + `background:${rgb(parseColor(styleFor(s.npc).bubble, [239, 231, 244]))};`
        + `color:${rgb(parseColor(styleFor(s.npc).accent, [255, 255, 255]))}`;
      const holder = document.createElement("span");
      holder.style.cssText = "display:block;width:32px;height:32px";
      holder.innerHTML = glyphFor(s.npc);
      if (holder.firstElementChild) {
        holder.firstElementChild.setAttribute("width", "32");
        holder.firstElementChild.setAttribute("height", "32");
      }
      ph.append(holder);
      stage.append(ph);

      const infoX = portraitFrame.x + portraitFrame.w + 12;
      textAt(stage, infoX, p.y + 22, s.npc, SKIN.ink).style.zIndex = "5";
      textAt(stage, infoX, p.y + 22 + 28, `好感度 ${s.hearts} 心`,
        SKIN.inkSoft).style.zIndex = "5";
      const meter = { x: infoX, y: p.y + p.h - 12 - 10, w: p.x + p.w - infoX - 12, h: 10 };
      rectEl(stage, meter).style.cssText += `background:${rgb(METER_BG)};z-index:5`;
      const filled = Math.round(meter.w * clamp(s.hearts / 10, 0, 1));
      if (filled > 0) {
        rectEl(stage, { x: meter.x, y: meter.y, w: filled, h: meter.h })
          .style.cssText += `background:${rgb(METER_FILL)};z-index:6`;
      }
    }

    // 底部：新设计里输入区是一层凹槽，输入框在其中居中
    if (design) {
      if (OPT.input) {
        inputWell(stage, L.inputBox);
        const box = textBoxDesign(stage, L.inputBox);
        caret(stage, { x: box.rect.x + 16, y: box.rect.y + 8, w: 4, h: 32 });
      } else {
        textBoxLegacy(stage, L.inputBox);
        caret(stage, { x: L.inputBox.x + 16, y: L.inputBox.y + 8, w: 4, h: 32 });
      }
      button(stage, L.sendButton, "发送", true, SKIN.btnPrimary);
      button(stage, L.topicButton, "找话题", true, SKIN.btnSecondary);
      button(stage, L.inventoryButton, "物品", true, SKIN.btnSecondary);
      button(stage, L.closeButton, "结束", true, SKIN.btnSecondary);
    } else {
      textBoxLegacy(stage, L.inputBox);
      caret(stage, { x: L.inputBox.x + 16, y: L.inputBox.y + 8, w: 4, h: 32 });
      button(stage, L.sendButton, "发送", true, [235, 246, 236]);
      button(stage, L.topicButton, "找话题", true, [239, 231, 244]);
      button(stage, L.inventoryButton, "物品", true, [235, 240, 246]);
      button(stage, L.closeButton, "结束", true, [247, 232, 227]);
    }

    guides.push(["Panel", L.panel], ["Header", L.header], ["MessageArea", L.messageArea],
      ["ConversationArea", L.conversationArea], ["ProfilePanel", L.profilePanel],
      ["InputBox", L.inputBox], ["Send", L.sendButton], ["Topic", L.topicButton],
      ["Inventory", L.inventoryButton], ["Close", L.closeButton]);
    addGuides(stage, guides);
    return `消息区放得下 ${selected.length} / ${s.messages.length} 条（取窗逻辑 ChatTextLayoutRules.SelectLatestThatFit）`;
  }

  // ── F9 群聊 ────────────────────────────────────────────────────────────
  function renderGroup(stage, vw, vh, design) {
    const L = groupLayout(vw, vh);
    const s = SAMPLE.group;
    guides.length = 0;

    // 遮罩：F8 / F9 / 中心三处都画（MenuSkinDrawing.DrawScrim，MenuSkinRules.ScrimAlpha = 0.28f）；
    // 改前 F9 与中心完全没有遮罩、F8 是 0.42f。
    // 「统一轻遮罩」开关只作用在新设计栏，关掉 = 不做这一层（仅用于对照）。
    scrim(stage, vw, vh, (!design || OPT.scrim) ? SKIN.scrim : 0);
    nineSlice(stage, L.panel, SKIN.panel, MENU_TEX, { z: 1 });

    // 标题带（GroupDialogueMenu.draw:170-175 → MenuSkinDrawing.DrawTitleBand）：与 F8 同一句，
    // 强调色取第一位参与者；参与者行在 header 里另一条基线上，走 InkSoft（= DimGray）。
    // 改前标题只是 (header.X+12, header.Y+10) 的一行裸文字，既没有竖条也没有分隔线。
    if (!design || OPT.title) {
      titleBand(stage, L.header, "线上多人对话", null,
        parseColor(styleFor(s.participants[0]).accent, [176, 146, 242]));
    }
    textAt(stage, L.participantStrip.x, L.participantStrip.y, s.participants.join("、"), SKIN.inkSoft).style.zIndex = "5";

    const area = L.messageArea;
    const bubbleLeft = area.x + 12, bubbleRight = area.x + area.w - 12;

    // 提示行放哪：**短提示**（正常态）放 header 右侧、与参与者条同一行 —— 气泡区零损失；
    // **长提示**（"无可用回复(fb=… n=… spk=[…])" 那种排障串）放不下 header，就回到底部留白。
    // 这一条是这次改动里唯一动了气泡可用高度的分支，且只在长提示时才触发。
    const namesWidth = Math.ceil(measureText(s.participants.join("、")));
    const headerHintSpace = L.participantStrip.w - namesWidth - 24;
    // ⚠ 这一对与「内容区凹槽」开关**解耦**：C# 里提示行分支与气泡区高度都无条件算
    //   （GroupDialogueMenu.draw → HintNeedsBottomRow / MessageBubbleAreaHeight），
    //   凹槽高度又吃 bubbleAreaH，绑在一起会让「关掉凹槽」顺带改掉气泡区高度与断点。
    const hintInHeader = Boolean(s.hint && measureText(s.hint) <= headerHintSpace);
    const bubbleAreaH = messageBubbleAreaHeight(area.h, hintInHeader);

    // 内容区凹槽（MenuSkinDrawing.DrawInset(messageArea.X, messageArea.Y, messageArea.Width,
    // bubbleAreaHeight)）：气泡浮在它上面；高度取气泡区实际可用高度（长提示时减 30）。
    // 现状栏也画（同上一条理由）。
    if (!design || OPT.inset) {
      nineSlice(stage, { x: area.x, y: area.y, w: area.w, h: bubbleAreaH },
        SKIN.inset, MENU_TEX, { noShadow: true, z: 2 }).dataset.inset = "groupMessage";
    }
    let y = area.y + 12;
    const seen = new Map();
    const visible = s.messages.slice(-10);        // GroupDialogueLayoutRules.cs:28
    let drawnCount = 0;
    for (const message of visible) {
      const speakerKey = message.npcId;
      const occurrence = seen.get(speakerKey) || 0;
      seen.set(speakerKey, occurrence + 1);
      const isPlayer = message.role === "player";
      const drawn = drawBubble(stage, bubbleLeft, bubbleRight, y,
        isPlayer ? "玩家" : speakerKey, message.text, isPlayer ? null : speakerKey, isPlayer, occurrence);
      if (!drawn) continue;
      drawnCount++;
      y += drawn + BUBBLE.gap;
      if (y > area.y + bubbleAreaH - LINE_SPACING) break;
    }

    if (design) {
      if (OPT.input) {
        inputWell(stage, L.inputBox);
        const box = textBoxDesign(stage, L.inputBox);
        caret(stage, { x: box.rect.x + 16, y: box.rect.y + 8, w: 4, h: 32 });
      } else {
        textBoxLegacy(stage, L.inputBox);
        caret(stage, { x: L.inputBox.x + 16, y: L.inputBox.y + 8, w: 4, h: 32 });
      }
      button(stage, L.sendButton, "发送", true, SKIN.btnPrimary);
      button(stage, L.retryButton, "重试", false, SKIN.btnSecondary);
      button(stage, L.closeButton, "关闭", true, SKIN.btnSecondary);
      // 现状：hint 在 messageArea.Bottom - 28，与最后一条气泡共用同一块高度（一多就叠）。
      // 新设计：能放 header 就放 header（右对齐、与参与者条同一行），放不下才落到底部留白。
      if (hintInHeader) {
        const hintW = Math.ceil(measureText(s.hint));
        textAt(stage, L.participantStrip.x + L.participantStrip.w - hintW,
          L.participantStrip.y + 5, s.hint, SKIN.inkSoft, "g-sm").style.zIndex = "5";
      } else {
        textAt(stage, area.x + 12, area.y + bubbleAreaH + 4, s.hint, SKIN.inkSoft, "g-sm").style.zIndex = "5";
      }
    } else {
      textBoxLegacy(stage, L.inputBox);
      caret(stage, { x: L.inputBox.x + 16, y: L.inputBox.y + 8, w: 4, h: 32 });
      button(stage, L.sendButton, "发送", true);
      button(stage, L.retryButton, "重试", false);
      button(stage, L.closeButton, "关闭", true);
      textAt(stage, area.x + 12, area.y + area.h - 28, s.hint, GAME_GRAY, "g-sm").style.zIndex = "5";
      addNote(stage, L.inputBox, "现状：输入框下面那条深色带");
    }

    guides.push(["Panel", L.panel], ["Header", L.header], ["ParticipantStrip", L.participantStrip],
      ["MessageArea", L.messageArea], ["Footer", L.footer], ["InputBox", L.inputBox],
      ["Send", L.sendButton], ["Retry", L.retryButton], ["Close", L.closeButton]);
    addGuides(stage, guides);
    return `一次最多 10 条气泡（GroupDialogueLayoutRules.cs:28），当前 ${drawnCount} 条`;
  }

  // ── 群聊中心 ───────────────────────────────────────────────────────────
  function renderHub(stage, vw, vh, design) {
    const L = hubLayout(vw, vh);
    const s = SAMPLE.hub;
    guides.length = 0;

    // 遮罩：F8 / F9 / 中心三处都画（MenuSkinDrawing.DrawScrim，MenuSkinRules.ScrimAlpha = 0.28f）；
    // 改前 F9 与中心完全没有遮罩、F8 是 0.42f。
    // 「统一轻遮罩」开关只作用在新设计栏，关掉 = 不做这一层（仅用于对照）。
    scrim(stage, vw, vh, (!design || OPT.scrim) ? SKIN.scrim : 0);
    nineSlice(stage, L.panel, SKIN.panel, MENU_TEX, { z: 1 });

    const cardH = SKIN.cardHeight;       // 92 —— 新设计也不动它（理由见 SKIN 里的注释）
    const cardStep = SKIN.cardStep;      // 104

    // 标题带（GroupDialogueHubMenu.draw:126-131 → MenuSkinDrawing.DrawTitleBand）：
    // header 是 panel 顶部那条固定 74 高的带（MenuSkinRules.HubTitleBandHeight），
    // 于是分隔线落在 panel.Y + 74 − 14 = panel.Y + 60；强调色取第一张卡的第一位参与者。
    // 改前标题只是 (panel.X+32, panel.Y+24) 的一行裸文字。
    if (!design || OPT.title) {
      titleBand(stage, { x: L.panel.x, y: L.panel.y, w: L.panel.w, h: HUB_TITLE_BAND_HEIGHT }, "线上多人对话", null,
        parseColor(styleFor(s.cards[0].participants[0]).accent, [176, 146, 242]));
    }

    const listArea = hubListArea(L.panel, L.closeButton);

    let y = L.panel.y + 94;
    for (const invitation of s.cards) {
      const row = { x: L.panel.x + 32, y, w: L.panel.w - 64, h: cardH };     // GroupDialogueHubMenu.draw 的卡片行矩形
      nineSlice(stage, row, SKIN.card, MENU_TEX, { z: 3 });
      const names = invitation.participants.join("、");
      const status = `${invitation.status} · 到期第 ${invitation.expires} 天`;
      // 行 1：标题 · 参与者（现状与两版都一样）
      textAt(stage, row.x + 18, row.y + SKIN.cardRow1Y,
        `${invitation.title} · ${names}`, GAME_BLACK).style.zIndex = "6";
      if (design && OPT.card) {
        // 新设计：主题与状态**并成一行**。
        // 这一行底 = +44 + 28 = +72，正好等于九宫格下内沿（92 − 20），不会出框。
        textAt(stage, row.x + 18, row.y + SKIN.cardRow2YDesign,
          `主题：${invitation.topic} · ${status}`, SKIN.inkSoft).style.zIndex = "6";
      } else {
        textAt(stage, row.x + 18, row.y + 42, `主题：${invitation.topic}`, SKIN.inkSoft).style.zIndex = "6";
        // 现状：第三行在 +66，文字底 +94 —— 比卡片本身（92）还低 2px，直接被下边框切断
        textAt(stage, row.x + 18, row.y + SKIN.cardStatusYLegacy,
          `状态：${status}`, DIM_GRAY, "g-sm").style.zIndex = "6";
        if (y === L.panel.y + 94) {
          addNote(stage, { x: row.x, y: row.y + 60, w: row.w, h: 34 },
            "现状：第三行 y=+66，文字底 +94 > 卡片高 92 —— 被下边框切断");
        }
      }
      ["接受", "稍后", "忽略"].forEach((label, i) => {
        button(stage, actionButtonAt(row, i), label, true,
          design ? (i === 0 ? SKIN.btnPrimary : SKIN.btnSecondary) : SKIN.btnPrimary);
      });
      y += cardStep;
    }

    // 列表区凹槽（MenuSkinDrawing.DrawInset(b, MenuSkinRules.HubListArea(panel, closeButton))）：
    // 卡片浮在它上面，靠底色分档分层（卡片自身的 tint 不用改）。
    // ⚠ 现状栏也画（同 F8 / F9 的理由）；实机画在卡片之前，页面靠 z-index 分层，结果相同。
    if (!design || OPT.inset) {
      nineSlice(stage, listArea, SKIN.inset, MENU_TEX, { noShadow: true, z: 2 })
        .dataset.inset = "hubList";
    }

    button(stage, L.closeButton, "关闭", true, design ? SKIN.btnSecondary : SKIN.btnPrimary);
    textAt(stage, L.panel.x + 32, L.panel.y + L.panel.h - 112, s.hint, GAME_GRAY, "g-sm").style.zIndex = "5";

    guides.push(["Panel", L.panel], ["CloseButton", L.closeButton], ["ListInset", listArea]);
    addGuides(stage, guides);
    return `邀约卡 ${s.cards.length} 张（显示上限 GroupInvitationRules.cs:18 = 4）；新设计把三行文字并成两行，几何零改动`;
  }

  // ── 舞台装配 / 缩放 / 自检 ─────────────────────────────────────────────
  const stageWrap = document.querySelector(".stage-wrap");
  const colLegacy = document.getElementById("col-legacy");
  const colDesign = document.getElementById("col-design");
  const stageLegacy = document.getElementById("stage-legacy");
  const stageDesign = document.getElementById("stage-design");
  const statusbar = document.getElementById("statusbar");
  const scaleReadout = document.getElementById("scale-readout");

  function paint(stage, view, vw, vh, design) {
    stage.className = "stage" + (view === "chat" && !design ? " f8" : "");
    stage.style.width = vw + "px";
    stage.style.height = vh + "px";
    stage.replaceChildren();
    if (view === "chat") return renderChat(stage, vw, vh, design);
    if (view === "group") return renderGroup(stage, vw, vh, design);
    return renderHub(stage, vw, vh, design);
  }

  function fitStages() {
    const cols = [colLegacy, colDesign].filter((c) => !c.hidden);
    const gap = 16;
    const each = Math.max(160, (stageWrap.clientWidth - gap * (cols.length - 1)) / cols.length);
    const k = Math.min(1, each / state.width);
    for (const col of cols) {
      const holder = col.querySelector(".stage-holder");
      const st = col.querySelector(".stage");
      st.style.transform = `scale(${k})`;
      holder.style.height = Math.round(state.height * k) + "px";
    }
    scaleReadout.textContent = `缩放 ${Math.round(k * 100)}% · 舞台 ${state.width}×${state.height}` + (cols.length === 2 ? "（两列同尺度）" : "");
    return k;
  }

  function selfCheck() {
    const issues = [];
    const stages = [["现状", stageLegacy], ["新设计", stageDesign]].filter(([, st]) => st.parentElement.parentElement.hidden === false);
    let count = 0;
    for (const [label, st] of stages) {
      for (const el of st.querySelectorAll(".abs")) {
        if (el.classList.contains("guide") || el.classList.contains("risk")) continue;
        if (el.classList.contains("scrim")) continue;
        count++;
        const x = parseFloat(el.style.left || "0");
        const y = parseFloat(el.style.top || "0");
        const w = el.offsetWidth, h = el.offsetHeight;
        if (x < -1 || y < -1 || x + w > state.width + 1 || y + h > state.height + 1) {
          issues.push(`${label}/${el.className.split(" ")[0]} 越出视口 (x=${Math.round(x)}, y=${Math.round(y)}, w=${Math.round(w)}, h=${Math.round(h)})`);
        }
      }
      // 内容是否溢出面板（气泡/卡片压在面板外）
      for (const el of st.querySelectorAll("[data-bubble]")) {
        const r = { x: parseFloat(el.style.left), y: parseFloat(el.style.top), w: el.offsetWidth, h: el.offsetHeight };
        if (r.x < 0 || r.y < 0 || r.x + r.w > state.width || r.y + r.h > state.height) {
          issues.push(`${label}/气泡 越出视口 (${Math.round(r.x)},${Math.round(r.y)} ${r.w}×${r.h})`);
        }
      }
    }
    return { elements: count, issues };
  }

  function updateStatus(notes) {
    const result = selfCheck();
    const label = { chat: "F8 私聊", group: "F9 群聊", hub: "群聊中心" }[state.view];
    const modeLabel = { legacy: "现状", design: "新设计", side: "并排" }[state.mode];
    const items = [
      ["pill", `${label} · ${state.width}×${state.height} · ${modeLabel}`],
      ["pill", `舞台内元素 ${result.elements}`],
      result.issues.length === 0
        ? ["pill ok", "内容未溢出舞台 ✓"]
        : ["pill bad", `溢出 ${result.issues.length} 处：${result.issues.slice(0, 3).join("；")}`],
    ];
    for (const note of notes.filter(Boolean)) items.push(["pill", note]);
    items.push(["pill ok", "✔ 气泡与 /test/ui、回放页同源（角色用描边归一变体 npc_bubble_texture.py + 反推 tint npc_bubble_tint.py，玩家 / 兜底用未着色面板 npc_bubble_panel_plain.py）"]);
    statusbar.replaceChildren();
    for (const [cls, text] of items) {
      const el = document.createElement("span");
      el.className = cls;
      el.textContent = text;
      statusbar.append(el);
    }
    window.__UI_REDESIGN_SELFCHECK__ = { view: state.view, mode: state.mode, width: state.width, height: state.height, ...result };
    window.__UI_REDESIGN_READY__ = true;
  }

  function render() {
    colLegacy.hidden = state.mode === "design";
    colDesign.hidden = state.mode === "legacy";
    const notes = [];
    if (state.mode !== "design") notes.push(paint(stageLegacy, state.view, state.width, state.height, false));
    if (state.mode !== "legacy") notes.push(paint(stageDesign, state.view, state.width, state.height, true));
    fitStages();
    updateStatus(notes);
  }

  // ── 交互 ───────────────────────────────────────────────────────────────
  function bindSeg(id, key, after) {
    const seg = document.getElementById(id);
    seg.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-" + key + "]");
      if (!btn) return;
      seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      const value = btn.getAttribute("data-" + key);
      if (key === "size") {
        const [w, h] = value.split("x").map(Number);
        state.width = w; state.height = h;
      } else {
        state[key] = value;
      }
      if (after) after(value);
      render();
    });
  }
  bindSeg("seg-view", "view");
  bindSeg("seg-size", "size");
  bindSeg("seg-mode", "mode");

  document.getElementById("toggle-guides").addEventListener("change", (e) => { state.guides = e.target.checked; render(); });
  document.getElementById("toggle-risk").addEventListener("change", (e) => { state.risk = e.target.checked; render(); });
  for (const [id, key] of [["opt-scrim", "scrim"], ["opt-f8frame", "f8frame"], ["opt-title", "title"], ["opt-inset", "inset"], ["opt-input", "input"], ["opt-card", "card"]]) {
    OPT[key] = document.getElementById(id).checked;
    document.getElementById(id).addEventListener("change", (e) => { OPT[key] = e.target.checked; render(); });
  }
  window.addEventListener("resize", () => fitStages());

  // 初始 aria-pressed
  for (const [id, key, value] of [["seg-view", "view", "chat"], ["seg-size", "size", "1280x720"], ["seg-mode", "mode", "side"]]) {
    document.querySelectorAll(`#${id} button`).forEach((b) => b.setAttribute("aria-pressed", String(b.getAttribute("data-" + key) === value)));
  }
  render();
})();
</script>
</body>
</html>
'''


def ui_preview_redesign_page() -> str:
    """外壳重构设计稿的完整 HTML（自包含：贴图 base64 内联，不读游戏目录）。"""

    payload = {
        "styles": _styles_payload(),
        "glyphs": _glyphs_payload(),
        "ornaments": _ornaments_payload(),
        "aliases": NPC_BUBBLE_ALIASES,
        "sample": _sample_payload(),
        "tex": GAME_TEX,
        "texBaked": GAME_TEX_BAKED,
        # 气泡专用九宫格（描边色相已归一到填充色，见 npc_bubble_texture.py）
        "bubbleTex": BUBBLE_MENU_TEX_DATA_URI,
        # 玩家 / 兜底气泡的未着色面板与两个反推 tint（见 npc_bubble_panel_plain.py）
        "plainTex": PLAIN_MENU_TEX_DATA_URI,
        "playerBubbleTint": list(PLAYER_BUBBLE_TINT),
        "npcFallbackBubbleTint": list(NPC_FALLBACK_BUBBLE_TINT),
    }
    return (
        _UI_REDESIGN_BODY
        .replace("__DATA__", _json(payload))
        .replace("__FRAME_SCRIPT__", _CHARACTER_FRAME_SCRIPT)
    )
