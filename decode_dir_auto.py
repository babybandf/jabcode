#!/usr/bin/env python3
"""
不依赖 manifest.json，自动扫描 encode_dir_to_jab.py 的输出目录并还原所有源码文件。

参数：
    --input     编码输出根目录
    --output    还原输出根目录（默认 ./jab_decode_dir）
    --reader    jabcodeReader 路径（可选）
"""

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="自动扫描并还原 JAB Code 批量编码目录"
    )
    parser.add_argument("--input", required=True, help="编码输出根目录")
    parser.add_argument("--output", default="jab_decode_dir", help="还原输出根目录")
    parser.add_argument("--reader", type=Path, help="jabcodeReader 路径（可选）")
    args = parser.parse_args()

    in_root = Path(args.input)
    if not in_root.is_dir():
        print(f"错误：输入目录不存在：{in_root}", file=sys.stderr)
        return 1

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)

    script_dir = Path(__file__).resolve().parent
    decode_script = script_dir / "decode_from_jab.py"
    if not decode_script.is_file():
        print(f"错误：找不到 {decode_script}", file=sys.stderr)
        return 1

    # 所有包含 .png 的目录即一个源码文件的编码目录
    png_files = in_root.rglob("*.png")
    encoded_dirs = sorted({p.parent for p in png_files})
    if not encoded_dirs:
        print(f"错误：未找到 PNG 图片：{in_root}", file=sys.stderr)
        return 1

    success = 0
    failed = 0

    for enc_dir in encoded_dirs:
        rel = enc_dir.relative_to(in_root)
        # 保持原相对目录层级；文件名会在解码时从全局头中恢复
        final_parent = out_root / rel.parent
        final_parent.mkdir(parents=True, exist_ok=True)

        print(f"\n还原：{enc_dir} -> {final_parent}/<原始文件名>")
        cmd = [
            sys.executable,
            str(decode_script),
            "--input",
            str(enc_dir.resolve()),
        ]
        if args.reader:
            cmd.extend(["--reader", str(args.reader)])

        # 在目标目录下运行，decode_from_jab.py 会用全局头里的原始文件名输出
        result = subprocess.run(cmd, cwd=final_parent)
        if result.returncode == 0:
            success += 1
        else:
            failed += 1
            print(f"  失败：{rel}", file=sys.stderr)

    print(
        f"\n完成：成功 {success} 个，失败 {failed} 个，还原根目录：{out_root.resolve()}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
