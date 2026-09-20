"""贴图 PNG 的零依赖解码 / 编码 —— 只用标准库，Bridge 不再需要 Pillow。

**为什么手写**：Bridge 的运行环境（``E:\\workspace\\venvs\\stardew-story-memory-py312``）里
没有 Pillow，而且那个 venv 连 pip 都没有 —— 「给运行环境加依赖」这条路是封死的。
2026-09-21 的事故正是这么来的：``bubble_color_page`` 在**模块顶层** ``from PIL import Image``，
``app.py`` 又顶层 import 它 → ``import stardew_ai_bridge.app`` 直接失败 → **Bridge 一重启就挂**。

而页面真正需要的只有两件事，都落在标准库的能力范围内（``zlib`` 负责 deflate，其余是字节算术）：

* 把内联的 base64 贴图解成 RGBA 像素 —— 源贴图是 8-bit RGBA、非交错，行 filter 用到 1 / 2 / 4；
* 把 tint **逐通道乘**进像素（``最终色 = 纹理色 × tint ÷ 255``）后再编回 PNG —— 页面自身零滤镜，
  见 ``bubble_color_page`` 的说明。

于是本模块只 import ``base64`` / ``struct`` / ``zlib``：**没有第三方依赖**，
``import stardew_ai_bridge.app`` 也就不可能再因为一块贴图而失败。

**支持范围**（够用即止，范围外一律抛 ``ValueError``，不猜也不静默降级）：

* 解码：8-bit、非交错、无压缩方法变体；颜色类型 6 / 2 / 4 / 0 / 3
  （RGBA / RGB / 灰度+alpha / 灰度 / 调色板，调色板的 ``tRNS`` 一并读取）；
  五种行 filter（None / Sub / Up / Average / Paeth）全部实现。
* 编码：固定写 8-bit RGBA + 行 filter 全 0。

**编码为什么不做 filter 启发式**：本模块的图都是几十像素的九宫格贴图，deflate 对纯色区已经压得很干净，
实测输出与 Pillow ``optimize=True`` 在同一量级；换来的是一条没有分支的 O(n) 编码路径
（页面首次打开要连做近百次预乘 + 编码，稳定比省几十字节重要）。

生成侧（``scripts/build_bubble_texture.py``、``.tmp/ui-preview/*``）仍然用 Pillow —— 那是**离线脚本**，
跑在开发者机器上，与 Bridge 的运行时依赖无关；本模块只负责「运行时不能再有这种依赖」这一段。
"""

from __future__ import annotations

import base64
import struct
import zlib

#: PNG 文件签名，解码第一步就要对上。
_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: 颜色类型 → 每像素通道数（仅 8-bit；调色板按 1 个索引算）。
_CHANNELS: dict[int, int] = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}

#: 解码结果缓存：同一块贴图会被不同 tint 反复预乘，解一次就够（页面里只有两三块贴图）。
_decode_cache: dict[str, tuple[int, int, bytes]] = {}


def decode_data_uri(data_uri: str) -> tuple[int, int, bytearray]:
    """``data:image/png;base64,…`` → ``(宽, 高, RGBA 像素)``。

    像素是 RGBA 顺序、逐行紧密排列的 ``bytearray``，并且是缓存内容的**副本** —— 调用方
    可以放心原地改写（:func:`tint_data_uri` 正是这么用的），不会污染下一次解码。
    """

    cached = _decode_cache.get(data_uri)
    if cached is None:
        cached = _decode_png(_payload_of(data_uri))
        _decode_cache[data_uri] = cached

    width, height, pixels = cached
    return width, height, bytearray(pixels)


def encode_data_uri(width: int, height: int, pixels: bytes | bytearray) -> str:
    """``(宽, 高, RGBA 像素)`` → ``data:image/png;base64,…``（8-bit RGBA、非交错）。"""

    if len(pixels) != width * height * 4:
        raise ValueError(
            f"像素字节数 {len(pixels)} 与 {width}×{height}×4 不符（只接受 RGBA）"
        )
    return "data:image/png;base64," + base64.b64encode(
        _encode_png(width, height, pixels)
    ).decode("ascii")


def tint_data_uri(data_uri: str, tint: tuple[int, int, int]) -> str:
    """把 tint **预乘**进贴图像素，返回新的 data URI。

    逐通道 ``通道 × tint ÷ 255``（四舍五入），与游戏 ``drawTextureBox`` 的乘法着色同一条公式。
    alpha 原样保留 —— 游戏里 tint 的 alpha 是 255，逐通道乘法不动 alpha；
    ``alpha == 0`` 的像素直接跳过（与 Pillow 时代那份实现逐像素等价，见 ``bubble_color_page._bake``）。
    """

    width, height, pixels = decode_data_uri(data_uri)
    red, green, blue = tint
    for index in range(0, len(pixels), 4):
        if pixels[index + 3] == 0:
            continue
        pixels[index] = round(pixels[index] * red / 255)
        pixels[index + 1] = round(pixels[index + 1] * green / 255)
        pixels[index + 2] = round(pixels[index + 2] * blue / 255)

    return encode_data_uri(width, height, pixels)


def _payload_of(data_uri: str) -> bytes:
    header, separator, payload = data_uri.partition(",")
    if not separator or "base64" not in header:
        raise ValueError("只支持 base64 编码的 PNG data URI")

    return base64.b64decode(payload)


def _decode_png(raw: bytes) -> tuple[int, int, bytes]:
    if not raw.startswith(_SIGNATURE):
        raise ValueError("不是 PNG 数据（签名不符）")

    header: tuple[int, int, int, int, int, int, int] | None = None
    palette = b""
    transparency = b""
    compressed = bytearray()
    position = len(_SIGNATURE)
    while position + 8 <= len(raw):
        length = struct.unpack(">I", raw[position:position + 4])[0]
        chunk_type = raw[position + 4:position + 8]
        payload = raw[position + 8:position + 8 + length]
        if len(payload) != length:
            raise ValueError("PNG 数据在块中途被截断")
        if chunk_type == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif chunk_type == b"PLTE":
            palette = payload
        elif chunk_type == b"tRNS":
            transparency = payload
        elif chunk_type == b"IDAT":
            compressed += payload
        elif chunk_type == b"IEND":
            break
        position += length + 12

    if header is None:
        raise ValueError("PNG 缺少 IHDR")
    width, height, depth, color_type, compression, filter_method, interlace = header
    if depth != 8 or interlace != 0 or compression != 0 or filter_method != 0:
        raise ValueError(
            f"只支持 8-bit 非交错 PNG（本图 depth={depth} interlace={interlace}）"
        )
    if color_type not in _CHANNELS:
        raise ValueError(f"不支持的颜色类型 {color_type}")

    channels = _CHANNELS[color_type]
    rows = _unfilter(zlib.decompress(bytes(compressed)), width, height, channels)
    return width, height, _rows_to_rgba(
        rows, width, height, color_type, channels, palette, transparency
    )


def _unfilter(data: bytes, width: int, height: int, channels: int) -> bytearray:
    """把 PNG 的行 filter 还原成原始像素（五种 filter 都要实现：源贴图用了 1 / 2 / 4）。"""

    stride = width * channels
    expected = height * (stride + 1)
    if len(data) != expected:
        raise ValueError(f"像素数据长度 {len(data)} 与 {width}×{height} 的预期 {expected} 不符")

    out = bytearray(height * stride)
    previous = bytearray(stride)
    for row in range(height):
        filter_type = data[row * (stride + 1)]
        start = row * (stride + 1) + 1
        line = bytearray(data[start:start + stride])

        if filter_type == 0:  # None
            pass
        elif filter_type == 1:  # Sub：加左邻
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_type == 2:  # Up：加上邻
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_type == 3:  # Average：加左邻与上邻的均值
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif filter_type == 4:  # Paeth
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                up = previous[index]
                up_left = previous[index - channels] if index >= channels else 0
                estimate = left + up - up_left
                distance_left = abs(estimate - left)
                distance_up = abs(estimate - up)
                distance_up_left = abs(estimate - up_left)
                if distance_left <= distance_up and distance_left <= distance_up_left:
                    predictor = left
                elif distance_up <= distance_up_left:
                    predictor = up
                else:
                    predictor = up_left
                line[index] = (line[index] + predictor) & 0xFF
        else:
            raise ValueError(f"未知的 PNG 行 filter {filter_type}")

        out[row * stride:(row + 1) * stride] = line
        previous = line

    return out


def _rows_to_rgba(
    rows: bytearray,
    width: int,
    height: int,
    color_type: int,
    channels: int,
    palette: bytes,
    transparency: bytes,
) -> bytes:
    """把解码后的原始通道铺成 RGBA（RGBA 源图直接返回，省一次整图拷贝）。"""

    if color_type == 6:
        return bytes(rows)

    out = bytearray(width * height * 4)
    for pixel in range(width * height):
        if color_type == 2:
            red, green, blue = rows[pixel * 3], rows[pixel * 3 + 1], rows[pixel * 3 + 2]
            alpha = 255
        elif color_type == 0:
            red = green = blue = rows[pixel]
            alpha = 255
        elif color_type == 4:
            red = green = blue = rows[pixel * 2]
            alpha = rows[pixel * 2 + 1]
        else:  # 3 = 调色板索引
            index = rows[pixel]
            offset = index * 3
            if offset + 3 > len(palette):
                raise ValueError(f"调色板索引 {index} 越界（PLTE 只有 {len(palette) // 3} 项）")
            red, green, blue = palette[offset], palette[offset + 1], palette[offset + 2]
            alpha = transparency[index] if index < len(transparency) else 255
        out[pixel * 4:pixel * 4 + 4] = bytes((red, green, blue, alpha))

    return bytes(out)


def _encode_png(width: int, height: int, pixels: bytes | bytearray) -> bytes:
    stride = width * 4
    raw = bytearray()
    for row in range(height):
        raw.append(0)  # 行 filter：None
        raw += pixels[row * stride:(row + 1) * stride]

    return b"".join(
        (
            _SIGNATURE,
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            _chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
            _chunk(b"IEND", b""),
        )
    )


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )
