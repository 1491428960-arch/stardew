"""玩家 / NPC 兜底气泡专用的「未着色面板」九宫格（自动生成，勿手改）。

`Maps\\MenuTilesUncolored`（游戏内 `Game1.uncoloredMenuTexture`）是 `Maps\\MenuTiles` 的
**去色版**：alpha 轮廓逐像素相同，底板色区从 #fdbc6e 换成近白 (248,248,248)，
描边也从红橙换成冷灰紫。九宫格的源区与切法一个字节没变 —— `(0,256,60,60)`、slice = 20。

**这两个气泡为什么必须换贴图**：彩色面板的基色 #fdbc6e 只有 G 188 / B 110，
而玩家气泡（浅蓝）与 NPC 兜底气泡（浅紫）的设计色在 G / B 上比基色还高
（反推要 324 / 570）—— 乘法 tint 最多到 1.0 倍，那些颜色根本乘不出来，
直接当 tint 只会被橙黄木纹染成橙棕。换成近白面板后反推值落在 255 以内，回乘即还原设计色。

**角色气泡不受影响**：46 个角色的专属配色本来就在基准色域内，继续用彩色 MenuTiles 的
描边归一变体（见 `npc_bubble_texture.py`）与各自的 tint。

与 `smapi/ChatBubbleDrawing.cs` 的 `PanelSource` / `PanelBase` / `ToPanelTint`
（:42-60、:178-193）同源：C# 不能 import Python，那边是**跨语言复刻**，改一处必须同步另一处。
**Python 侧的反推公式只有一份** —— `npc_bubble_tint.to_tint`；本文件只是给它补上未着色面板的
基色，公式与下面两个 tint 都不再自己抄一遍。

生成脚本：.tmp/ui-preview/_build_plain_panel.py（只读游戏解包目录，幂等）
源 MenuTilesUncolored.png → 60x60，png 322B

⚠ 重跑该生成脚本前要先同步它的模板 —— 那里面仍内联着一份同形状公式与两个 tint 数值
（本轮收敛只动了 `bridge/` 与 `scripts/`），否则本文件会被写回「两份实现」的旧形态。
"""

from __future__ import annotations

from .npc_bubble_tint import to_tint

# Maps\MenuTilesUncolored.xnb (0,256,60,60)；按 MENU_TEX 的切法使用（slice = 20）。
PLAIN_MENU_TEX_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAABCUlEQVR42u3bIQ6DQBBA0d0G1wRbxzF6gq7iBOCqGmxFE05AUlFLGgQOXYPiBj0GB0CQNAG1tV0EpAoW/jjYkMzLzGTMIsVEnM83LSyKPL/LsfOd2FgAXns4wxdFURkzGwQnq0BKKSP/MFSSlga85hke7tnhzMbxwypQklyN56oyfbQ04LXv4bZtRz+IosuiAGn6/Ct/Whrw2md4KjxvP2vCdf2hwoABAwYMeLN7uO97KgwYMGDAgAHPtIe7rrMtZVoaMDP8E1prKgwYsMUz3DTNvAk7ByoMGDBgwIA3u4ez7EWFAQNeTsip+9K+fzTOXdddFGB4L6ss34L70oC3PMOC/5ZoacA2xRfbhTuzfwTZrwAAAABJRU5ErkJggg=="
)

# 九宫格中心块的主色（实测 20×20 里占 160/400 px，近邻 255 / 240 / 239）——
# smapi/ChatBubbleDrawing.cs::PanelBase 用的就是它。
PLAIN_PANEL_BASE: tuple[int, int, int] = (248, 248, 248)

# 两个设计色（= 游戏里最终看到的颜色）。
PLAYER_BUBBLE_DESIGN: tuple[int, int, int] = (226, 239, 246)
NPC_FALLBACK_BUBBLE_DESIGN: tuple[int, int, int] = (239, 231, 244)


def to_panel_tint(design: tuple[int, int, int]) -> tuple[int, int, int]:
    """设计色 → 未着色面板的 tint：`tint = 设计色 × 255 ÷ 基色`（逐通道，上限 255）。

    公式本体只有一份 —— :func:`stardew_ai_bridge.npc_bubble_tint.to_tint`；这里只把基色
    换成 `Maps\\MenuTilesUncolored` 的中心块主色。与 `smapi/ChatBubbleDrawing.cs::ToPanelTint`
    同一条规则（那边是跨语言复刻，不是第二份 Python 实现）。
    """

    return to_tint(design, PLAIN_PANEL_BASE)


# 两个 tint 由上面那条唯一实现现算 —— 此前是 6 个手抄的数字，与设计色一旦脱节就会静默偏色。
PLAYER_BUBBLE_TINT: tuple[int, int, int] = to_panel_tint(PLAYER_BUBBLE_DESIGN)
NPC_FALLBACK_BUBBLE_TINT: tuple[int, int, int] = to_panel_tint(NPC_FALLBACK_BUBBLE_DESIGN)
