"""气泡专用的 MenuTiles 九宫格变体（自动生成，勿手改）。

气泡底是 `IClickableMenu.drawTextureBox(Maps\\MenuTiles (0,256,60,60), tint)` 画出来的，
最终色 = 纹理色 × tint ÷ 255。这块贴图**自带的描边是红橙色**（(177,78,5)，饱和度 0.97、
B 通道只有 5）：白 tint 下面板/按钮是木框本色，没问题；可角色气泡的 tint 是紫红/靛蓝
这类深色，描边的 B 通道乘完仍是 5×84÷255 ≈ 2 —— 「紫红底色」旁边就围了一圈**橙红**的边。

本文件把**描边像素的色相归一到填充基准色**（(253, 188, 110) = #fdbc6e），
逐像素保留相对亮度：

    新描边 = base × (亮度(p) ÷ 亮度(base))

于是对任意 tint 都有「描边最终色 = 填充最终色 × 同一比例」，边框就是底色的暗版本，
四档明暗与圆角形状一个像素不动，木框质感与纹理全部保留。

* 描边映射：(133, 54, 5)→(92, 68, 40), (177, 78, 5)→(127, 94, 55), (250, 147, 5)→(206, 153, 90), (220, 123, 5)→(177, 131, 77)
* 填充 1296 px（13 色）**逐像素原样保留**，纹理色差不受影响；
* 只改这一块 60×60 裁剪 —— 面板 / 按钮 / 凹槽共用的那份贴图原封不动；
* 基准色取自 `stardew_ai_bridge.npc_bubble_tint::BUBBLE_TEX_BASE`（脚本直接 import，不是副本）。

生成脚本：scripts/build_bubble_texture.py（只读游戏解包目录，幂等）
源 MenuTiles.png → 60x60，png 351B
"""

from __future__ import annotations

# Maps\MenuTiles.xnb (0,256,60,60)；按 MENU_TEX 的切法使用（slice = 20）。
BUBBLE_MENU_TEX_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADwAAAA8CAYAAAA6/NlyAAABJklEQVR42u3bPwtBURjH8XOkTLLdQZlEZgtlUnarQd6KvAbvQAYrszIpFmVQJJMy2ETulevPfM9wpTOc++f7jHTr+fQ8v84d7pHiR7UbpY8IUQ2nW+n3f0LErABHvZLqD91OxZPZZi0fKlA+m/H03xssJSsNOMoZVs9ZNbPj+SFUILX/w+nyYaUBx+kcPp6vvg+06tVAAUazxV/9s9KAo57hX1Uqpow2vNvcmDBgwIABA47tOfy2HaMNu+6LCQMGDBgw4Niew85DGm34+WLCgAHrZFiIu9mO3y4TBgxYJ8OGIyyekgkDBqyRYVuafZd2JRMGDFgnw/3JmgkDBhygDKt3BNTvjcsFy/NAzkoHCqB+l7Xan4XfHQhWGnDESnJviZUGHOr6Ahz2QZq7szv6AAAAAElFTkSuQmCC"
)
