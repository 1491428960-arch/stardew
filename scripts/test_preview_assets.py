import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("preview_assets.py")
SPEC = importlib.util.spec_from_file_location("preview_assets", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def png_header(width: int, height: int, color_type: int = 6) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
        + b"\x00\x00\x00\x00"
    )


def webp_lossless_header(width: int, height: int) -> bytes:
    packed = (width - 1) | ((height - 1) << 14)
    return (
        b"RIFF"
        + b"\x00\x00\x00\x00"
        + b"WEBP"
        + b"VP8L"
        + b"\x04\x00\x00\x00"
        + b"\x2f"
        + packed.to_bytes(4, "little")
    )


class PreviewAssetsTests(unittest.TestCase):
    def test_read_png_info_and_hash(self) -> None:
        payload = png_header(2, 3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "portrait.png"
            path.write_bytes(payload)
            info = MODULE.read_png_info(path)

        self.assertEqual(info["width"], 2)
        self.assertEqual(info["height"], 3)
        self.assertEqual(info["colorType"], 6)
        self.assertEqual(info["sha256"], hashlib.sha256(payload).hexdigest())

    def test_invalid_png_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.png"
            path.write_bytes(b"not-a-png")
            with self.assertRaises(ValueError):
                MODULE.read_png_info(path)

    def test_webp_payload_with_png_extension_is_reported(self) -> None:
        payload = webp_lossless_header(128, 448)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "portrait.png"
            path.write_bytes(payload)
            info = MODULE.read_png_info(path)

        self.assertEqual(info["format"], "webp")
        self.assertEqual(info["width"], 128)
        self.assertEqual(info["height"], 448)

    def test_manifest_is_sorted_and_html_disclaims_runtime_fidelity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "assets"
            root.mkdir()
            (root / "z.png").write_bytes(png_header(4, 5))
            (root / "a.png").write_bytes(png_header(6, 7))
            manifest = MODULE.build_manifest(root)
            html = MODULE.render_contact_sheet(manifest)

        self.assertEqual([item["path"] for item in manifest["files"]], ["a.png", "z.png"])
        self.assertIn("素材快检，不等同于 Stardew Valley 最终渲染", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertEqual(json.loads(json.dumps(manifest))["fileCount"], 2)


if __name__ == "__main__":
    unittest.main()
