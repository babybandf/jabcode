#!/usr/bin/env python3
"""
批量遍历 encode_dir_to_jab.py 生成的输出目录，还原所有源码文件。

参数：
    --input     编码输出根目录（包含 manifest.json 和各子目录）
    --output    还原输出根目录（默认 ./jab_decode_dir）
    --reader    jabcodeReader 路径（可选）
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="批量还原 JAB Code 图片序列为源码文件")
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

    manifest_path = in_root / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        print(f"错误：找不到清单文件 {manifest_path}", file=sys.stderr)
        return 1

    success = 0
    failed = 0

    for entry in manifest:
        original = Path(entry["original"])
        encoded_dir = in_root / entry["encoded_dir"]
        out_path = out_root / original
        out_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"\n还原：{encoded_dir} -> {out_path}")
        cmd = [
            sys.executable,
            str(decode_script),
            "--input",
            str(encoded_dir),
            "--output",
            str(out_path),
        ]
        if args.reader:
            cmd.extend(["--reader", str(args.reader)])

        result = subprocess.run(cmd)
        if result.returncode == 0:
            success += 1
        else:
            failed += 1
            print(f"  失败：{original}", file=sys.stderr)

    print(f"\n完成：成功 {success} 个，失败 {failed} 个，还原根目录：{out_root.resolve()}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
