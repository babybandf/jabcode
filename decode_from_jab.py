#!/usr/bin/env python3
"""
从 JAB Code PNG 图片序列还原原始文件，并校验 SHA-256。

参数：
    --input      包含 page_*.png 的目录
    --output     还原文件输出路径（默认使用全局头里的文件名）
    --reader     jabcodeReader 可执行文件路径（默认自动查找）
"""

import argparse
import gzip
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter

PAGE_MAGIC = b"JABP"
GLOBAL_MAGIC = b"JAB0"


def find_default_reader() -> Path:
    """根据脚本所在位置推断 jabcodeReader 路径。"""
    repo_root = Path(__file__).resolve().parent
    return repo_root / "src" / "jabcodeReader" / "bin" / "jabcodeReader"


def _try_decode_raw(png_path: Path, reader: Path) -> Optional[bytes]:
    """直接调用 jabcodeReader 解码，成功返回数据，失败返回 None。"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
        out_path = tmp.name
    try:
        cmd = [str(reader), str(png_path), "--output", out_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return None
        return Path(out_path).read_bytes()
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)


def _preprocess_variants(png_path: Path) -> List[Path]:
    """生成几种预处理后的临时 PNG，用于增强截图解码成功率。"""
    img = Image.open(png_path).convert("RGB")
    variants: List[Path] = []
    base = Path(tempfile.gettempdir()) / f"jab_decode_{png_path.stem}"

    # 1. 锐化
    sharp = img.filter(ImageFilter.SHARPEN)
    p = Path(f"{base}_sharp.png")
    sharp.save(p)
    variants.append(p)

    # 2. 2 倍放大 + 锐化
    up = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    up_sharp = up.filter(ImageFilter.SHARPEN)
    p = Path(f"{base}_up2x_sharp.png")
    up_sharp.save(p)
    variants.append(p)

    # 3. 对比度增强
    enhancer = ImageEnhance.Contrast(img)
    contrast = enhancer.enhance(1.5)
    p = Path(f"{base}_contrast.png")
    contrast.save(p)
    variants.append(p)

    return variants


def decode_png(png_path: Path, reader: Path, auto_preprocess: bool = True) -> bytes:
    """调用 jabcodeReader 解码单张 PNG，返回原始二进制包。"""
    data = _try_decode_raw(png_path, reader)
    if data is not None:
        return data

    if not auto_preprocess:
        raise RuntimeError(f"解码失败：{png_path}")

    # 直接失败时，尝试预处理
    variants = _preprocess_variants(png_path)
    try:
        for v in variants:
            data = _try_decode_raw(v, reader)
            if data is not None:
                return data
        raise RuntimeError(f"解码失败：{png_path}（已尝试锐化/放大/对比度增强）")
    finally:
        for v in variants:
            if v.exists():
                v.unlink()


def parse_page_packet(packet: bytes) -> Tuple[int, int, bytes]:
    """
    解析一页二进制包，返回 (index, total, payload)。
    校验 Magic、长度、CRC32。
    """
    if len(packet) < 18:
        raise ValueError(f"页包太短：{len(packet)} 字节")

    magic = packet[:4]
    if magic != PAGE_MAGIC:
        raise ValueError(f"页 Magic 不匹配：{magic!r}")

    index, total, length, crc = struct.unpack("<IIHI", packet[4:18])
    payload = packet[18:]
    if len(payload) != length:
        raise ValueError(
            f"页长度不匹配：声明 {length} 字节，实际 {len(payload)} 字节"
        )

    expected_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if crc != expected_crc:
        raise ValueError(f"CRC32 不匹配：页 {index}")

    return index, total, payload


def parse_global_header(data: bytes) -> Tuple[str, int, bytes, bytes]:
    """
    解析全局头，返回 (filename, original_size, sha256, remaining_data)。
    """
    if len(data) < 4 + 8 + 32 + 2:
        raise ValueError("数据不足以包含全局头")

    if data[:4] != GLOBAL_MAGIC:
        raise ValueError(f"全局头 Magic 不匹配：{data[:4]!r}")

    pos = 4
    original_size = struct.unpack("<Q", data[pos : pos + 8])[0]
    pos += 8
    sha256 = data[pos : pos + 32]
    pos += 32
    name_len = struct.unpack("<H", data[pos : pos + 2])[0]
    pos += 2
    if len(data) < pos + name_len:
        raise ValueError("全局头文件名长度超出数据范围")
    filename = data[pos : pos + name_len].decode("utf-8")
    pos += name_len
    return filename, original_size, sha256, data[pos:]


def main() -> int:
    parser = argparse.ArgumentParser(description="从 JAB Code 图片序列还原文件")
    parser.add_argument("--input", required=True, help="包含 PNG 的目录")
    parser.add_argument("--output", help="输出文件路径（默认使用全局头中的文件名）")
    parser.add_argument("--reader", type=Path, help="jabcodeReader 路径")
    parser.add_argument(
        "--no-preprocess",
        action="store_true",
        help="关闭截图自动预处理（默认开启）",
    )
    args = parser.parse_args()

    in_dir = Path(args.input)
    if not in_dir.is_dir():
        print(f"错误：输入目录不存在：{in_dir}", file=sys.stderr)
        return 1

    reader = args.reader or find_default_reader()
    if not reader.is_file():
        print(
            f"错误：找不到 jabcodeReader：{reader}\n"
            "请先在 src/jabcodeReader 目录执行 make，并用 -no-pie 链接。",
            file=sys.stderr,
        )
        return 1

    png_files = sorted(
        p
        for p in in_dir.glob("*.png")
        if not any(s in p.stem for s in ("_sharp", "_up2x", "_contrast"))
    )
    if not png_files:
        print(f"错误：目录中没有 PNG 图片：{in_dir}", file=sys.stderr)
        return 1

    print(f"发现 {len(png_files)} 张图片，开始解码...")

    pages: List[Tuple[int, int, bytes]] = []
    for png in png_files:
        packet = decode_png(png, reader, auto_preprocess=not args.no_preprocess)
        index, total, payload = parse_page_packet(packet)
        pages.append((index, total, payload))
        print(f"  {png.name} -> 页 {index + 1}/{total}")

    pages.sort(key=lambda x: x[0])
    indices = [p[0] for p in pages]
    totals = {p[1] for p in pages}
    if len(totals) != 1:
        raise ValueError(f"页总数不一致：{totals}")
    total = totals.pop()
    if indices != list(range(total)):
        missing = set(range(total)) - set(indices)
        raise ValueError(f"缺页：{sorted(missing)}")

    # 逐个解压并拼接
    decompressed = bytearray()
    for idx, _, payload in pages:
        try:
            chunk = gzip.decompress(payload)
        except Exception as e:
            raise RuntimeError(f"第 {idx} 页 gzip 解压失败：{e}")
        decompressed.extend(chunk)

    # 解析全局头
    filename, original_size, expected_sha, source = parse_global_header(
        bytes(decompressed)
    )

    if len(source) != original_size:
        raise ValueError(
            f"还原大小不匹配：声明 {original_size}，实际 {len(source)}"
        )

    # 校验 SHA-256
    actual_sha = hashlib.sha256(source).digest()
    if actual_sha != expected_sha:
        raise ValueError(
            "SHA-256 校验失败！\n"
            f"预期：{expected_sha.hex()}\n"
            f"实际：{actual_sha.hex()}"
        )

    # 输出
    out_path = Path(args.output) if args.output else Path(filename)
    out_path.write_bytes(source)
    print(f"还原成功：{out_path.resolve()}")
    print(f"SHA-256：{actual_sha.hex()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
