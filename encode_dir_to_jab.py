#!/usr/bin/env python3
"""
批量遍历目录，把主流源码文件分别编码为独立的 JAB Code 图片目录。

默认支持的扩展名：.c .h .cc .cpp .cxx .c++ .asm .s .py .js .ts .java
.go .rs .swift .kt .m .mm .cs .php .rb .sh .bat

参数：
    --input     源码根目录
    --output    输出根目录（默认 ./jab_out_dir）
    --writer    jabcodeWriter 路径（可选）
    --ext       额外扩展名列表，用逗号分隔（可选）
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_EXTS = {
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".c++",
    ".asm",
    ".s",
    ".py",
    ".js",
    ".ts",
    ".java",
    ".go",
    ".rs",
    ".swift",
    ".kt",
    ".m",
    ".mm",
    ".cs",
    ".php",
    ".rb",
    ".sh",
    ".bat",
}


def safe_name(filename: str) -> str:
    """把文件名中的 '.' 替换为 '_'，用于目录名，例如 decoder.c -> decoder_c。"""
    return filename.replace(".", "_")


def main() -> int:
    parser = argparse.ArgumentParser(description="批量编码目录中的源码文件为 JAB Code")
    parser.add_argument("--input", required=True, help="源码根目录")
    parser.add_argument("--output", default="jab_out_dir", help="输出根目录")
    parser.add_argument("--writer", type=Path, help="jabcodeWriter 路径（可选）")
    parser.add_argument(
        "--ext",
        help="额外扩展名列表，用逗号分隔，例如 .vue,.sql（可选，大小写不敏感）",
    )
    args = parser.parse_args()

    src_dir = Path(args.input)
    if not src_dir.is_dir():
        print(f"错误：输入目录不存在：{src_dir}", file=sys.stderr)
        return 1

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)

    exts = set(DEFAULT_EXTS)
    if args.ext:
        for e in args.ext.split(","):
            e = e.strip().lower()
            if not e.startswith("."):
                e = "." + e
            exts.add(e)

    # 收集所有匹配扩展名的文件，保持相对目录层级
    files = sorted(
        p for p in src_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts
    )
    if not files:
        print(f"未找到支持的源码文件：{src_dir}", file=sys.stderr)
        return 1

    script_dir = Path(__file__).resolve().parent
    encode_script = script_dir / "encode_to_jab.py"
    if not encode_script.is_file():
        print(f"错误：找不到 {encode_script}", file=sys.stderr)
        return 1

    success = 0
    failed = 0
    manifest = []

    for src_file in files:
        rel = src_file.relative_to(src_dir)
        # 输出目录保持原相对目录层级，文件部分用下划线替换扩展名
        sub_dir = out_root / rel.parent / safe_name(rel.name)
        sub_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n编码：{rel} -> {sub_dir}")
        cmd = [
            sys.executable,
            str(encode_script),
            "--input",
            str(src_file),
            "--output",
            str(sub_dir),
        ]
        if args.writer:
            cmd.extend(["--writer", str(args.writer)])

        result = subprocess.run(cmd)
        if result.returncode == 0:
            success += 1
            manifest.append(
                {
                    "original": rel.as_posix(),
                    "encoded_dir": sub_dir.relative_to(out_root).as_posix(),
                }
            )
        else:
            failed += 1
            print(f"  失败：{rel}", file=sys.stderr)

    # 写入清单，方便批量还原
    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n完成：成功 {success} 个，失败 {failed} 个，输出根目录：{out_root.resolve()}")
    print(f"清单文件：{manifest_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
