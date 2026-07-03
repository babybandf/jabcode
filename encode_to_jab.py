#!/usr/bin/env python3
"""
将任意文件编码为一系列 JAB Code PNG 图片。

参数：
    --input        输入文件路径
    --output       输出目录（默认 ./jab_out）
    --writer       jabcodeWriter 可执行文件路径（默认自动查找）
    --module-size  模块尺寸（默认 16，设为 8 可得到宽高各一半的 PNG）
    --ecc-level    纠错等级（默认 4）
"""

import argparse
import gzip
import hashlib
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import List

from PIL import Image, ImageColor

# 单页参数：24x24 ECC4 模块 16px
COLOR_NUMBER = 8
SYMBOL_VERSION_X = 24
SYMBOL_VERSION_Y = 24
ECC_LEVEL = 4
DEFAULT_MODULE_SIZE = 16

# 协议魔数
PAGE_MAGIC = b"JABP"
GLOBAL_MAGIC = b"JAB0"

# 实测 24x24 各 ECC 等级最大净荷（字节）；留出安全余量后的每页容量
# 余量用于覆盖页眉、模式切换开销和 zlib/gzip 头
MAX_PAYLOAD_BY_ECC = {
    1: 2400,
    2: 2200,
    3: 2000,
    4: 2200,
    5: 1900,
    6: 1450,
    7: 1100,
    8: 800,
    9: 650,
    10: 500,
}


def max_payload_for_ecc(ecc_level: int) -> int:
    ecc_level = max(1, min(10, ecc_level))
    return MAX_PAYLOAD_BY_ECC[ecc_level]


# 每次尝试压缩的原始数据上限，代码压缩率通常 4~6 倍
INITIAL_INPUT_CHUNK = 2200 * 4


def find_default_writer() -> Path:
    """根据脚本所在位置推断 jabcodeWriter 路径。"""
    repo_root = Path(__file__).resolve().parent
    return repo_root / "src" / "jabcodeWriter" / "bin" / "jabcodeWriter"


def build_global_header(filename: str, file_size: int, sha256: bytes) -> bytes:
    """构造第 0 页开头的全局头。"""
    name_bytes = filename.encode("utf-8")
    if len(name_bytes) > 65535:
        raise ValueError("文件名超过 65535 字节")
    return (
        GLOBAL_MAGIC
        + struct.pack("<Q", file_size)
        + sha256
        + struct.pack("<H", len(name_bytes))
        + name_bytes
    )


def compress_in_chunks(data: bytes, max_payload: int) -> List[bytes]:
    """
    将 data 切成多块，每块独立 gzip 压缩后 <= max_payload。
    返回压缩后的块列表。
    """
    chunks: List[bytes] = []
    offset = 0
    n = len(data)

    while offset < n:
        # 先尝试较大一块
        trial_end = min(n, offset + INITIAL_INPUT_CHUNK)
        compressed = gzip.compress(data[offset:trial_end], compresslevel=9)

        # 如果压缩后仍超过限制，二分缩小输入
        if len(compressed) > max_payload:
            lo, hi = offset, trial_end
            best = b""
            while lo + 1 < hi:
                mid = (lo + hi) // 2
                c = gzip.compress(data[offset:mid], compresslevel=9)
                if len(c) <= max_payload:
                    lo = mid
                    best = c
                else:
                    hi = mid
            if not best:
                raise RuntimeError(
                    f"无法将数据装入单页：offset={offset}，最小压缩块也超过 {max_payload} 字节"
                )
            end = lo
            compressed = best
        else:
            end = trial_end

        chunks.append(compressed)
        offset = end

    return chunks


def build_page_packet(index: int, total: int, payload: bytes) -> bytes:
    """构造一页的二进制包。"""
    return (
        PAGE_MAGIC
        + struct.pack("<I", index)
        + struct.pack("<I", total)
        + struct.pack("<H", len(payload))
        + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF)
        + payload
    )


def encode_page(bin_path: Path, png_path: Path, writer: Path, module_size: int, ecc_level: int) -> None:
    """调用 jabcodeWriter 把 .bin 编码为 .png。"""
    cmd = [
        str(writer),
        "--input-file",
        str(bin_path),
        "--output",
        str(png_path),
        "--color-number",
        str(COLOR_NUMBER),
        "--ecc-level",
        str(ecc_level),
        "--symbol-version",
        str(SYMBOL_VERSION_X),
        str(SYMBOL_VERSION_Y),
        "--module-size",
        str(module_size),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"jabcodeWriter 失败：{result.stderr or result.stdout}\n命令：{' '.join(cmd)}"
        )


def add_border(png_path: Path, border: int, color: str) -> None:
    """在生成的 JAB Code PNG 四周加上纯色边框。"""
    img = Image.open(png_path).convert("RGB")
    bg_color = ImageColor.getrgb(color)
    bg = Image.new("RGB", (img.width + 2 * border, img.height + 2 * border), bg_color)
    bg.paste(img, (border, border))
    bg.save(png_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="将文件编码为 JAB Code 图片序列")
    parser.add_argument("--input", required=True, help="输入文件路径")
    parser.add_argument("--output", default="jab_out", help="输出目录")
    parser.add_argument("--writer", type=Path, help="jabcodeWriter 路径")
    parser.add_argument(
        "--module-size",
        type=int,
        default=DEFAULT_MODULE_SIZE,
        help="模块尺寸（默认 16，设为 8 可得到宽高各一半的 PNG）",
    )
    parser.add_argument(
        "--ecc-level",
        type=int,
        default=ECC_LEVEL,
        help="纠错等级（默认 4，范围 1-10，越高越抗错但容量越小）",
    )
    parser.add_argument(
        "--border",
        type=int,
        default=0,
        help="在 PNG 四周添加的边框宽度（像素，默认 0）",
    )
    parser.add_argument(
        "--border-color",
        default="white",
        help="边框颜色（默认 white，支持颜色名或 #RRGGBB）",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"错误：输入文件不存在：{input_path}", file=sys.stderr)
        return 1

    writer = args.writer or find_default_writer()
    if not writer.is_file():
        print(
            f"错误：找不到 jabcodeWriter：{writer}\n"
            "请先在 src/jabcodeWriter 目录执行 make，并用 -no-pie 链接。",
            file=sys.stderr,
        )
        return 1

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 读取原始文件并计算哈希
    raw = input_path.read_bytes()
    sha256 = hashlib.sha256(raw).digest()
    filename = input_path.name

    # 构造待压缩流：全局头 + 原始数据
    stream = build_global_header(filename, len(raw), sha256) + raw

    # 分块压缩
    max_payload = max_payload_for_ecc(args.ecc_level)
    compressed_chunks = compress_in_chunks(stream, max_payload)
    total_pages = len(compressed_chunks)
    print(
        f"输入：{len(raw)} 字节，压缩后分 {total_pages} 页，"
        f"ECC{args.ecc_level}，模块尺寸 {args.module_size}px"
    )

    # 生成每页
    for idx, payload in enumerate(compressed_chunks):
        packet = build_page_packet(idx, total_pages, payload)
        bin_path = out_dir / f"page_{idx:03d}.bin"
        png_path = out_dir / f"page_{idx:03d}.png"
        bin_path.write_bytes(packet)
        encode_page(bin_path, png_path, writer, args.module_size, args.ecc_level)
        if args.border > 0:
            add_border(png_path, args.border, args.border_color)
        print(f"  已生成 {png_path.name}（包大小 {len(packet)} 字节）")

    print(f"全部完成，输出目录：{out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
