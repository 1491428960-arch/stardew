"""角色气泡配色核对页（``/test/bubble-colors``）。

这个页面回答一个具体问题：**46 个角色的气泡底色，在游戏里实际渲染出来等于设计色吗？**

背景是气泡底的着色机制 —— 游戏用
``IClickableMenu.drawTextureBox(Maps\\MenuTiles (0,256,60,60), tint)`` 画气泡底，
最终色 = **纹理色 × tint ÷ 255**（逐通道）。所以「设计色 → tint」必须反推
（``npc_bubble_tint``），而反推的上限是 255：**目标色任一分量高于面板基色时，
那个分量就乘不出来**。

彩色面板的基色是 ``#fdbc6e``（B 通道只有 110），于是：

* 43 个角色三个通道都在基色以内 → 反推无损，回乘即还原设计色；
* **3 个深蓝角色（Maru / Mermaid / Henchman）的 B 通道超出 110** → 反推值超过 255 被夹住，
  渲染后 B 比设计色暗 7~9 个色阶；
* 玩家气泡与 NPC 兜底气泡更极端（G / B 要 324 / 570）→ 早就改用了游戏自带的
  **去色版面板** ``Maps\\MenuTilesUncolored``（基色 248），颜色得以精确还原。

于是页面并排给出两条路，供人对着实物判断「那 7~9 个色阶值不值得为它换面板」：

| 方案 | 面板 | 描边 | 底色 |
|---|---|---|---|
| **现方案** | 彩色 ``MenuTiles`` 的**描边归一**变体 | 归一到填充色相，随 tint 一起变暗（保留木框质感） | 3 个角色偏暗 |
| **备选** | 去色版 ``MenuTilesUncolored`` | 贴图自带的冷灰紫，**不随 tint 变化** | 46 个全部精确 |

顺带把「描边发红」这件事也画出来（``normalize_before`` / ``normalize_after``）：
那圈突兀的橙红边是同一套乘法着色在**高饱和描边**上的产物，修法是只把描边像素的
色相归一到填充基准色（见 ``scripts/build_bubble_texture.py``）。

页面自身**零滤镜**：所有贴图都在服务端预乘 tint 后内联（与
``ui_preview_redesign_assets.GAME_TEX_BAKED`` 同一套做法），跨浏览器渲染结果一致。

**本页零依赖**：贴图那点像素活儿（解 PNG、逐通道乘、再编回 PNG）走标准库的
:mod:`stardew_ai_bridge.png_rgba`，**不需要 Pillow**。此前这里在模块顶层 ``from PIL import Image``，
而 Bridge 的运行环境没有 Pillow 也没法装 —— 于是 ``import stardew_ai_bridge.app`` 直接失败、
**Bridge 一重启就挂**（2026-09-21 事故，与 2026-09-20 ``group_dialogue_review_page`` 同一类）。
现在这个模块只 import 本包内模块与标准库，`app.py` 那层惰性导入是留给「以后再有人加错依赖」的护栏，不是本页的必需品。

气泡外围的**装饰边框**也一并画上：形状与配色直接复用回放页的 ``_CHARACTER_FRAME_SCRIPT``
（``characterFrameSvg``）与 ``npc_bubble_elements`` 的 ``ornament`` 表 —— 本页不复制任何
装饰常量，只决定「画在哪」。几何是气泡外扩 14px（= ``NpcBubbleFrame.Pad``），与设计稿、
回放页逐像素一致；顶部还能切三套构图（游戏里随发言次序轮换）。

⚠ 装饰必须挂在气泡元素**之外**的兄弟节点上：气泡贴图带 tint，任何 filter 都会作用到整棵
子树，装饰一旦成为它的后代就会被染色（回放页 2026-09-20 踩过，绿色茎叶被乘成暗紫红）。
"""

from __future__ import annotations

import json

from .group_dialogue_review_page import _CHARACTER_FRAME_SCRIPT
from .npc_bubble_elements import NPC_BUBBLE_ELEMENTS
from .npc_bubble_panel_plain import PLAIN_MENU_TEX_DATA_URI, PLAIN_PANEL_BASE
from .npc_bubble_texture import BUBBLE_MENU_TEX_DATA_URI
from .npc_bubble_tint import BUBBLE_TEX_BASE, bubble_to_tint, parse_color, to_tint
from .png_rgba import tint_data_uri
from .ui_preview_redesign_assets import GAME_TEX

#: 页面里气泡的显示尺寸（像素）。九宫格 slice = 20，四角原样、边与中心拉伸。
_BUBBLE_WIDTH = 240
_BUBBLE_HEIGHT = 72

#: 描边发红的代表角色：底色深、描边差异最刺眼。
_RED_EDGE_SAMPLE = "Sophia"

_bake_cache: dict[tuple[str, tuple[int, int, int]], str] = {}


def _bake(data_uri: str, tint: tuple[int, int, int]) -> str:
    """把 tint **预乘**进贴图像素，返回新的 data URI。

    与 ``GAME_TEX_BAKED`` 同一套做法：预览页因此不需要任何 SVG 滤镜，
    也就不会遇到「滤镜在部分浏览器 / GPU 路径下被忽略或按 linearRGB 计算」那类偏差。
    alpha 保持原样 —— 游戏里 tint 的 alpha 是 255，逐通道乘法不动 alpha。

    像素活儿在 :mod:`stardew_ai_bridge.png_rgba`（标准库 ``zlib`` + 字节算术），
    所以这一页不依赖 Pillow；结果按 ``(贴图, tint)`` 缓存，页面首次渲染只算一遍。
    """

    key = (data_uri, tint)
    cached = _bake_cache.get(key)
    if cached is not None:
        return cached

    baked = tint_data_uri(data_uri, tint)
    _bake_cache[key] = baked
    return baked


def _rendered(tint: tuple[int, int, int], base: tuple[int, int, int]) -> tuple[int, int, int]:
    """复算一次游戏的着色结果：纹理基色 × tint ÷ 255。"""

    return tuple(round(tint[i] * base[i] / 255) for i in range(3))


def _clamped(design: tuple[int, int, int]) -> bool:
    """这个设计色在彩色面板上是否触发钳位（任一分量的反推值超过 255）。"""

    return any(round(c * 255 / b) > 255 for c, b in zip(design, BUBBLE_TEX_BASE))


def _rows() -> list[dict[str, object]]:
    """每个角色的设计色、两条路的 tint 与最终渲染色，按偏差从大到小排。"""

    rows: list[dict[str, object]] = []
    for npc, item in NPC_BUBBLE_ELEMENTS.items():
        design = parse_color(item["palette"]["bubble"])
        current_tint = bubble_to_tint(design)
        plain_tint = to_tint(design, PLAIN_PANEL_BASE)
        current = _rendered(current_tint, BUBBLE_TEX_BASE)
        alternative = _rendered(plain_tint, PLAIN_PANEL_BASE)
        rows.append(
            {
                "npc": npc,
                "tone": item["tone"],
                "design": design,
                "currentTint": current_tint,
                "current": current,
                "currentDelta": max(abs(a - b) for a, b in zip(current, design)),
                "currentArt": _bake(BUBBLE_MENU_TEX_DATA_URI, current_tint),
                "plainTint": plain_tint,
                "alternative": alternative,
                "alternativeDelta": max(abs(a - b) for a, b in zip(alternative, design)),
                "plainArt": _bake(PLAIN_MENU_TEX_DATA_URI, plain_tint),
                "clamped": _clamped(design),
            }
        )

    rows.sort(key=lambda row: (-int(row["currentDelta"]), str(row["npc"])))  # type: ignore[arg-type]
    return rows


def _sample_payload(npc: str) -> dict[str, object]:
    """红边演示用的单个角色（原始彩色贴图 vs 描边归一变体）。"""

    design = parse_color(NPC_BUBBLE_ELEMENTS[npc]["palette"]["bubble"])
    tint = bubble_to_tint(design)
    return {
        "npc": npc,
        "tone": NPC_BUBBLE_ELEMENTS[npc]["tone"],
        "design": design,
        "tint": tint,
        "rendered": _rendered(tint, BUBBLE_TEX_BASE),
        "normalizeBefore": _bake(GAME_TEX["menuButton"], tint),
        "normalizeAfter": _bake(BUBBLE_MENU_TEX_DATA_URI, tint),
    }


def _ornaments_payload() -> dict[str, dict[str, object]]:
    """每个角色的装饰边框素材。

    与 ``ui_preview_redesign_page`` 同源：装饰的**形状与配色只有一份来源**
    （``npc_bubble_elements`` 的 ``ornament`` 表 + 回放页的 ``characterFrameSvg``），
    本页只决定画在哪，不复制任何常量。
    """

    return {npc: item["ornament"] for npc, item in NPC_BUBBLE_ELEMENTS.items()}


def bubble_color_page() -> str:
    """角色气泡配色核对页的完整 HTML（自包含：贴图预乘后内联）。"""

    payload = {
        "rows": _rows(),
        "sample": _sample_payload(_RED_EDGE_SAMPLE),
        "ornaments": _ornaments_payload(),
        "bubbleBase": list(BUBBLE_TEX_BASE),
        "plainBase": list(PLAIN_PANEL_BASE),
        "size": [_BUBBLE_WIDTH, _BUBBLE_HEIGHT],
    }
    return (
        _BODY.replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c"))
        .replace("__FRAME_SCRIPT__", _CHARACTER_FRAME_SCRIPT)
    )


_BODY = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>角色气泡配色核对 · Stardew AI NPC</title>
<style>
:root {
  color-scheme: dark;
  --bg: #14161c; --surface: #1d2028; --line: #39404f;
  --text: #eceef4; --muted: #a3abbd; --soft: #cfd5e2;
  --gold: #e5bf7c; --green: #b3ce91; --warn: #f0b58a; --bad: #ef9a86;
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; color: var(--text); background: var(--bg); }
.page { width: min(1400px, calc(100% - 40px)); margin: 0 auto; padding: 26px 0 64px; }
h1 { margin: 9px 0 10px; font-size: clamp(1.3rem, 2.2vw, 1.8rem); font-weight: 650; }
h2 { margin: 0 0 12px; font-size: .95rem; font-weight: 600; color: var(--soft); }
.eyebrow { color: var(--green); font-size: .67rem; letter-spacing: .18em; text-transform: uppercase; font-weight: 700; }
.subtitle { max-width: 1000px; margin: 0; color: var(--muted); font-size: .78rem; line-height: 1.85; }
.subtitle code, .card code { color: #d8c9a0; font-family: ui-monospace, Consolas, monospace; font-size: .72rem; }
.subtitle b { color: var(--soft); font-weight: 400; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px 12px; align-items: center; margin-top: 18px; padding: 11px 14px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }
.toolbar label { color: var(--muted); font-size: .72rem; }
.toolbar select { font: inherit; font-size: .72rem; padding: 5px 8px; color: var(--text); background: #191c24; border: 1px solid var(--line); border-radius: 4px; }
.toolbar-hint { flex: 1 1 320px; color: var(--muted); font-size: .68rem; line-height: 1.7; }
.toolbar-hint code { color: #d8c9a0; font-family: ui-monospace, Consolas, monospace; font-size: .66rem; }
.card { margin-top: 22px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); padding: 16px 18px; }
.card p { margin: 0 0 10px; color: var(--muted); font-size: .74rem; line-height: 1.85; }
table { width: 100%; border-collapse: collapse; font-size: .72rem; }
th, td { padding: 7px 9px; border-bottom: 1px solid #2c313c; text-align: left; vertical-align: middle; }
th { color: var(--muted); font-weight: 500; white-space: nowrap; }
td code { color: #d8c9a0; font-family: ui-monospace, Consolas, monospace; font-size: .68rem; }

/* 气泡：九宫格 border-image + 服务端预乘好的贴图，页面里零滤镜 */
.bubble-wrap { position: relative; flex: none; }
.bubble {
  position: absolute; border-style: solid; border-width: 20px;
  border-image-slice: 20 fill; border-image-repeat: stretch;
  display: grid; place-items: center;
}
.bubble .label { font-size: 17px; line-height: 1; color: #000; text-shadow: none; }
.bubble .label.deep { color: #f3f0fc; }
/* 装饰边框：与回放页 / 设计稿同一套（SVG 内联 fill，不依赖 CSS 变量）。
   ⚠ 必须画在气泡**之外**的兄弟节点上：气泡贴图带 tint（这里是预乘好的），
   任何 filter 都会作用到整棵子树，装饰一旦成为它的后代就会被染色。 */
.bubble-frame { position: absolute; left: 0; top: 0; z-index: 5; pointer-events: none; user-select: none; line-height: 0; }
.bubble-frame svg { display: block; width: 100%; height: 100%; overflow: visible; image-rendering: pixelated; }

.row { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
.swatch { width: 34px; height: 20px; border: 1px solid #000; border-radius: 3px; display: inline-block; vertical-align: middle; }
.pill { display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 3px 9px; background: #191c24; font-size: .68rem; color: var(--muted); }
.pill.ok { color: var(--green); border-color: #47593b; }
.pill.bad { color: var(--bad); border-color: #7a4234; }
.pill.tag { color: var(--gold); border-color: #6d5c36; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 12px; margin-top: 6px; }
.cell { border: 1px solid var(--line); border-radius: 5px; padding: 9px 10px; background: #191c24; }
.cell.bad { border-color: #7a4234; background: #241d1c; }
.cell .head { display: flex; align-items: baseline; gap: 7px; margin-bottom: 6px; }
.cell .head b { font-size: .78rem; }
.cell .head span { color: var(--muted); font-size: .66rem; }
.cell .meta { margin-top: 6px; color: var(--muted); font-size: .66rem; line-height: 1.7; font-family: ui-monospace, Consolas, monospace; }
.compare { display: flex; gap: 16px; flex-wrap: wrap; }
.compare > div { flex: 1 1 320px; min-width: 0; }
.compare h3 { margin: 0 0 8px; font-size: .78rem; color: var(--soft); font-weight: 600; }
.note { color: var(--muted); font-size: .7rem; line-height: 1.8; margin-top: 8px; }
.flag { color: var(--warn); font-weight: 600; }
</style>
</head>
<body>
<main class="page">
  <header>
    <div class="eyebrow">Bridge / Bubble Colors</div>
    <h1>角色气泡配色核对 · 46 个角色 × 两种面板</h1>
    <p class="subtitle">
      游戏里的气泡底色是「<b>贴图色 × tint ÷ 255</b>」乘出来的，所以「设计色」必须反推成 tint。
      反推的上限是 255 —— <b>目标色任一分量高于面板基色，那个分量就乘不出来</b>。
      这个页面把两条路的实物并排放在一起：<b>现方案</b>（彩色木框 + 描边归一）与
      <b>备选</b>（去色版面板）。所有气泡都已按游戏同一条公式预乘，页面里没有任何滤镜。
    </p>
  </header>

  <div class="toolbar">
    <label for="occ">装饰构图</label>
    <select id="occ">
      <option value="0">第 1 套</option>
      <option value="1">第 2 套</option>
      <option value="2">第 3 套</option>
    </select>
    <span class="toolbar-hint">
      气泡外围的藤蔓／物件就是游戏里的装饰边框（构图随发言次序在这三套之间轮换，这里可以手动切）。
      形状与配色直接复用回放页的 <code>characterFrameSvg</code>，本页没有复制任何装饰常量。
    </span>
  </div>

  <section class="card">
    <h2>一、先说「那圈红边」是怎么回事</h2>
    <p>
      气泡底用的那块九宫格贴图<b>自带红橙描边</b> <code>(177,78,5)</code>（饱和度 0.97，B 通道只有 5）。
      白 tint 下它是木框本色，没问题；但角色气泡的 tint 是紫红／靛蓝这类深色，
      描边乘完 B 通道只剩 <code>5 × t ÷ 255 ≈ 2</code> —— 于是深色底旁边就围了一圈橙红。
      修法是把<b>描边像素的色相归一到填充基准色</b>（逐像素保留亮度比例），
      填充像素一个不动，木框质感与四档明暗全部保留。下面是同一个角色的前后对照：
    </p>
    <div class="compare" id="rededge"></div>
  </section>

  <section class="card">
    <h2>二、那 3 个角色：现方案 vs 换去色面板</h2>
    <p id="three-note"></p>
    <div id="three"></div>
  </section>

  <section class="card">
    <h2>三、全部 46 个角色（现方案）</h2>
    <p>按偏差从大到小排。只有最上面那 3 个有肉眼可辨的偏差，其余 43 个回乘无损。</p>
    <div class="grid" id="all"></div>
  </section>
</main>

<script id="bubble-color-data" type="application/json">__DATA__</script>
<script>
(() => {
  const DATA = JSON.parse(document.getElementById("bubble-color-data").textContent);
  const [W, H] = DATA.size;

  const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
  const hex = (c) => "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  const bubbleBase = DATA.bubbleBase, plainBase = DATA.plainBase;

  /** 装饰外扩的像素数 = NpcBubbleFrame.Pad，与设计稿／回放页同一套几何。 */
  const FRAME_PAD = 14;

  /** 当前展示的装饰构图（游戏里随发言次序轮换，这里手动切）。 */
  const OCC = { value: 0 };

  // ── 回放页那套装饰边框（group_dialogue_review_page.py 的 _CHARACTER_FRAME_SCRIPT，原样复用）
__FRAME_SCRIPT__

  /** 用预乘好的贴图画一个气泡；有专属配色的角色再套上外围装饰。 */
  function bubble(art, label, npc) {
    const wrap = document.createElement("div");
    wrap.className = "bubble-wrap";
    wrap.style.width = (W + FRAME_PAD * 2) + "px";
    wrap.style.height = (H + FRAME_PAD * 2) + "px";

    const el = document.createElement("div");
    el.className = "bubble";
    el.style.left = FRAME_PAD + "px";
    el.style.top = FRAME_PAD + "px";
    el.style.width = W + "px";
    el.style.height = H + "px";
    el.style.borderImageSource = `url("${art}")`;
    const span = document.createElement("span");
    span.className = "label" + (isDeep(npc) ? " deep" : "");
    span.textContent = label;
    el.append(span);
    wrap.append(el);

    // 装饰挂在**兄弟节点**上，不能进气泡元素：气泡贴图带 tint，
    // 任何 filter 都会作用到整棵子树，装饰一旦成为后代就会被染色。
    // 几何 = 气泡外扩 14px（viewBox 是 w+28 × h+28），与 drawBubble 逐像素等价。
    const ornament = DATA.ornaments[npc];
    if (ornament) {
      const frame = document.createElement("span");
      frame.className = "bubble-frame";
      frame.style.width = (W + FRAME_PAD * 2) + "px";
      frame.style.height = (H + FRAME_PAD * 2) + "px";
      frame.innerHTML = characterFrameSvg(W, H, ornament, OCC.value);
      wrap.append(frame);
    }
    return wrap;
  }

  /** 深色底用浅字，浅色底用黑字（与 ChatBubbleDrawing 的分流同口径）。 */
  const isDeep = (() => {
    const cache = new Map();
    return (tone) => {
      const npc = String(tone || "");
      if (cache.has(npc)) return cache.get(npc);
      const row = DATA.rows.find((r) => r.npc === npc);
      const design = row ? row.design : [239, 231, 244];
      const lum = 0.299 * design[0] + 0.587 * design[1] + 0.114 * design[2];
      const value = lum < 140;
      cache.set(npc, value);
      return value;
    };
  })();

  function colorCell(label, color, reference, deltaText) {
    const wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;align-items:center;gap:7px;margin:3px 0;font-size:.7rem;color:#a3abbd";
    const chip = document.createElement("span");
    chip.className = "swatch";
    chip.style.background = rgb(color);
    const text = document.createElement("span");
    text.innerHTML = `${label} <code style="color:#d8c9a0">${rgb(color)}</code>`
      + (reference ? ` <span style="opacity:.6">设计 ${rgb(reference)}</span>` : "")
      + (deltaText ? ` <span class="${deltaText.cls}">${deltaText.text}</span>` : "");
    wrap.append(chip, text);
    return wrap;
  }

  // ── 一、红边前后对照 ───────────────────────────────────────────────────
  function renderRedEdge() {
    const s = DATA.sample;
    const host = document.getElementById("rededge");
    host.replaceChildren();
    const pair = [
      ["改前 · 原始彩色贴图（红橙描边）", s.normalizeBefore, "bad"],
      ["改后 · 描边归一（现在游戏里的样子）", s.normalizeAfter, "ok"],
    ];
    for (const [title, art, kind] of pair) {
      const box = document.createElement("div");
      const h3 = document.createElement("h3");
      h3.innerHTML = `${title} <span class="pill ${kind}">${kind === "ok" ? "已修" : "问题"}</span>`;
      box.append(h3, bubble(art, s.npc, s.npc));
      box.append(colorCell("底色渲染", s.rendered, s.design));
      host.append(box);
    }
  }

  // ── 二、三个角色两条路并排 ─────────────────────────────────────────────
  function renderThree() {
    const bad = DATA.rows.filter((r) => r.currentDelta > 0);
    document.getElementById("three-note").innerHTML =
      `这 ${bad.length} 个角色的设计色 <code>B</code> 通道高于彩色面板基色 `
      + `<code>${bubbleBase[2]}</code>，反推值超过 255 被夹住，于是渲染出来比设计色暗 `
      + `<span class="flag">7~9 个色阶</span>。换成去色版面板（基色 <code>${plainBase[0]}</code>）后 `
      + `反推值全部落在界内，颜色可以精确还原 —— 代价是<b>描边不再随 tint 变化</b>，`
      + `木框质感让位给颜色准确。`;
    const host = document.getElementById("three");
    host.replaceChildren();
    for (const row of bad) {
      const block = document.createElement("div");
      block.style.cssText = "margin:16px 0;padding-top:14px;border-top:1px solid #2c313c";
      const h3 = document.createElement("h3");
      h3.style.cssText = "margin:0 0 10px;font-size:.82rem;color:#cfd5e2";
      h3.innerHTML = `<b>${row.npc}</b> <span style="color:#a3abbd;font-weight:400">· ${row.tone}</span>`;
      block.append(h3);

      const cmp = document.createElement("div");
      cmp.className = "compare";

      const left = document.createElement("div");
      left.innerHTML = '<h3>现方案 · 彩色木框 + 描边归一</h3>';
      left.append(bubble(row.currentArt, row.npc, row.npc));
      left.append(colorCell("渲染", row.current, row.design,
        { cls: "flag", text: `最大差 ${row.currentDelta} 色阶` }));
      left.insertAdjacentHTML("beforeend",
        `<div class="note">tint <code>${row.currentTint.join(", ")}</code>（B 被夹到 255）</div>`);

      const right = document.createElement("div");
      right.innerHTML = '<h3>备选 · 去色版面板</h3>';
      right.append(bubble(row.plainArt, row.npc, row.npc));
      right.append(colorCell("渲染", row.alternative, row.design,
        { cls: "ok", text: `最大差 ${row.alternativeDelta} 色阶` }));
      right.insertAdjacentHTML("beforeend",
        `<div class="note">tint <code>${row.plainTint.join(", ")}</code>（全部在界内）</div>`);

      cmp.append(left, right);
      block.append(cmp);
      host.append(block);
    }
  }

  // ── 三、全部 46 个 ─────────────────────────────────────────────────────
  function renderGrid() {
    const host = document.getElementById("all");
    host.replaceChildren();
    for (const row of DATA.rows) {
      const cell = document.createElement("div");
      cell.className = "cell" + (row.currentDelta > 0 ? " bad" : "");
      const head = document.createElement("div");
      head.className = "head";
      head.innerHTML = `<b>${row.npc}</b><span>${row.tone}</span>`
        + (row.currentDelta > 0 ? '<span class="pill bad">偏暗</span>' : '<span class="pill ok">无损</span>');
      cell.append(head);
      cell.append(bubble(row.currentArt, row.npc, row.npc));
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.innerHTML = `设计 ${rgb(row.design)}<br>渲染 ${rgb(row.current)}`
        + (row.currentDelta > 0 ? `　<span class="flag">Δ${row.currentDelta}</span>` : "");
      cell.append(meta);
      host.append(cell);
    }
  }

  function renderAll() {
    renderRedEdge();
    renderThree();
    renderGrid();
  }

  renderAll();

  document.getElementById("occ").addEventListener("change", (event) => {
    OCC.value = Number(event.target.value);
    renderAll();
  });

  window.__BUBBLE_COLORS_READY__ = true;
})();
</script>
</body>
</html>
'''
