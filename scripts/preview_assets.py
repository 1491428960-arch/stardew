"""生成 PNG 素材的离线尺寸/哈希清单和可点击 contact sheet。

该工具只做 PNG 文件级快检，不加载 Stardew 的 XNB、Content Patcher 条件或
MonoGame SpriteBatch，因此输出不能替代真实游戏引擎截图。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_png_info(path: Path) -> dict[str, Any]:
    path = Path(path)
    payload = path.read_bytes()
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        if payload[12:16] != b"VP8L" or len(payload) < 25 or payload[20] != 0x2F:
            raise ValueError(f"暂不支持的 WebP 编码：{path}")
        packed = int.from_bytes(payload[21:25], "little")
        return {
            "format": "webp",
            "width": (packed & 0x3FFF) + 1,
            "height": ((packed >> 14) & 0x3FFF) + 1,
            "bitDepth": None,
            "colorType": None,
            "compression": None,
            "filtering": None,
            "interlace": None,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    header = payload[:33]
    if len(header) < 33 or header[:8] != PNG_SIGNATURE:
        raise ValueError(f"不是有效 PNG 或 WebP：{path}")
    chunk_length = struct.unpack(">I", header[8:12])[0]
    if header[12:16] != b"IHDR" or chunk_length != 13:
        raise ValueError(f"PNG 缺少标准 IHDR：{path}")
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", header[16:29]
    )
    if width <= 0 or height <= 0:
        raise ValueError(f"PNG 尺寸无效：{path}")
    return {
        "format": "png",
        "width": width,
        "height": height,
        "bitDepth": bit_depth,
        "colorType": color_type,
        "compression": compression,
        "filtering": filtering,
        "interlace": interlace,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build_manifest(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"素材目录不存在：{root}")

    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.png"), key=lambda item: item.relative_to(root).as_posix().lower()):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        info = read_png_info(path)
        files.append({"path": relative, **info})

    return {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "fileCount": len(files),
        "files": files,
    }


def render_contact_sheet(manifest: dict[str, Any]) -> str:
    root = Path(str(manifest["root"]))
    cards: list[str] = []
    for item in manifest["files"]:
        relative = str(item["path"])
        source = root / Path(relative)
        encoded = base64.b64encode(source.read_bytes()).decode("ascii")
        label = html.escape(relative)
        cards.append(
            "<article class=\"card\">"
            f"<img loading=\"lazy\" src=\"data:image/{item['format']};base64,{encoded}\" alt=\"{label}\">"
            f"<code>{label}</code>"
            f"<span>{item['width']}×{item['height']} · {item['format']} · type {item['colorType']} · {item['sha256'][:12]}</span>"
            "</article>"
        )

    title = html.escape(str(manifest.get("root", "PNG 素材")))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stardew PNG 素材快检</title>
<style>
body {{ margin: 0; padding: 24px; color: #2c211b; background: #f6efe3; font: 15px/1.5 system-ui, sans-serif; }}
h1 {{ margin-top: 0; }}
.notice {{ padding: 12px 16px; border: 2px solid #b87836; border-radius: 8px; background: #fff4d5; }}
.root {{ color: #6f625a; word-break: break-all; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-top: 20px; }}
.card {{ display: flex; min-height: 220px; padding: 12px; flex-direction: column; gap: 6px; border: 2px solid #c58b4a; border-radius: 10px; background: #fffaf0; box-shadow: 2px 2px 0 #b87836; }}
.card img {{ width: 100%; height: 150px; object-fit: contain; image-rendering: pixelated; background: repeating-conic-gradient(#eee 0 25%, #fff 0 50%) 50% / 16px 16px; }}
.card code {{ overflow-wrap: anywhere; }}
.card span {{ color: #6f625a; font-size: 12px; }}
</style>
</head>
<body>
<h1>Stardew PNG 素材快检</h1>
<p class="notice"><strong>素材快检，不等同于 Stardew Valley 最终渲染。</strong><br>
这里没有执行 Content Patcher 条件、XNB 加载、SpriteBatch 缩放、语言包或游戏 UI 合成；最终外观以真实引擎截图为准。</p>
<p class="root">源目录：{title} · 文件数：{manifest['fileCount']}</p>
<section class="grid">{''.join(cards)}</section>
</body>
</html>
"""


def write_preview(input_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"输出目录非空，为避免误读旧结果请换目录：{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(Path(input_dir))
    manifest_path = output_dir / "manifest.json"
    html_path = output_dir / "contact-sheet.html"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_contact_sheet(manifest), encoding="utf-8")
    return manifest_path, html_path


def main() -> int:
    parser = argparse.ArgumentParser(description="PNG 素材离线快检与 contact sheet")
    parser.add_argument("--input", required=True, type=Path, help="素材根目录")
    parser.add_argument("--output", required=True, type=Path, help="新输出目录")
    args = parser.parse_args()
    try:
        manifest_path, html_path = write_preview(args.input, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"MANIFEST: {manifest_path}")
    print(f"CONTACT_SHEET: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
