#!/usr/bin/env python3
"""
将任意文件编码为一系列 JAB Code PNG 图片。

参数：
    --input     输入文件路径
    --output    输出目录（默认 ./jab_out）
    --writer    jabcodeWriter 可执行文件路径（默认自动查找）
"""

import argparse
import gzip
import hashlib
import struct
import subprocess
import sys
import zlib
from pathlib import Path

# 单页参数：24x24 ECC4 模块 16px
COLOR_NUMBER = 8
SYMBOL_VERSION_X = 24
SYMBOL_VERSION_Y = 24
ECC_LEVEL = 4
MODULE_SIZE = 16

# 协议魔数
PAGE_MAGIC = b"JABP"
GLOBAL_MAGIC = b"JAB0"

# 实测 24x24 ECC4 最大可塞 2310 字节；留出 110 字节余量
MAX_PAYLOAD = 2200

# 每次尝试压缩的原始数据上限，代码压缩率通常 4~6 倍
INITIAL_INPUT_CHUNK = MAX_PAYLOAD * 4


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


def compress_in_chunks(data: bytes, max_payload: int) -> list[bytes]:
    """
    将 data 切成多块，每块独立 gzip 压缩后 <= max_payload。
    返回压缩后的块列表。
    """
    chunks: list[bytes] = []
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


def encode_page(bin_path: Path, png_path: Path, writer: Path) -> None:
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
        str(ECC_LEVEL),
        "--symbol-version",
        str(SYMBOL_VERSION_X),
        str(SYMBOL_VERSION_Y),
        "--module-size",
        str(MODULE_SIZE),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"jabcodeWriter 失败：{result.stderr or result.stdout}\n命令：{' '.join(cmd)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="将文件编码为 JAB Code 图片序列")
    parser.add_argument("--input", required=True, help="输入文件路径")
    parser.add_argument("--output", default="jab_out", help="输出目录")
    parser.add_argument("--writer", type=Path, help="jabcodeWriter 路径")
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
    compressed_chunks = compress_in_chunks(stream, MAX_PAYLOAD)
    total_pages = len(compressed_chunks)
    print(f"输入：{len(raw)} 字节，压缩后分 {total_pages} 页")

    # 生成每页
    for idx, payload in enumerate(compressed_chunks):
        packet = build_page_packet(idx, total_pages, payload)
        bin_path = out_dir / f"page_{idx:03d}.bin"
        png_path = out_dir / f"page_{idx:03d}.png"
        bin_path.write_bytes(packet)
        encode_page(bin_path, png_path, writer)
        print(f"  已生成 {png_path.name}（包大小 {len(packet)} 字节）")

    print(f"全部完成，输出目录：{out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
