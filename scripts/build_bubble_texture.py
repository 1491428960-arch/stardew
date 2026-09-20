"""生成 bridge/src/stardew_ai_bridge/npc_bubble_texture.py。

气泡底 = `IClickableMenu.drawTextureBox(MenuTiles (0,256,60,60), tint)`，
最终色 = 纹理色 × tint ÷ 255。但这块贴图**自带的描边是红橙色**：

    描边 (177,78,5)      饱和度 0.97   B 通道只有 5
    填充 (253,188,110)   饱和度 0.57

白 tint 下面板/按钮看着是木框本色，没问题；可角色气泡的 tint 是紫红/靛蓝这类深色，
描边的 B 通道乘完仍是 5×84÷255 ≈ 2 —— 「紫红底色」旁边就围了一圈**橙红**的边。

本脚本把**描边像素的色相归一到填充基准色**，逐像素保留相对亮度：

    新描边 = base × (亮度(p) ÷ 亮度(base))

于是对任意 tint 都有「描边最终色 = 填充最终色 × 同一比例」：边框成为底色的暗版本，
四档明暗与圆角形状一个像素不动，木框质感全部保留。

* 填充像素逐像素原样保留（按饱和度分流），填充的细微色差纹理不受影响；
* 只处理这一块 60×60 裁剪，面板 / 按钮 / 凹槽共用的那份贴图不受影响；
* 输出是静态常量，运行时零依赖、零开销；脚本幂等，可重复执行。

只读游戏解包目录，不改动仓库任何源码 —— 只写 npc_bubble_texture.py 与两张核对图。
"""
from __future__ import annotations

import base64
import io
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(r"E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory")
GAME = Path(r"D:\sbeam\steamapps\common\Stardew Valley\Content (unpacked)")
SOURCE = GAME / "Maps/MenuTiles.png"
SOURCE_BOX = (0, 256, 60, 316)          # Maps\MenuTiles.xnb (0,256,60,60)
TARGET = ROOT / "bridge/src/stardew_ai_bridge/npc_bubble_texture.py"
PREVIEW_DIR = ROOT / ".tmp/ui-preview"

# 与 scripts/export_npc_bubble_assets.py::BUBBLE_TEX_BASE 同源：九宫格中心块主色 #fdbc6e。
# 两边必须一致 —— 那边用它反推 tint，这边用它定描边色相，否则设计色会对不上。
BUBBLE_TEX_BASE = (253, 188, 110)
# 描边饱和度 ≈0.97、填充 ≈0.55，两档分明，阈值取中间。
EDGE_SATURATION = 0.75


def luminance(px: tuple[int, int, int]) -> float:
    """Rec.601 亮度：游戏与浏览器都在 sRGB 直通道上做乘法，用相对亮度做比例即可。"""
    return 0.299 * px[0] + 0.587 * px[1] + 0.114 * px[2]


def saturation(px: tuple[int, int, int]) -> float:
    mx, mn = max(px), min(px)
    return 0.0 if mx == 0 else (mx - mn) / mx


def is_edge(px: tuple[int, int, int]) -> bool:
    """高饱和 = 贴图自带的红橙描边；低饱和 = 填充（含填充边的过渡色）。"""
    return saturation(px) >= EDGE_SATURATION


def normalize_edges(img: Image.Image) -> tuple[Image.Image, Counter, Counter]:
    """把描边像素映射成「填充基准色的暗版本」，返回 (结果, 描边映射表, 填充色计数)。"""
    out = img.convert("RGBA").copy()
    src, dst = img.convert("RGBA").load(), out.load()
    base_lum = luminance(BUBBLE_TEX_BASE)
    remap: Counter = Counter()
    kept: Counter = Counter()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = src[x, y]
            if a == 0:
                continue
            if not is_edge((r, g, b)):
                kept[(r, g, b)] += 1
                continue
            scale = luminance((r, g, b)) / base_lum
            new = tuple(
                min(255, max(0, round(channel * scale))) for channel in BUBBLE_TEX_BASE
            )
            dst[x, y] = (new[0], new[1], new[2], a)
            remap[((r, g, b), new)] += 1
    return out, remap, kept


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def tinted(px: tuple[int, int, int], tint: tuple[int, int, int]) -> tuple[int, int, int]:
    """复算一次游戏/浏览器的着色：纹理色 × tint ÷ 255。"""
    return tuple(round(c * t / 255) for c, t in zip(px, tint))


def main() -> None:
    source = Image.open(SOURCE).convert("RGBA").crop(SOURCE_BOX)
    result, remap, kept = normalize_edges(source)

    print(f"源 {SOURCE.name} 裁剪 {SOURCE_BOX} → {source.size[0]}x{source.size[1]}")
    print(f"\n描边像素（饱和度 ≥{EDGE_SATURATION}）映射表：")
    print(f"  {'原色':>18}  {'→ 新色':>18}  {'像素':>5}  亮度比例")
    base_lum = luminance(BUBBLE_TEX_BASE)
    for (old, new), count in sorted(remap.items(), key=lambda kv: -kv[1]):
        print(
            f"  {str(old):>18}  {str(new):>18}  {count:5d}  "
            f"{luminance(old) / base_lum:.3f}"
        )
    print(f"\n填充像素逐像素保留：{sum(kept.values())} px / {len(kept)} 色")
    for color, count in kept.most_common():
        print(f"  {str(color):>18}  ×{count}")

    # ── 自检 ────────────────────────────────────────────────────────────────
    src_px, out_px = source.load(), result.load()
    changed = 0
    for y in range(source.height):
        for x in range(source.width):
            if src_px[x, y] != out_px[x, y]:
                changed += 1
                assert is_edge(src_px[x, y][:3]), f"填充像素被改动: {src_px[x, y]}"
    assert changed == sum(remap.values()), (changed, sum(remap.values()))
    for (old, new) in remap:
        scale = luminance(old) / base_lum
        for channel, base in zip(new, BUBBLE_TEX_BASE):
            assert abs(channel - round(base * scale)) <= 1, (old, new)
    print(f"\n自检通过：改动 {changed} px，全部是描边；填充与透明像素零改动。")

    # 着色自检：任取一个 tint，验证描边 / 填充的比例一致
    for tint in ((105, 43, 84), (226, 239, 246), (49, 119, 49)):
        print(f"\n  tint {tint} 下的最终色（描边 → 填充）：")
        for (old, new), _ in sorted(remap.items(), key=lambda kv: luminance(kv[0][0])):
            print(f"    改前 {str(tinted(old, tint)):>16}   改后 {str(tinted(new, tint)):>16}")
        print(f"    填充 {str(tinted(BUBBLE_TEX_BASE, tint)):>16}（两侧同值，未改动）")

    # ── 输出 ────────────────────────────────────────────────────────────────
    raw = png_bytes(result)
    b64 = base64.b64encode(raw).decode("ascii")
    TARGET.write_text(_module_source(b64, raw, remap, kept), encoding="utf-8", newline="\n")
    print(f"\n写出 {TARGET.relative_to(ROOT)}  ({TARGET.stat().st_size} B)")

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for tag, image in (("before", source), ("after", result)):
        path = PREVIEW_DIR / f"bubble-border-menutiles-{tag}-8x.png"
        image.resize((image.width * 8, image.height * 8), Image.NEAREST).save(path)
        print(f"核对图（8x）: {path.relative_to(ROOT)}")


def _module_source(
    b64: str, raw: bytes, remap: Counter, kept: Counter
) -> str:
    edges = ", ".join(
        f"{old}→{new}"
        for (old, new), _ in sorted(remap.items(), key=lambda kv: -kv[1])[:4]
    )
    return f'''"""气泡专用的 MenuTiles 九宫格变体（自动生成，勿手改）。

气泡底是 `IClickableMenu.drawTextureBox(Maps\\MenuTiles (0,256,60,60), tint)` 画出来的，
最终色 = 纹理色 × tint ÷ 255。这块贴图**自带的描边是红橙色**（(177,78,5)，饱和度 0.97、
B 通道只有 5）：白 tint 下面板/按钮是木框本色，没问题；可角色气泡的 tint 是紫红/靛蓝
这类深色，描边的 B 通道乘完仍是 5×84÷255 ≈ 2 —— 「紫红底色」旁边就围了一圈**橙红**的边。

本文件把**描边像素的色相归一到填充基准色**（{BUBBLE_TEX_BASE} = #fdbc6e），
逐像素保留相对亮度：

    新描边 = base × (亮度(p) ÷ 亮度(base))

于是对任意 tint 都有「描边最终色 = 填充最终色 × 同一比例」，边框就是底色的暗版本，
四档明暗与圆角形状一个像素不动，木框质感与纹理全部保留。

* 描边映射：{edges}
* 填充 {sum(kept.values())} px（{len(kept)} 色）**逐像素原样保留**，纹理色差不受影响；
* 只改这一块 60×60 裁剪 —— 面板 / 按钮 / 凹槽共用的那份贴图原封不动；
* 与 `scripts/export_npc_bubble_assets.py::BUBBLE_TEX_BASE` 同源，改一处必须同步另一处。

生成脚本：scripts/build_bubble_texture.py（只读游戏解包目录，幂等）
源 {SOURCE.name} → 60x60，png {len(raw)}B
"""

from __future__ import annotations

# Maps\\MenuTiles.xnb (0,256,60,60)；按 MENU_TEX 的切法使用（slice = 20）。
BUBBLE_MENU_TEX_DATA_URI = (
    "data:image/png;base64,{b64}"
)
'''


if __name__ == "__main__":
    main()
