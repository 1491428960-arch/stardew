"""把 astra 的群聊气泡资产导出为 SMAPI 可用的素材。

产出：
  1. smapi/assets/npc_bubbles.png  —— 46 个角色图标的横向图集（每格 24×24，透明底）
  2. smapi/NpcBubbleStyle.cs       —— 角色 → 调色板 / 特征标签 / 图集索引

数据源是 bridge 侧的 npc_bubble_elements.py，不复制、不改写那份定义。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"E:\workspace\projects\stardew-ai-npc.worktrees\story-memory")
sys.path.insert(0, str(ROOT / "bridge" / "src"))

from stardew_ai_bridge.npc_bubble_elements import (  # noqa: E402
    NPC_BUBBLE_ALIASES,
    NPC_BUBBLE_ELEMENTS,
)

CELL = 24
FRAME_CELL = 32
OUT_PNG = ROOT / "smapi" / "assets" / "npc_bubbles.png"
OUT_CS = ROOT / "smapi" / "NpcBubbleStyle.cs"

_RGBA = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)"
)


def parse_color(value: str) -> tuple[int, int, int]:
    """把 '#rrggbb' 或 'rgba(r, g, b, a)' 统一成 RGB 三元组。"""
    m = _RGBA.match(value.strip())
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    hexv = value.strip().lstrip("#")
    if len(hexv) == 6:
        return int(hexv[0:2], 16), int(hexv[2:4], 16), int(hexv[4:6], 16)
    raise ValueError(f"无法解析颜色: {value!r}")


def build_sheet_html(names: list[str]) -> str:
    cells: list[str] = []
    for npc in names:
        element = NPC_BUBBLE_ELEMENTS[npc]
        motif = element["motifs"][0]
        accent = element["palette"]["accent"]
        accent_soft = element["palette"]["accentSoft"]
        cells.append(
            f'<div class="cell" style="color:{accent};--accent-soft:{accent_soft}">'
            f'<svg viewBox="0 0 24 24" width="{CELL}" height="{CELL}" '
            f'shape-rendering="crispEdges">{motif}</svg></div>'
        )
    return (
        '<!doctype html><meta charset="utf-8"><style>'
        "*{margin:0;padding:0;box-sizing:border-box}"
        "html,body{background:transparent}"
        f"#sheet{{display:flex;width:{CELL * len(names)}px;height:{CELL}px}}"
        f".cell{{width:{CELL}px;height:{CELL}px;flex:0 0 {CELL}px}}"
        "svg{display:block;image-rendering:pixelated}"
        f'</style><div id="sheet">{"".join(cells)}</div>'
    )


def export_sheet(names: list[str]) -> None:
    from playwright.sync_api import sync_playwright

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    width = CELL * len(names)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": CELL},
            device_scale_factor=1,
        )
        page.set_content(build_sheet_html(names))
        page.locator("#sheet").screenshot(
            path=str(OUT_PNG), omit_background=True
        )
        browser.close()
    print(f"图集已写出: {OUT_PNG}  ({width}x{CELL}, {len(names)} 格)")


def csharp_color(rgb: tuple[int, int, int]) -> str:
    return f"new Color({rgb[0]}, {rgb[1]}, {rgb[2]})"


def write_csharp(names: list[str]) -> None:
    rows: list[str] = []
    for index, npc in enumerate(names):
        element = NPC_BUBBLE_ELEMENTS[npc]
        palette = element["palette"]
        bubble = parse_color(palette["bubble"])
        border = parse_color(palette["border"])
        accent = parse_color(palette["accent"])
        ornament = element["ornament"]
        colors = ornament["colors"]
        rows.append(
            f'        ["{npc}"] = new NpcBubbleStyle({index}, '
            f'{csharp_color(bubble)}, {csharp_color(border)}, '
            f'{csharp_color(accent)}, "{element["tone"]}", '
            f'{index}, "{ornament["kind"]}", '
            f'{csharp_color(parse_color(colors["line"]))}, '
            f'{csharp_color(parse_color(colors["highlight"]))}, '
            f'{csharp_color(parse_color(colors["leaf"]))}, '
            f'{csharp_color(parse_color(colors["leafHi"]))}),'
        )

    alias_rows = [
        f'        ["{alias}"] = "{target}",'
        for alias, target in sorted(NPC_BUBBLE_ALIASES.items())
    ]

    source = f'''using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

namespace StardewAI.NPC;

/// <summary>
/// 角色气泡视觉样式；数据由 <c>scripts/export_npc_bubble_assets.py</c> 从
/// bridge 侧的 <c>npc_bubble_elements.py</c> 生成，请勿手改。
/// 图集见 assets/npc_bubbles.png（每格 {CELL}×{CELL}，横向排列）。
/// </summary>
public sealed record NpcBubbleStyle(
    int SheetIndex,
    Color Bubble,
    Color Border,
    Color Accent,
    string Tone,
    int FrameRow,
    string FrameKind,
    Color FrameLine,
    Color FrameHighlight,
    Color FrameLeaf,
    Color FrameLeafHi)
{{
    /// <summary>图标图集的单元格边长。</summary>
    public const int CellSize = {CELL};

    /// <summary>装饰零件图集的单元格边长。</summary>
    public const int FrameCellSize = {FRAME_CELL};

    /// <summary>角色图标图集，由 ModEntry 启动时注入；缺失时退回纯配色绘制。</summary>
    public static Texture2D? Sheet {{ get; set; }}

    /// <summary>装饰零件图集（细节造型 + 两个大物件），同样由 ModEntry 注入。</summary>
    public static Texture2D? FrameSheet {{ get; set; }}

    /// <summary>该角色在图集中的单元格。</summary>
    public Rectangle SheetSource =>
        new(SheetIndex * CellSize, 0, CellSize, CellSize);

    /// <summary>装饰零件单元格：0 = 细节造型，1/2 = 大物件。</summary>
    public Rectangle FrameSource(int column) =>
        new(column * FrameCellSize, FrameRow * FrameCellSize, FrameCellSize, FrameCellSize);

    private static readonly IReadOnlyDictionary<string, NpcBubbleStyle> Styles =
        new Dictionary<string, NpcBubbleStyle>(StringComparer.OrdinalIgnoreCase)
{{
{chr(10).join(rows)}
        }};

    private static readonly IReadOnlyDictionary<string, string> Aliases =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
{{
{chr(10).join(alias_rows)}
        }};

    /// <summary>未知角色回落到中性样式，绝不抛异常打断绘制。</summary>
    public static NpcBubbleStyle? For(string? npcId)
    {{
        if (string.IsNullOrWhiteSpace(npcId))
        {{
            return null;
        }}

        var key = npcId.Trim();
        if (Aliases.TryGetValue(key, out var canonical))
        {{
            key = canonical;
        }}

        return Styles.TryGetValue(key, out var style) ? style : null;
    }}
}}
'''
    OUT_CS.write_text(source, encoding="utf-8-sig")
    print(f"C# 样式表已写出: {OUT_CS}  ({len(names)} 个角色, {len(NPC_BUBBLE_ALIASES)} 个别名)")


def main() -> None:
    names = list(NPC_BUBBLE_ELEMENTS)
    export_sheet(names)
    write_csharp(names)


if __name__ == "__main__":
    main()
