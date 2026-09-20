"""把 astra 的群聊气泡资产导出为 SMAPI 可用的素材。

产出：
  1. smapi/assets/npc_bubbles.png  —— 46 个角色图标的横向图集（每格 24×24，透明底）
  2. smapi/NpcBubbleStyle.cs       —— 角色 → 调色板 / 特征标签 / 图集索引

数据源是 bridge 侧的 npc_bubble_elements.py，不复制、不改写那份定义。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"E:\workspace\projects\stardew-ai-npc.worktrees\story-memory")
sys.path.insert(0, str(ROOT / "bridge" / "src"))

from stardew_ai_bridge.npc_bubble_elements import (  # noqa: E402
    NPC_BUBBLE_ALIASES,
    NPC_BUBBLE_ELEMENTS,
)

# 颜色解析与「设计色 → tint」的反推都只有一份实现：bridge 侧的 npc_bubble_tint
# （两个预览页 /test/ui 与 /test/ui-redesign 也从那里取）。这里不再复制公式与基准色。
from stardew_ai_bridge.npc_bubble_tint import (  # noqa: E402
    bubble_to_tint,
    parse_color,
)

CELL = 24
FRAME_CELL = 32
OUT_PNG = ROOT / "smapi" / "assets" / "npc_bubbles.png"
OUT_CS = ROOT / "smapi" / "NpcBubbleStyle.cs"


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


# ── 设计色 → tint 的反推（2026-09-20） ────────────────────────────────────
#
# 气泡底色在游戏里是 `IClickableMenu.drawTextureBox(b, x, y, w, h, tint)` 画出来的，
# 最终色 = 纹理色 × tint ÷ 255（逐通道）。而 npc_bubble_elements.py 里的 palette.bubble
# 是**设计色**——回放页把它当 CSS 背景色直接铺，所以它必须是「最终色」。
#
# 把这个设计色直接当 tint 传进 C#，橙黄的木纹就会把它乘偏：
# Sophia 的品红 (105,43,84) 会被渲染成暗红 (104,31,36)，色相从 hue 320 偏到 ≈355，
# 明度也掉一档——「气泡不该是这个颜色」就是这么来的。
#
# 所以导出时按纹理基准色反推：tint = 设计色 × 255 ÷ 基准色。回乘即可还原设计色。
# 基准色取 MenuTiles (0,256,60,60) 九宫格**中心块**的主色（20×20 里占一半的那一色），
# 因为气泡的中心区正是被拉伸的这块；该块另有 3 个近邻色（#ffc576 / #f5b56f / #f5b565），
# 用主色反推时它们的偏差在 7 个色阶以内。
# 常量与实现见 stardew_ai_bridge.npc_bubble_tint（BUBBLE_TEX_BASE = (253, 188, 110) = #fdbc6e），
# 上面 import 进来的 bubble_to_tint 就是它 —— 本文件不再自带一份。

# 注意：玩家气泡与 NPC 兜底气泡**不走这条反推**。
# 它们的设计色（浅蓝 (226,239,246) / 浅紫 (239,231,244)）在 G、B 通道上高于上面的基准色
# （239 > 188、246 > 110），反推出来是 324 / 570，超过乘法 tint 的上限 255，乘不出来。
# 所以那两处在 smapi/ChatBubbleDrawing.cs 里改用 Maps\MenuTilesUncolored（基色近白 248），
# 由 ToPanelTint 反推成 (232,246,253) 与 (246,238,251)，回乘即还原设计色。
# 本文件继续负责 46 个角色的专属配色：43 个各通道都在基准色以内，回乘无损；
# 另有 3 个深蓝角色（Maru / Mermaid / Henchman）的 B 通道超出基准色 110，被 min() 压到 110，
# 渲染后 B 比设计色暗 7~9 个色阶——这是乘法 tint 的硬边界，要彻底消掉同样得换未着色面板。


def write_csharp(names: list[str]) -> None:
    rows: list[str] = []
    for index, npc in enumerate(names):
        element = NPC_BUBBLE_ELEMENTS[npc]
        palette = element["palette"]
        # palette.bubble 是设计色（回放页直接铺的颜色），进 C# 前要反推成 tint，
        # 否则会被 drawTextureBox 乘上橙黄木纹而偏色。见 bubble_to_tint 的说明。
        bubble = bubble_to_tint(parse_color(palette["bubble"]))
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
