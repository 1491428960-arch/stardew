"""导出 astra 装饰边框的可复用素材。

装饰边框（`characterFrameSvg`）是按气泡实际尺寸过程式生成的，不能用九宫格切图，
所以要把它的**基本零件**导出成图集，再由 C# 复刻同一套布局算法：

  每个角色 3 格：细节造型（detail，按该角色配色）+ 2 个 32×32 大物件

产出：smapi/assets/npc_bubble_frames.png（3 列 × N 行，每格 32×32，透明底）
以及 smapi/NpcBubbleFrameData.cs（kind / 配色 / 图集索引）。

数据源与绘制算法都从 bridge 侧读，不复制定义。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(r"E:\workspace\projects\stardew-ai-npc.worktrees\story-memory")
sys.path.insert(0, str(ROOT / "bridge" / "src"))

from stardew_ai_bridge.npc_bubble_elements import NPC_BUBBLE_ELEMENTS  # noqa: E402

CELL = 32
PAGE_SRC = ROOT / "bridge" / "src" / "stardew_ai_bridge" / "group_dialogue_review_page.py"
OUT_PNG = ROOT / "smapi" / "assets" / "npc_bubble_frames.png"


def extract_frame_script() -> str:
    """从回放页源码里取出 characterFrameSvg 的定义（唯一副本在那边）。"""
    source = PAGE_SRC.read_text(encoding="utf-8")
    match = re.search(
        r"_CHARACTER_FRAME_SCRIPT = r'''(.*?)'''", source, flags=re.DOTALL
    )
    if not match:
        raise SystemExit("没能从回放页里提取 _CHARACTER_FRAME_SCRIPT")
    return match.group(1)


def build_html(frame_js: str, ornaments: dict[str, dict]) -> str:
    return (
        '<!doctype html><meta charset="utf-8"><style>'
        "*{margin:0;padding:0;box-sizing:border-box}"
        "html,body{background:transparent}"
        f"#sheet{{display:grid;grid-template-columns:repeat(3,{CELL}px);"
        f"width:{CELL * 3}px}}"
        f".cell{{width:{CELL}px;height:{CELL}px}}"
        "svg{display:block;image-rendering:pixelated}"
        "</style><div id=\"sheet\"></div>"
        "<script>"
        + frame_js
        + """
const ORNAMENTS = """
        + json.dumps(ornaments, ensure_ascii=False)
        + """;
const sheet = document.getElementById('sheet');
for (const npc of Object.keys(ORNAMENTS)) {
  const orn = ORNAMENTS[npc];
  const svgText = characterFrameSvg(320, 100, orn);
  const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
  const detail = doc.querySelector('[data-ink="detail"]');
  const objects = [...doc.querySelectorAll('[data-ink="object"]')];
  const cells = [detail, objects[0] || null, objects[1] || null];
  for (const node of cells) {
    const cell = document.createElement('div');
    cell.className = 'cell';
    if (node) {
      const clone = node.cloneNode(true);
      // 去掉边框上的定位 transform，让零件回到自身坐标系原点。
      clone.setAttribute('transform', '');
      cell.innerHTML = '<svg viewBox="0 0 32 32" width="32" height="32">'
        + clone.outerHTML + '</svg>';
    }
    sheet.append(cell);
  }
}
</script>"""
    )


def main() -> None:
    frame_js = extract_frame_script()
    ornaments = {
        npc: {
            "kind": element["ornament"]["kind"],
            "colors": element["ornament"]["colors"],
            "objects": list(element["ornament"]["objects"]),
        }
        for npc, element in NPC_BUBBLE_ELEMENTS.items()
    }

    from playwright.sync_api import sync_playwright

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": CELL * 3, "height": CELL * len(ornaments)},
            device_scale_factor=1,
        )
        page.set_content(build_html(frame_js, ornaments))
        page.locator("#sheet").screenshot(path=str(OUT_PNG), omit_background=True)
        browser.close()

    kinds = sorted({item["kind"] for item in ornaments.values()})
    print(f"素材表已写出: {OUT_PNG}")
    print(f"  角色 {len(ornaments)} 行 × 3 格（detail + 2 objects），每格 {CELL}px")
    print(f"  覆盖 kind {len(kinds)} 种: {', '.join(kinds)}")


if __name__ == "__main__":
    main()
