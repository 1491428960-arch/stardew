"""玩家 / NPC 兜底气泡专用的「未着色面板」九宫格（自动生成，勿手改）。

`Maps\MenuTilesUncolored`（游戏内 `Game1.uncoloredMenuTexture`）是 `Maps\MenuTiles` 的
**去色版**：alpha 轮廓逐像素相同，底板色区从 #fdbc6e 换成近白 (248,248,248)，
描边也从红橙换成冷灰紫。九宫格的源区与切法一个字节没变 —— `(0,256,60,60)`、slice = 20。

**这两个气泡为什么必须换贴图**：彩色面板的基色 #fdbc6e 只有 G 188 / B 110，
而玩家气泡（浅蓝）与 NPC 兜底气泡（浅紫）的设计色在 G / B 上比基色还高
（反推要 324 / 570）—— 乘法 tint 最多到 1.0 倍，那些颜色根本乘不出来，
直接当 tint 只会被橙黄木纹染成橙棕。换成近白面板后反推值落在 255 以内，回乘即还原设计色。

**角色气泡不受影响**：46 个角色的专属配色本来就在基准色域内，继续用彩色 MenuTiles 的
描边归一变体（见 `npc_bubble_texture.py`）与各自的 tint。

与 `smapi/ChatBubbleDrawing.cs` 的 `PanelSource` / `PanelBase` / `ToPanelTint`
（:42-60、:178-193）同源：**改一处必须同步另一处**，包括下面两个 tint 常量。

生成脚本：.tmp/ui-preview/_build_plain_panel.py（只读游戏解包目录，幂等）
源 MenuTilesUncolored.png → 60x60，png 322B
"""

from __future__ import annotations

# Maps\MenuTilesUncolored.xnb (0,256,60,60)；按 MENU_TEX 的切法使用（slice = 20）。
PLAIN_MENU_TEX_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAABCUlEQVR42u3bIQ6DQBBA0d0G1wRbxzF6gq7iBOCqGmxFE05AUlFLGgQOXYPiBj0GB0CQNAG1tV0EpAoW/jjYkMzLzGTMIsVEnM83LSyKPL/LsfOd2FgAXns4wxdFURkzGwQnq0BKKSP/MFSSlga85hke7tnhzMbxwypQklyN56oyfbQ04LXv4bZtRz+IosuiAGn6/Ct/Whrw2md4KjxvP2vCdf2hwoABAwYMeLN7uO97KgwYMGDAgAHPtIe7rrMtZVoaMDP8E1prKgwYsMUz3DTNvAk7ByoMGDBgwIA3u4ez7EWFAQNeTsip+9K+fzTOXdddFGB4L6ss34L70oC3PMOC/5ZoacA2xRfbhTuzfwTZrwAAAABJRU5ErkJggg=="
)

# 九宫格中心块的主色（实测 20×20 里占 160/400 px，近邻 255 / 240 / 239）——
# smapi/ChatBubbleDrawing.cs::PanelBase 用的就是它。
PLAIN_PANEL_BASE: tuple[int, int, int] = (248, 248, 248)

# 两个设计色（= 游戏里最终看到的颜色）与把它们反推出来的 tint。
PLAYER_BUBBLE_DESIGN: tuple[int, int, int] = (226, 239, 246)
NPC_FALLBACK_BUBBLE_DESIGN: tuple[int, int, int] = (239, 231, 244)
PLAYER_BUBBLE_TINT: tuple[int, int, int] = (232, 246, 253)
NPC_FALLBACK_BUBBLE_TINT: tuple[int, int, int] = (246, 238, 251)


def to_panel_tint(design: tuple[int, int, int]) -> tuple[int, int, int]:
    """设计色 → 未着色面板的 tint：tint = 设计色 × 255 ÷ 基色（逐通道，上限 255）。

    与 `smapi/ChatBubbleDrawing.cs::ToPanelTint` 同一条公式；上面两个 tint 常量就是
    用它算出来的（改设计色时重跑生成脚本，别手改常量）。
    """

    return tuple(
        min(255, round(channel * 255 / base))
        for channel, base in zip(design, PLAIN_PANEL_BASE)
    )
