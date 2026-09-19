"""审计群聊气泡的九角色色板：色相分离度、果实与底色对比度、底色可辨性。

用法：
    py -3.10 scripts/audit_npc_bubble_palette.py
    py -3.10 scripts/audit_npc_bubble_palette.py docs/npc-bubble-elements-2026-09-19.json

退出码 0 表示全部达标；1 表示存在需要收口的问题（逐条打印）。
阈值来自 docs/npc-bubble-elements-2026-09-19.md 的敲定口径。
"""

from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from pathlib import Path

BG = (17, 18, 27)  # 回放页 --bg
MIN_HUE_GAP = 20.0      # accent 色相两两最小间距
MIN_BUBBLE_HUE = 30.0   # 气泡底色色相接近时……
MIN_BUBBLE_LUM = 5.0    # ……必须靠亮度拉开
MIN_FRUIT_CONTRAST = 2.8
MIN_NAME_CONTRAST = 4.5
MIN_BUBBLE_CONTRAST = 1.30

DEFAULT_SPEC = Path(__file__).resolve().parents[1] / "docs" / "npc-bubble-elements-2026-09-19.json"


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgba_to_rgb(value: str, base: tuple[int, int, int] = BG) -> tuple[int, int, int]:
    match = re.match(r"rgba?\(([^)]+)\)", value.strip())
    if not match:
        return hex_to_rgb(value)
    parts = [p.strip() for p in match.group(1).split(",")]
    r, g, b = float(parts[0]), float(parts[1]), float(parts[2])
    alpha = float(parts[3]) if len(parts) > 3 else 1.0
    return tuple(round(c * alpha + base_c * (1 - alpha)) for c, base_c in zip((r, g, b), base))


def lum(rgb: tuple[int, int, int]) -> float:
    out = []
    for c in rgb:
        v = c / 255
        out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hue_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", nargs="?", default=str(DEFAULT_SPEC), help="元素规格 JSON")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.is_file():
        print(f"规格文件不存在：{spec_path}", file=sys.stderr)
        return 2
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    order = spec.get("npcOrder") or list(spec["npcs"])
    rows = {}
    for npc in order:
        palette = spec["npcs"][npc]["palette"]
        accent = hex_to_rgb(palette["accent"])
        bubble = rgba_to_rgb(palette["bubble"])
        rows[npc] = {
            "accent": accent,
            "accentHex": palette["accent"],
            "bubble": bubble,
            "bubbleRaw": palette["bubble"],
            "fruit": hex_to_rgb(palette["fruit"]),
            "fruitHex": palette["fruit"],
            "hue": float(palette["hue"]),
            "bubbleHue": colorsys.rgb_to_hls(*[c / 255 for c in bubble])[0] * 360,
            "bubbleLum": colorsys.rgb_to_hls(*[c / 255 for c in bubble])[1] * 100,
        }

    print(f"{'角色':<11}{'accent':<10}{'色相':>6}  {'气泡底':<22}{'果实':<10}{'名字/底':>8}{'果实/底':>8}")
    print("=" * 92)
    for npc in order:
        r = rows[npc]
        print(
            f"{npc:<11}{r['accentHex']:<10}{r['hue']:>6.1f}  rgb{str(r['bubble']):<18}"
            f"{r['fruitHex']:<10}{contrast(r['accent'], r['bubble']):>8.2f}"
            f"{contrast(r['fruit'], r['bubble']):>8.2f}"
        )

    problems: list[str] = []
    names = list(order)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = rows[names[i]], rows[names[j]]
            gap = hue_gap(a["hue"], b["hue"])
            if gap < MIN_HUE_GAP:
                problems.append(f"accent 撞色：{names[i]} × {names[j]} 色相差 {gap:.1f}° < {MIN_HUE_GAP}°")
            bg_gap = hue_gap(a["bubbleHue"], b["bubbleHue"])
            bl = abs(a["bubbleLum"] - b["bubbleLum"])
            if bg_gap < MIN_BUBBLE_HUE and bl < MIN_BUBBLE_LUM:
                problems.append(
                    f"气泡底近似：{names[i]} × {names[j]} 色相差 {bg_gap:.1f}° 亮度差 {bl:.1f} < {MIN_BUBBLE_LUM}"
                )
    for npc in order:
        r = rows[npc]
        if contrast(r["fruit"], r["bubble"]) < MIN_FRUIT_CONTRAST:
            problems.append(f"{npc} 果实/底色对比 {contrast(r['fruit'], r['bubble']):.2f} < {MIN_FRUIT_CONTRAST}")
        if contrast(r["accent"], r["bubble"]) < MIN_NAME_CONTRAST:
            problems.append(f"{npc} 名字色/底色对比 {contrast(r['accent'], r['bubble']):.2f} < {MIN_NAME_CONTRAST}")
        if contrast(r["bubble"], BG) < MIN_BUBBLE_CONTRAST:
            problems.append(f"{npc} 气泡底/页面底对比 {contrast(r['bubble'], BG):.2f} < {MIN_BUBBLE_CONTRAST}")

    print()
    if problems:
        print(f"审计未通过（{len(problems)} 项）：")
        for item in problems:
            print("  ⚠", item)
        return 1
    print("审计通过：色相分离、果实对比、名字对比、底色可辨全部达标 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
