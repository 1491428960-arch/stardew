"""设计色 → tint 的乘法反推（唯一来源）。

气泡底色在游戏里是 `IClickableMenu.drawTextureBox(Maps\\MenuTiles (0,256,60,60), tint)` 画出来的：
**最终色 = 纹理色 × tint ÷ 255**（逐通道）。而 `npc_bubble_elements.py` 里的
`palette.bubble` 是**设计色** —— 回放页把它当 CSS 背景色直接铺，所以它必须是「最终色」。

把设计色直接当 tint 传给彩色面板，橙黄的木纹会**再乘一次**：

* Abigail 的设计色 (65,44,109) → 渲染成 (64,32,47)（整体暗一档、B 通道掉得最狠）；
* Sophia 的品红 (105,43,84) → 渲染成暗红 (104,32,36)（hue 320 偏到 ≈355）。

所以凡是要把设计色画进「彩色 MenuTiles」的地方，一律先反推：

    tint = 设计色 × 255 ÷ 基色        （逐通道，上限 255）

基色取 `MenuTiles (0,256,60,60)` 九宫格**中心块**的主色 `#fdbc6e`（气泡中心区正是被拉伸的
这块；该块另有 3 个近邻色 #ffc576 / #f5b56f / #f5b565，用主色反推时它们的偏差在 7 个色阶内），
回乘即可还原设计色。

**反推公式只有本模块这一份**：:func:`to_tint` 把基色收成参数，两种面板各传各的基色 ——

* 彩色 `Maps\\MenuTiles`（#fdbc6e）：:data:`BUBBLE_TEX_BASE` + :func:`bubble_to_tint`；
* 去色版 `Maps\\MenuTilesUncolored`（近白 248）：`npc_bubble_panel_plain.py` 的
  `PLAIN_PANEL_BASE` + `to_panel_tint`（那里只保留一层薄封装，不再自带公式）。

此前这两个模块各有一份同形状实现、基色写死在函数体里，正是本项目反复抓到的「同概念多实现」。

消费点都指向本模块，不再各自复制公式与基准色：

* `scripts/export_npc_bubble_assets.py` —— 导出 `smapi/NpcBubbleStyle.cs`
  （C# 侧 `NpcBubbleStyle.Bubble` 就是这里的返回值）；
* `scripts/build_bubble_texture.py` —— 生成描边归一变体，直接 import 本模块的
  :data:`BUBBLE_TEX_BASE`（此前它自带一份同值副本，靠注释人工同步）；
* `ui_preview_page.py`（`/test/ui`）与 `ui_preview_redesign_page.py`（`/test/ui-redesign`
  的现状栏与新设计栏）—— 服务端算好、经 styles payload 交给 JS，页面里只消费结果。

**玩家气泡与 NPC 兜底气泡走的是同一条公式、不同的基色**：它们的设计色在 G / B 通道高于
彩色面板基色（239 > 188、246 > 110），反推值 324 / 570 超过乘法 tint 的上限 255，彩色面板
乘不出来 —— 所以改用近白的 `Maps\\MenuTilesUncolored` 面板 +
`npc_bubble_panel_plain.py::to_panel_tint`。
"""

from __future__ import annotations

import re

#: `Maps\MenuTiles (0,256,60,60)` 九宫格中心块主色 #fdbc6e。
BUBBLE_TEX_BASE: tuple[int, int, int] = (253, 188, 110)

_RGBA = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)"
)


def parse_color(value: str) -> tuple[int, int, int]:
    """把 `'#rrggbb'` 或 `'rgba(r, g, b, a)'` 统一成 RGB 三元组。

    palette 里两种写法都有（`accent` 多为 hex、`bubble` 多为 rgba），游戏侧用的是不透明
    Color，所以 rgba 只取 RGB 分量。与页面里 JS `parseColor` 的口径一致。
    """

    text = value.strip()
    m = _RGBA.match(text)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    hexv = text.lstrip("#")
    if len(hexv) == 6:
        return int(hexv[0:2], 16), int(hexv[2:4], 16), int(hexv[4:6], 16)
    raise ValueError(f"无法解析颜色: {value!r}")


def to_tint(
    design: tuple[int, int, int], base: tuple[int, int, int]
) -> tuple[int, int, int]:
    """设计色 → 乘法 tint 的**唯一反推实现**：`tint = 设计色 × 255 ÷ 基色`（逐通道，上限 255）。

    基色是面板九宫格中心块的主色 —— 彩色 `Maps\\MenuTiles` 是 #fdbc6e，去色版
    `Maps\\MenuTilesUncolored` 是近白 (248, 248, 248)。两种面板的规则只差这一个参数，
    所以只保留这一份实现：:func:`bubble_to_tint` 与
    `npc_bubble_panel_plain.to_panel_tint` 都是把基色填好的一层薄封装。
    """

    return tuple(
        min(255, round(channel * 255 / reference))
        for channel, reference in zip(design, base)
    )


def bubble_to_tint(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """把设计色反推成 tint，使 `drawTextureBox` 乘完**彩色**面板后正好回到设计色。

    本函数的函数体只有一次委托 —— 公式本体在 :func:`to_tint`，这里只补上彩色面板的基色。
    """

    return to_tint(rgb, BUBBLE_TEX_BASE)


def bubble_tint_of(value: str) -> tuple[int, int, int]:
    """`palette.bubble` 的原始字符串 → 彩色面板的 tint（解析与反推合一，调用方最常用的一条）。"""

    return bubble_to_tint(parse_color(value))
