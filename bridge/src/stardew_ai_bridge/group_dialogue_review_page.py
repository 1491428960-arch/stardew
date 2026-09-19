from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from .npc_bubble_elements import NPC_BUBBLE_ELEMENTS
# NPC_BUBBLE_ALIASES 由分配器模块定义（npc_bubble_catalog），这里从定义处导入；
# 早先写成从 npc_bubble_elements 导入会让整个 app 导入失败（Bridge 无法启动）。
from .npc_bubble_catalog import NPC_BUBBLE_ALIASES


_DEFAULT_BATCH = "20260918-group-dialogue-cloud-v3-fanout-cases"
_KNOWN_BATCHES = (
    _DEFAULT_BATCH,
    "20260918-group-dialogue-cloud-v4-natural-flow-cases",
)
_BATCH_LABELS = {
    _DEFAULT_BATCH: "v3 · 多人回应基线",
    "20260918-group-dialogue-cloud-v4-natural-flow-cases": "v4 · 自然接话流",
}

_OBSERVATIONS = {
    "generated-group-shane-harvey-care": (
        "Shane 的疲惫式嘴硬成立；回复会顺手把 Harvey 拉进话题，符合群聊语境。"
    ),
    "generated-group-sebastian-elliott-creative": (
        "Elliott 的文学化节奏和具体感最明显，建议保留这种慢一点的展开。"
    ),
    "generated-group-sophia-emily-vineyard": (
        "Sophia 的轻快追问成立，先接住葡萄颜色，再把话题递回给玩家。"
    ),
    "generated-group-wizard-alex-research-training": (
        "Wizard 的判断和研究口吻成立；这一条混入了舞台动作和日期说明，标为观察项。"
    ),
    "generated-group-abigail-sebastian-sophia-playlist": (
        "Sebastian 的短促克制很清楚，适合作为多人群聊里的低主动发言人。"
    ),
    "generated-group-elliott-harvey-wizard-records": (
        "Harvey 的核对和照料动作具体；后续可压低偶发的角色名重复前缀。"
    ),
}


# 按实际气泡尺寸绘制一个完整 SVG，不用平铺图案；文字始终留在普通 DOM 中。
_CHARACTER_FRAME_SCRIPT = r'''
  function characterFrameSvg(width, height, ornament) {
    const w = Math.round(width), h = Math.round(height), pad = 14;
    const left = pad, top = pad, right = w + pad, bottom = h + pad;
    const c = ornament.colors, kind = ornament.kind;
    // Curated clusters leave quiet stretches; a turn keeps its composition on resize.
    const variant = ((Number(arguments[3]) || 0) + [...kind].reduce((n,ch)=>n+ch.charCodeAt(0),0)) % 3;
    const layouts = [
      {top:[.08,.14,.23,.72],bottom:[.34,.42,.83,.91],left:[.68],right:[.22,.31]},
      {top:[.42,.49,.86,.92],bottom:[.09,.17,.26,.71],left:[.23,.34],right:[.76]},
      {top:[.09,.18,.78,.86,.92],bottom:[.24,.32,.59],left:[.72,.81],right:[.29]},
    ];
    const organic = ["vine", "grapevine", "laurel", "wheat", "crop", "leaf", "flower"].includes(kind);
    const parts = [];
    const rect = (x,y,width,height,color) => `<rect x="${Math.round(x)}" y="${Math.round(y)}" width="${width}" height="${height}" fill="${color}"/>`;
    let detailScale = 1;
    const group = (x,y,body) => parts.push(`<g data-ink="detail" transform="translate(${Math.round(x)} ${Math.round(y)}) scale(${detailScale})">${body}</g>`);
    // Each edge has one long bend. Two-pixel steps retain a sprite-like silhouette.
    const edgePoint = (side,t) => {
      const bend = organic ? Math.sin(Math.PI*t)*4 : 0;
      const sway = ["vine", "grapevine"].includes(kind) ? Math.sin(Math.PI*t*2)*2 : 0;
      if (side === "top") return [left+w*t, top-bend+sway];
      if (side === "bottom") return [left+w*t, bottom+bend+sway];
      if (side === "left") return [left-bend, top+h*t];
      return [right+bend, top+h*t];
    };
    const pixel = n => Math.round(n/2)*2;
    for (const side of ["top", "right", "bottom", "left"]) {
      const horizontal = side === "top" || side === "bottom";
      const length = horizontal ? w : h;
      const count = Math.max(2, Math.ceil(length/8));
      let d = "";
      for (let i=0;i<=count;i++) {
        const [x,y] = edgePoint(side,i/count).map(pixel);
        d += i === 0 ? `M${x} ${y}` : (horizontal ? `H${x}V${y}` : `V${y}H${x}`);
      }
      const lineWidth = ["ribbon","wood","book"].includes(kind) ? 6 : ["arcane","fish"].includes(kind) ? 2 : kind === "slime" ? 5 : 3;
      parts.push(`<g data-side="${side}">`);
      parts.push(`<path data-ink="outline" d="${d}" fill="none" stroke="#171f20" stroke-width="${lineWidth+2}"/>`);
      parts.push(`<path data-ink="stem" d="${d}" fill="none" stroke="${c.line}" stroke-width="${lineWidth}"/>`);
      if (organic || kind === "ribbon") parts.push(`<path data-ink="highlight" d="${d}" fill="none" stroke="${c.highlight}" stroke-width="1"/>`);
      parts.push('</g>');
      // These are growing accents on a continuous stem, not a repeating border tile.
      const positions = layouts[variant][side];
      positions.forEach((t,index) => {
        detailScale = [1,.75,1.125,.875][(index+variant+(horizontal?0:1))%4];
        const [x,y] = edgePoint(side,t);
        if (organic) {
          const leaf = kind === "crop"
            ? '<path fill="#263a2b" d="M6 0H9V8H14V11H10V14H6V10H2V7H0V4H4V6H6Z"/><path fill="'+c.leaf+'" d="M7 1H8V8H12V10H9V12H7V9H3V6H4V8H7Z"/>'+rect(7,2,1,6,c.leafHi)
            : kind === "leaf"
            ? '<path fill="#21352a" d="M4 0H10V2H14V5H16V10H13V13H9V15H5V12H2V9H0V5H4Z"/><path fill="'+c.leaf+'" d="M5 2H9V4H12V6H14V9H11V11H8V13H6V10H4V8H2V6H5Z"/>'+rect(7,4,2,7,c.leafHi)
            : kind === "flower"
            ? '<path fill="#33302e" d="M4 0H8V3H12V7H9V11H5V9H1V5H4Z"/><path fill="'+c.leaf+'" d="M4 1H7V4H10V7H7V9H5V7H2V5H5Z"/>'+rect(5,4,3,3,c.leafHi)+'<path fill="'+c.line+'" d="M7 11H11V9H14V12H11V14H7Z"/>'
            : kind === "grapevine"
            ? '<path fill="#21352a" d="M6 0H10V3H14V6H16V10H12V13H8V15H4V12H0V7H3V3H6Z"/><path fill="'+c.leaf+'" d="M6 3H9V5H12V8H14V10H10V12H7V13H5V10H2V8H5V5H6Z"/>'+rect(6,5,3,5,c.leafHi)
            : kind === "wheat"
            ? '<path fill="'+c.leaf+'" d="M0 5H2V2H4V0H6V4H4V7H2V10H0ZM6 8H8V5H10V3H12V7H10V10H8V12H6Z"/>'+rect(3,2,2,3,c.leafHi)
            : '<path fill="#21352a" d="M0 4H2V2H6V0H12V6H10V8H6V10H2V8H0Z"/><path fill="'+c.leaf+'" d="M2 4H6V2H10V6H6V8H2Z"/>'+rect(4,3,4,2,c.leafHi);
          const outward = index%2 === 0 ? -1 : 1;
          const dx = horizontal ? -5 : (side === "left" ? -10 : 0);
          const dy = horizontal ? (side === "top" ? -8 : 0) + outward*2 : -5;
          group(x+dx,y+dy,(index+variant)%2 ? '<g transform="translate(16 0) scale(-1 1)">'+leaf+'</g>' : leaf);
          if (["vine", "grapevine"].includes(kind) && horizontal && index%2===1) {
            group(x+6,y-2,'<path d="M0 0V4H4V8H8V4H6" fill="none" stroke="'+c.highlight+'" stroke-width="2"/>');
          }
        } else if (kind === "crystal") {
          group(x-4,y-6,'<path fill="#242238" d="M2 0H6V2H8V10H6V14H2V12H0V4H2Z"/><path fill="'+c.leaf+'" d="M2 4H4V2H6V10H4V12H2Z"/>'+rect(2,4,2,4,c.leafHi));
        } else if (kind === "arcane") {
          group(x-4,y-4,'<path fill="'+c.leaf+'" d="M3 0H5V3H8V5H5V8H3V5H0V3H3Z"/>'+rect(3,3,2,2,c.leafHi));
        } else if (kind === "cable") {
          group(x-4,y-3,rect(0,0,8,6,"#202331")+rect(1,1,6,4,c.leaf)+rect(2,1,2,2,c.leafHi));
        } else if (kind === "ribbon") {
          group(x-4,y-3,'<path fill="'+c.leaf+'" d="M0 0H3V2H5V0H8V6H5V4H3V6H0Z"/>'+rect(3,2,2,2,c.leafHi));
        } else if (kind === "ore") {
          group(x-6,y-4,'<path fill="#242933" d="M3 0H10V2H13V8H0V3H3Z"/><path fill="'+c.leaf+'" d="M3 2H9V4H11V6H2V4H3Z"/>'+rect(4,2,5,2,c.leafHi));
        } else if (kind === "book") {
          group(x-5,y-5,rect(0,0,10,12,'#27242d')+rect(1,1,3,10,c.line)+rect(4,1,5,10,c.leaf)+rect(5,2,3,2,c.leafHi)+rect(5,8,3,1,c.highlight));
        } else if (kind === "wood") {
          group(x-3,y-6,'<path fill="#29282a" d="M2 0H5V2H7V14H0V2H2Z"/><path fill="'+c.leaf+'" d="M2 2H5V12H2Z"/>'+rect(2,3,1,7,c.leafHi)+rect(3,5,2,2,'#66533e'));
        } else if (kind === "wool") {
          group(x-6,y-4,'<path d="M0 4V1H4V7H8V1H12V4" fill="none" stroke="#28252f" stroke-width="4"/><path d="M0 4V1H4V7H8V1H12V4" fill="none" stroke="'+c.leaf+'" stroke-width="2"/>'+rect(4,4,2,2,c.leafHi));
        } else if (kind === "fish") {
          group(x-5,y-5,'<path d="M0 0H5V5H10V10M5 0H10V5H0V10H5V5" fill="none" stroke="'+c.leaf+'" stroke-width="1"/>'+rect(4,4,3,3,c.leafHi));
        } else if (kind === "slime") {
          group(x-5,y-3,'<path fill="#222430" d="M0 0H12V5H9V10H6V7H3V4H0Z"/><path fill="'+c.leaf+'" d="M1 0H11V3H8V8H7V5H4V2H1Z"/>'+rect(7,2,2,2,c.leafHi));
        } else if (kind === "stone") {
          group(x-5,y-5,'<path fill="#26272e" d="M3 0H8V2H11V7H9V10H2V8H0V3H3Z"/><path fill="'+c.leaf+'" d="M3 2H7V3H9V7H7V8H3V6H2V4H3Z"/>'+rect(3,3,4,2,c.leafHi));
        } else {
          group(x-4,y-3,rect(0,0,8,5,c.leaf)+rect(1,0,6,2,c.leafHi));
        }
      });
    }
    // Larger objects sit across the edge; generous text padding keeps their interiors clear.
    const object = (index,x,y,size=32) => parts.push(`<g data-ink="object" data-object="${index}" transform="translate(${x} ${y}) scale(${size/32})">${ornament.objects[index]}</g>`);
    const placements = [
      [[0,w-35,-2,40],[1,4,h-10,36]],
      [[0,Math.round(w*.16),0,36],[1,w-34,h-12,40]],
      [[1,Math.round(w*.56),0,36],[0,Math.round(w*.12),h-12,40]],
    ];
    placements[variant].forEach(args=>object(...args));
    if (kind === "grapevine" && w >= 260) object(0,Math.round(w*(variant===0?.64:.76)),h-6,28);
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w+28} ${h+28}" width="${w+28}" height="${h+28}" fill="none" shape-rendering="crispEdges" aria-hidden="true" focusable="false">${parts.join("")}</svg>`;
  }
'''


def _batch_label(name: str) -> str:
    if name in _BATCH_LABELS:
        return _BATCH_LABELS[name]
    short = re.sub(r"^[0-9]{8}-group-dialogue-cloud-", "", name)
    return f"{name[:8]} · {short}"


def _records_path(artifact_root: Path, batch_name: str) -> Path:
    return artifact_root / batch_name / "cases.json"


def _is_group_batch_name(name: str) -> bool:
    """只接受形如 ``20260918-group-dialogue-cloud-*`` 的批次目录名。"""

    return bool(re.fullmatch(r"[0-9]{8}-group-dialogue-cloud-[a-z0-9-]+", name))


def _available_batches(artifact_root: Path) -> list[str]:
    """列出真正存在 cases.json 的群聊批次，最新的排最前。

    按 cases.json 的写入时间排序，不能按目录名字符串排——字符串比较里 "v9" 大于
    "v10"/"v11"（"1" < "9"），那样默认显示的就成了旧批次。
    """

    found: list[tuple[float, str]] = []
    try:
        for path in artifact_root.iterdir():
            if not path.is_dir() or not _is_group_batch_name(path.name):
                continue
            records = path / "cases.json"
            if records.is_file():
                found.append((records.stat().st_mtime, path.name))
    except OSError:
        pass
    found.sort(reverse=True)
    return [name for _, name in found]


def _resolve_batch(artifact_root: Path, requested: str | None) -> str:
    """显式请求优先；没有请求时显示最新批次。

    这样回放页用一个固定 URL 就能一直看最新结果，刷新标签即可，
    不必每次带 ?batch= 打开一个新页面。
    """

    if requested and _is_group_batch_name(requested):
        if _records_path(artifact_root, requested).is_file():
            return requested
    available = _available_batches(artifact_root)
    return available[0] if available else _DEFAULT_BATCH


def _load_records(artifact_root: Path, batch_name: str) -> list[dict[str, Any]]:
    try:
        records = json.loads(
            _records_path(artifact_root, batch_name).read_text(encoding="utf-8")
        )
    except (OSError, TypeError, ValueError):
        return []
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def group_dialogue_review_page(artifact_root: Path, batch: str | None = None) -> str:
    batch_name = _resolve_batch(artifact_root, batch)
    records = _load_records(artifact_root, batch_name)
    available = _available_batches(artifact_root) or [batch_name]
    batch_links = " ".join(
        '<a class="batch-link{cls}" href="/test/group/review?batch={name}">{label}</a>'.format(
            cls=" active" if name == batch_name else "",
            name=name,
            label=_batch_label(name),
        )
        for name in available
    )
    payload = {"batchName": batch_name, "records": records}
    serialized = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    observations_json = json.dumps(_OBSERVATIONS, ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    # 主图案只存一份；备用标志物留在 Python 数据库，不发送到页面。
    styles = {
        npc: {
            "icon": item["icon"], "tone": item["tone"], "className": npc.lower(),
            **{key: item["palette"][key] for key in ("accent", "accentSoft", "bubble", "border")},
        }
        for npc, item in NPC_BUBBLE_ELEMENTS.items()
    }
    glyphs = {
        npc: '<svg viewBox="0 0 24 24" fill="currentColor" shape-rendering="crispEdges" '
             'aria-hidden="true">' + item["motifs"][0] + '</svg>'
        for npc, item in NPC_BUBBLE_ELEMENTS.items()
    }
    styles_json = json.dumps(styles, ensure_ascii=False).replace("<", "\\u003c")
    glyphs_json = json.dumps(glyphs, ensure_ascii=False).replace("<", "\\u003c")
    aliases_json = json.dumps(NPC_BUBBLE_ALIASES, ensure_ascii=False).replace("<", "\\u003c")
    ornaments_json = json.dumps(
        {npc: item["ornament"] for npc, item in NPC_BUBBLE_ELEMENTS.items()}, ensure_ascii=False
    ).replace("<", "\\u003c")
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>群聊样本回放 · Stardew AI NPC</title>
  <style>
:root {{
  color-scheme: dark;
  --bg: #11121b;
  --panel: #222b27;
  --panel-strong: #29332c;
  --line: #405044;
  --text: #f3efdf;
  --muted: #a4b09f;
  --soft: #d5dacb;
  --violet: #c1cd9f;
  --cyan: #c1cd9f;
  --gold: #e5bf7c;
  --green: #b3ce91;
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; color: var(--text); background: #18221e; }}
a {{ color: inherit; text-decoration: none; }}
button {{ font: inherit; }}
button:focus-visible, a:focus-visible {{ outline: 2px solid var(--gold); outline-offset: 4px; }}
.page {{ width: min(1260px, calc(100% - 64px)); margin: 0 auto; padding: 38px 0 56px; }}
.topbar {{ display: flex; justify-content: space-between; gap: 28px; align-items: flex-start; margin-bottom: 28px; }}
.topbar > div {{ min-width: 0; }}
.eyebrow {{ color: var(--green); font-size: .67rem; letter-spacing: .18em; text-transform: uppercase; font-weight: 700; }}
h1 {{ margin: 10px 0 12px; font-size: clamp(1.65rem, 3vw, 2.25rem); letter-spacing: .015em; font-weight: 650; }}
.subtitle {{ max-width: 760px; margin: 0; color: var(--muted); font-size: .8rem; line-height: 1.8; }}
.subtitle b {{ color: var(--soft); font-weight: 400; overflow-wrap: anywhere; }}
.back {{ border: 1px solid #647258; border-radius: 4px; padding: 10px 14px; color: var(--soft); background: #273429; white-space: nowrap; font-size: .8rem; box-shadow: 0 3px 0 #101914; }}
.back:hover {{ color: #fff4d8; border-color: var(--gold); }}
.batch-nav {{ display: flex; gap: 7px; margin-top: 18px; padding: 0 2px 9px; overflow-x: auto; scrollbar-width: thin; scrollbar-color: #627259 transparent; }}
.batch-link {{ flex: 0 0 auto; border: 1px solid transparent; border-radius: 3px; padding: 7px 10px; color: var(--muted); font-size: .69rem; }}
.batch-link:hover {{ color: var(--text); background: #2d382e; }}
.batch-link.active {{ color: #efe4be; border-color: #687357; background: #35412e; }}
.stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; margin-bottom: 24px; border: 1px solid var(--line); border-radius: 5px; background: #202c24; }}
.stat {{ padding: 14px 20px; border-right: 1px solid var(--line); }}
.stat:last-child {{ border-right: 0; }}
.stat-label {{ color: var(--muted); font-size: .68rem; letter-spacing: .05em; }}
.stat-value {{ display: block; margin-top: 8px; font-size: 1.05rem; font-weight: 600; }}
.stat-value.green {{ color: var(--green); }}
.stat-value.cyan {{ color: #d4dac0; }}
.stat-value.gold {{ color: var(--gold); font-size: .88rem; }}
.review-shell {{ display: grid; grid-template-columns: 254px minmax(0, 1fr); gap: 24px; align-items: start; }}
.sidebar {{ padding: 0; position: sticky; top: 22px; }}
.sidebar-head {{ display: flex; justify-content: space-between; align-items: center; padding: 7px 4px 15px; border-bottom: 1px solid var(--line); margin-bottom: 12px; }}
.sidebar-head strong {{ font-size: .85rem; font-weight: 600; }}
.sidebar-head span {{ color: var(--muted); font-size: .7rem; }}
.case-list {{ display: grid; gap: 8px; }}
.case-button {{ width: 100%; display: grid; grid-template-columns: 7px minmax(0, 1fr) auto; gap: 10px; align-items: center; text-align: left; border: 1px solid transparent; border-radius: 4px; padding: 14px 10px; color: var(--soft); background: transparent; cursor: pointer; }}
.case-button:hover {{ background: #253128; border-color: var(--line); }}
.case-button.active {{ border-color: #687955; background: #303c2d; color: #fff1cd; box-shadow: inset 3px 0 #c0cc91; }}
.case-dot {{ width: 5px; height: 5px; background: var(--green); }}
.case-button.watch .case-dot {{ background: var(--gold); }}
.case-title {{ font-weight: 550; font-size: .8rem; line-height: 1.55; }}
.case-title, .case-meta {{ display: block; }}
.case-meta {{ margin-top: 5px; color: var(--muted); font-size: .64rem; }}
.case-index {{ color: #8e9d85; font-size: .68rem; font-variant-numeric: tabular-nums; }}
.detail {{ min-width: 0; min-height: 560px; border: 1px solid #61704d; border-radius: 6px; background: #1d2622; box-shadow: 0 5px 0 #101812, 0 0 0 3px #131d16; overflow: hidden; }}
.detail-empty {{ display: grid; place-items: center; min-height: 560px; color: var(--muted); padding: 40px; text-align: center; }}
.detail-head {{ padding: 26px 30px 22px; border-bottom: 1px solid #48563c; background: #2c3629; box-shadow: inset 0 2px #5a6543; }}
.detail-title-row {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }}
.detail h2 {{ margin: 9px 0; font-size: clamp(1.12rem, 2.1vw, 1.45rem); line-height: 1.45; color: #f5edcf; font-weight: 600; }}
.detail-id {{ color: #98a18b; font: .64rem/1.6 ui-monospace, Consolas, monospace; overflow-wrap: anywhere; }}
.badge-row, .participant-row, .check-row {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.badge-row {{ max-width: 210px; justify-content: flex-end; padding-top: 2px; }}
.badge, .participant, .check {{ border: 1px solid #4d5c45; border-radius: 3px; padding: 4px 7px; color: var(--soft); background: #263125; font-size: .63rem; line-height: 1.6; }}
.badge.success, .check.success {{ color: var(--green); border-color: #47593b; }}
.badge.channel {{ color: #c7d6bb; }}
.participant-row {{ margin-top: 14px; }}
.participant {{ display: inline-flex; align-items: center; gap: 6px; color: var(--accent); border-color: color-mix(in srgb, var(--accent) 25%, #3b4534); background: #202b23; padding: 4px 9px; }}
.participant::before {{ content: ""; width: 4px; height: 4px; background: currentColor; }}
.topic {{ margin-top: 17px; padding: 11px 0 0; border-top: 1px solid #424e38; color: #ddd9c4; line-height: 1.75; font-size: .8rem; }}
.topic b {{ display: block; margin-bottom: 4px; color: #9fac93; font-size: .65rem; font-weight: 400; letter-spacing: .05em; }}
.conversation {{ padding: 24px 30px 10px; }}
.conversation-label {{ color: #aaba9b; font-size: .66rem; letter-spacing: .14em; text-transform: uppercase; }}
.rhythm-note {{ margin-top: 7px; color: #8f9e88; font-size: .65rem; line-height: 1.65; }}
.message {{ display: flex; gap: 14px; margin: 28px 0; align-items: flex-start; }}
.avatar {{ flex: 0 0 46px; width: 46px; height: 46px; display: grid; place-items: center; margin-top: 1px; color: var(--accent, var(--gold)); background: #35402d; border: 2px solid #6e7650; box-shadow: inset 0 0 0 2px #202a20, 3px 3px 0 #101810; border-radius: 3px; }}
.avatar-glyph {{ display: grid; place-items: center; width: 100%; height: 100%; }}
.avatar-glyph svg {{ width: 24px; height: 24px; display: block; image-rendering: pixelated; }}
.speaker-dot {{ width: 4px; height: 4px; background: var(--accent, var(--green)); flex: 0 0 auto; }}
.bubble-wrap {{ max-width: min(700px, calc(100% - 60px)); min-width: 0; }}
.speaker-line {{ display: flex; flex-wrap: wrap; align-items: center; column-gap: 7px; row-gap: 5px; margin: 0 0 9px 2px; line-height: 1.4; }}
.speaker {{ color: var(--accent, var(--muted)); font-size: .76rem; font-weight: 600; }}
.speaker-tone {{ color: #a3ae9a; font-size: .65rem; margin-left: 2px; }}
.address-chip {{ padding: 1px 5px; border: 1px solid #43513e; border-radius: 2px; color: #bfc9b5; font-size: .6rem; }}
.bubble {{ position: relative; padding: 16px 20px; border: 1px solid #576246; border-radius: 5px; color: var(--text); background: var(--panel-strong); line-height: 1.85; white-space: pre-wrap; overflow-wrap: anywhere; box-shadow: 3px 3px 0 #101912; }}
.bubble-text {{ position: relative; }}
.message.npc-message:has(.has-character-frame) {{ margin-top: 34px; margin-bottom: 40px; }}
.has-character-frame {{ min-width: 164px; min-height: 98px; padding: 34px 32px 36px; isolation: isolate; }}
.bubble-frame {{ position: absolute; inset: -15px; z-index: -1; pointer-events: none; user-select: none; line-height: 0; }}
.bubble-frame svg {{ display: block; width: 100%; height: 100%; overflow: visible; image-rendering: pixelated; }}
.message:has(.has-character-frame) .speaker-line {{ margin-bottom: 22px; }}
.message.npc-message .bubble {{ border-color: var(--border, #576246); background: var(--bubble, var(--panel-strong)); box-shadow: inset 0 0 0 3px rgba(17,18,27,.22), 3px 3px 0 #101912; }}
.message.npc-message .avatar {{ color: var(--accent); border-color: var(--border); background: var(--bubble); }}
.message.npc-message.continued {{ margin-top: 12px; }}
.message.continued .avatar {{ visibility: hidden; }}
.message.continued .speaker-line {{ display: none; }}
.message.player {{ flex-direction: row-reverse; margin-top: 24px; margin-bottom: 32px; }}
.message.player .avatar {{ color: #e4c88a; background: #3c3d2a; border-color: #a69a62; font-size: .83rem; }}
.message.player .speaker {{ text-align: right; color: #b9b59b; margin: 0 2px 9px 0; font-size: .67rem; }}
.message.player .bubble {{ border-color: #dfc48a; color: #3e3827; background: #e6d4a4; box-shadow: inset 0 0 0 3px #d6bf88, 3px 3px 0 #101912; font-size: .86rem; }}
.analysis {{ display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(200px, 1fr); gap: 20px; padding: 18px 30px 25px; border-top: 1px solid #354330; background: #1b241f; }}
.insight h3, .checks h3 {{ margin: 0 0 9px; color: #9baa90; font-size: .67rem; font-weight: 500; letter-spacing: .04em; }}
.insight p {{ margin: 0; color: #bfc8b3; line-height: 1.85; font-size: .75rem; }}
.check-row {{ gap: 5px; }}
.check {{ padding: 2px 5px; font-size: .6rem; background: transparent; }}
.footnote {{ margin: 18px 4px 0; color: #8a9980; font-size: .68rem; line-height: 1.85; }}
@media (max-width: 1000px) {{
  .page {{ width: calc(100% - 40px); }}
  .review-shell {{ grid-template-columns: 218px minmax(0, 1fr); gap: 18px; }}
  .detail-title-row {{ flex-direction: column; gap: 12px; }}
  .badge-row {{ max-width: none; justify-content: flex-start; }}
  .detail-head, .conversation, .analysis {{ padding-left: 24px; padding-right: 24px; }}
  .analysis {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 760px) {{
  .page {{ width: calc(100% - 28px); padding-top: 24px; }}
  .review-shell {{ grid-template-columns: 1fr; gap: 24px; }}
  .sidebar {{ position: static; }}
  .case-list {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .sidebar .footnote {{ display: none; }}
  .topbar {{ display: block; margin-bottom: 18px; }}
  .back {{ display: inline-block; margin-top: 14px; }}
  .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .stat {{ padding: 12px 14px; }}
  .stat:nth-child(2) {{ border-right: 0; }}
  .stat:nth-child(-n+2) {{ border-bottom: 1px solid var(--line); }}
}}
@media (max-width: 480px) {{
  .case-list {{ grid-template-columns: 1fr; }}
  .detail-head, .conversation, .analysis {{ padding-left: 16px; padding-right: 16px; }}
  .message {{ gap: 11px; }}
  .avatar {{ flex-basis: 38px; width: 38px; height: 38px; }}
  .bubble-wrap {{ max-width: calc(100% - 49px); }}
  .message.npc-message .bubble-wrap {{ max-width: calc(100% - 59px); }}
  .bubble {{ padding: 14px 16px; font-size: .9rem; }}
  .bubble.has-character-frame {{ padding: 32px 28px 34px; }}
  .speaker-tone {{ font-size: .6rem; }}
  .badge-row {{ gap: 5px; }}
}}
  </style>
</head>
<body data-bubble-design="character-frames-v2">
<main class="page">
  <header class="topbar">
    <div>
      <div class="eyebrow">Dialogue Lab / Group Review</div>
      <h1>线上群聊 · 云端样本回放</h1>
  <p class="subtitle">这里只回放已生成结果，不会再次请求模型；把“谁在说、说了什么、问题在哪里”拆开看。当前批次 <b id="batch-name">{batch_name}</b>。</p>
  <nav class="batch-nav" aria-label="批次切换">{batch_links}</nav>
    </div>
    <a class="back" href="/test/group">← 返回实验台</a>
  </header>
  <section class="stats" id="review-stats" aria-label="批次统计"></section>
  <section class="review-shell">
    <aside class="sidebar">
      <div class="sidebar-head"><strong>案例列表</strong><span id="case-count"></span></div>
      <div class="case-list" id="case-list"></div>
      <p class="footnote">绿色表示协议检查通过；黄色表示协议没问题，但对白里有值得继续收口的角色表现。</p>
    </aside>
    <article class="detail" id="case-detail" aria-live="polite"></article>
  </section>
</main>
<script id="group-review-data" type="application/json">{serialized}</script>
<script>
(() => {{
  const data = JSON.parse(document.getElementById("group-review-data").textContent);
  const records = Array.isArray(data.records) ? data.records : [];
  const observations = {observations_json};
  const SPEAKER_GLYPHS = {glyphs_json};
  const CHARACTER_ORNAMENTS = {ornaments_json};
  const NPC_ALIASES = {aliases_json};
  const canonicalNpcId = (npcId) => Object.hasOwn(NPC_ALIASES, npcId) ? NPC_ALIASES[npcId] : npcId;
  const ornamentFor = (npcId) => Object.hasOwn(CHARACTER_ORNAMENTS, canonicalNpcId(npcId)) ? CHARACTER_ORNAMENTS[canonicalNpcId(npcId)] : null;
  const glyphFor = (npcId) => Object.hasOwn(SPEAKER_GLYPHS, canonicalNpcId(npcId)) ? SPEAKER_GLYPHS[canonicalNpcId(npcId)] : "";
{_CHARACTER_FRAME_SCRIPT}
  const frameObserver = new ResizeObserver(entries => {{
    entries.forEach((entry) => {{
      const bubble = entry.target;
      const frame = bubble.querySelector(".bubble-frame");
      const ornament = ornamentFor(bubble.dataset.npc);
      if (!frame || !ornament) return;
      const rect = bubble.getBoundingClientRect();
      frame.innerHTML = characterFrameSvg(rect.width, rect.height, ornament, Number(bubble.dataset.frameVariant));
    }});
  }});
  const list = document.getElementById("case-list");
  const detail = document.getElementById("case-detail");
  const count = document.getElementById("case-count");
  const stats = document.getElementById("review-stats");
  let selected = 0;

  const el = (tag, className, text) => {{
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }};
  const recordId = (record) => record.caseId || "未命名案例";
  const participantNames = (record) => {{
    const raw = (record.request && record.request.participants) || [];
    return raw.map((item) => (typeof item === "string" ? item : (item && (item.npcId || item.displayName)) || "?"));
  }};
  const participants = participantNames;
  const response = (record) => record.response || {{}};
  const turns = (record) => response(record).turns || [];
  const hasObservation = (record) => Boolean(observations[recordId(record)]);
  const shortName = (value) => String(value || "?").slice(0, 1);
  const prettyTitle = (record) => participants(record).join(" + ") || recordId(record);
  const STRATEGY_LABELS = {{ fanout: "多人回应", turn_based: "轮流单发言人", multi_turn: "自然接话流（可插话）" }};
  const STRATEGY_NOTES = {{
    fanout: "当前批次：多人回应 · 每位参与者各接一轮；实验台可切换“自然接话流（可插话）”",
    turn_based: "当前批次：轮流单发言人 · 每次只记录当前发言人一轮",
    multi_turn: "当前批次：自然接话流 · 允许有人不发言、有人插话、同一人连续补一句",
  }};
  const strategyOf = (record) => (record.request && record.request.strategy) || "unknown";
  const strategyLabelOf = (record) => STRATEGY_LABELS[strategyOf(record)] || strategyOf(record);
  const speakerIds = (record) => [...new Set(turns(record).map((turn) => turn.speakerNpcId).filter(Boolean))];
  const NPC_STYLES = {styles_json};
  const styleFor = (npcId) => Object.hasOwn(NPC_STYLES, canonicalNpcId(npcId)) ? NPC_STYLES[canonicalNpcId(npcId)] : {{ icon: "•", tone: "参与者", className: "guest", accent: "#a990ff", accentSoft: "#79d9db", bubble: "var(--panel-strong)", border: "var(--line)" }};

  function renderStats() {{
    stats.replaceChildren();
    const allOk = records.length > 0 && records.every((item) => item.status === "ok");
    const strategies = [...new Set(records.map((record) => strategyLabelOf(record)))];
    const values = [
      ["样本案例", String(records.length), ""],
      ["成功返回", `${{records.filter((item) => item.status === "ok").length}} / ${{records.length}}`, "green"],
      ["协议状态", allOk ? "全部通过" : "需复核", "cyan"],
      ["生成策略", strategies.length ? strategies.join(" / ") : "—", "gold"],
    ];
    values.forEach(([label, value, tone]) => {{
      const card = el("div", "stat"); card.append(el("span", "stat-label", label), el("strong", `stat-value ${{tone}}`, value)); stats.append(card);
    }});
    count.textContent = `${{records.length}} 个案例`;
  }}

  function renderList() {{
    list.replaceChildren();
    records.forEach((record, index) => {{
      const button = el("button", `case-button${{index === selected ? " active" : ""}}${{hasObservation(record) ? " watch" : ""}}`);
      button.type = "button";
      button.append(el("span", "case-dot"));
      const people = participants(record).length;
      const text = el("span"); text.append(el("span", "case-title", prettyTitle(record)), el("span", "case-meta", `${{people}} 人参与 · ${{speakerIds(record).length}} 人发言 · ${{turns(record).length}} 回合`)); button.append(text);
      button.append(el("span", "case-index", String(index + 1).padStart(2, "0")));
      button.addEventListener("click", () => {{ selected = index; renderList(); renderDetail(); }});
      list.append(button);
    }});
  }}

  function renderChecks(record) {{
    const checks = record.checks || {{}};
    const items = [
      ["线上频道", checks.remoteChannel], ["云端生成", checks.providerCloud], ["无 fallback", checks.noFallback], ["全员发言（自然流允许缺席）", checks.allParticipantsReplied], ["发言人合规", checks.speakersInRoster],
    ];
    const box = el("div", "checks"); box.append(el("h3", "", "协议检查 · 协议通过"));
    const row = el("div", "check-row"); items.forEach(([label, ok]) => row.append(el("span", `check ${{ok ? "success" : ""}}`, `${{ok ? "✓" : "!"}} ${{label}}`))); box.append(row); return box;
  }}

  function renderDetail() {{
    frameObserver.disconnect();
    const record = records[selected];
    if (!record) {{ detail.replaceChildren(el("div", "detail-empty", "这批次还没有可回放的对白。")); return; }}
    const res = response(record);
    const head = el("header", "detail-head");
    const titleRow = el("div", "detail-title-row");
    const titleBlock = el("div"); titleBlock.append(el("div", "eyebrow", `CASE ${{String(selected + 1).padStart(2, "0")}}`), el("h2", "", prettyTitle(record)), el("div", "detail-id", recordId(record))); titleRow.append(titleBlock);
    const badges = el("div", "badge-row"); badges.append(el("span", "badge success", "✓ 返回正常"), el("span", "badge channel", "线上 remote"), el("span", "badge", `${{strategyLabelOf(record)}} · ${{turns(record).length}} 回合 · ${{speakerIds(record).length}}/${{participants(record).length}} 人发言`)); titleRow.append(badges); head.append(titleRow);
    const people = el("div", "participant-row");
    participants(record).forEach((name) => {{
      const chip = el("span", "participant", name);
      chip.style.setProperty("--accent", styleFor(name).accent);
      people.append(chip);
    }});
    head.append(people);
    const topic = el("div", "topic"); topic.append(el("b", "", "玩家抛出的主题"), document.createTextNode(record.request?.message || "未记录")); head.append(topic);
    const convo = el("section", "conversation"); convo.append(el("div", "conversation-label", "Conversation replay"), el("div", "rhythm-note", STRATEGY_NOTES[strategyOf(record)] || `当前批次：${{strategyLabelOf(record)}}`));
    const player = el("div", "message player"); player.append(el("div", "avatar", "我")); const playerWrap = el("div", "bubble-wrap"); playerWrap.append(el("div", "speaker", "玩家"), el("div", "bubble", record.request?.message || "")); player.append(playerWrap); convo.append(player);
    let previousSpeaker = "";
    const speakerOccurrences = new Map();
    turns(record).forEach((turn) => {{
      const speakerId = turn.speakerNpcId || "";
      const style = styleFor(speakerId);
      const continued = speakerId && speakerId === previousSpeaker;
      const msg = el("div", `message npc-message role-${{style.className}}${{continued ? " continued" : ""}}`);
      msg.style.setProperty("--accent", style.accent); msg.style.setProperty("--accent-soft", style.accentSoft); msg.style.setProperty("--bubble", style.bubble); msg.style.setProperty("--border", style.border);
      const glyph = glyphFor(speakerId);
      const avatar = el("div", "avatar");
      if (glyph) {{ const holder = el("span", "avatar-glyph"); holder.innerHTML = glyph; avatar.append(holder); }} else {{ avatar.textContent = style.icon; }}
      msg.append(avatar);
      const wrap = el("div", "bubble-wrap");
      const speakerLine = el("div", "speaker-line"); speakerLine.append(el("span", "speaker-dot"), el("span", "speaker", speakerId || "未知发言人"), el("span", "speaker-tone", style.tone));
      if (Array.isArray(turn.addressedTo) && turn.addressedTo.length) speakerLine.append(el("span", "address-chip", `→ ${{turn.addressedTo.join("、")}}`));
      const bubble = el("div", "bubble");
      bubble.append(el("span", "bubble-text", turn.content || ""));
      bubble.dataset.npc = speakerId;
      const occurrence = speakerOccurrences.get(canonicalNpcId(speakerId)) || 0;
      bubble.dataset.frameVariant = String(occurrence);
      speakerOccurrences.set(canonicalNpcId(speakerId), occurrence + 1);
      const ornament = ornamentFor(speakerId);
      if (ornament) {{
        bubble.classList.add("has-character-frame");
        const frame = el("span", "bubble-frame");
        frame.setAttribute("aria-hidden", "true");
        bubble.append(frame);
        frameObserver.observe(bubble);
      }}
      wrap.append(speakerLine, bubble); msg.append(wrap); convo.append(msg); previousSpeaker = speakerId;
    }});
    const analysis = el("section", "analysis"); const insight = el("div", "insight"); insight.append(el("h3", "", "角色观察"), el("p", "", observations[recordId(record)] || "本案例暂无额外观察。")); analysis.append(insight, renderChecks(record));
    detail.replaceChildren(head, convo, analysis);
  }}

  renderStats(); renderList(); renderDetail();

  // 切回这个标签页时自动取最新结果，于是固定 URL 就能一直用，不必新开页面。
  const loadedAt = Date.now();
  document.addEventListener("visibilitychange", () => {{
    if (!document.hidden && Date.now() - loadedAt > 2000) location.reload();
  }});
}})();
</script>
</body>
</html>'''
