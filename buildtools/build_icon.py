from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        renderer.render(painter, QRectF(0, 0, size, size))
    finally:
        painter.end()

    encoded = QByteArray()
    buffer = QBuffer(encoded)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError(f"Could not open the {size}x{size} icon buffer.")
    if not image.save(buffer, "PNG"):
        raise RuntimeError(f"Could not encode the {size}x{size} icon image.")
    buffer.close()
    return bytes(encoded)


def compile_ico(source: Path, output: Path):
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG icon: {source}")

    images = [(size, render_png(renderer, size)) for size in ICON_SIZES]
    header_size = 6 + 16 * len(images)
    offset = header_size
    entries = []
    payloads = []
    for size, payload in images:
        encoded_size = 0 if size == 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                encoded_size,
                encoded_size,
                0,
                0,
                1,
                32,
                len(payload),
                offset,
            )
        )
        payloads.append(payload)
        offset += len(payload)

    output.write_bytes(
        struct.pack("<HHH", 0, 1, len(images))
        + b"".join(entries)
        + b"".join(payloads)
    )
    print(f"Built {output} from {source} ({len(images)} sizes)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile ClipTrim's SVG into a multi-resolution ICO.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    compile_ico(args.source.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
