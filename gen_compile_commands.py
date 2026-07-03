#!/usr/bin/env python3
"""
为 jabcode 三个子项目生成 compile_commands.json。
不需要 clang，直接解析 `make -Bn` 的编译命令。
"""

import json
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent
SUBDIRS = ["src/jabcode", "src/jabcodeWriter", "src/jabcodeReader"]


def find_source_after_c(tokens: List[str]) -> Optional[str]:
    """在命令行 tokens 中找到 -c 后面的源文件名（跳过选项）。"""
    for i, tok in enumerate(tokens):
        if tok == "-c" and i + 1 < len(tokens):
            for candidate in tokens[i + 1 :]:
                if not candidate.startswith("-"):
                    return candidate
    return None


def generate() -> List[Dict]:
    entries: List[Dict] = []

    for sub in SUBDIRS:
        cwd = (REPO_ROOT / sub).resolve()
        result = subprocess.run(
            ["make", "-Bn"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or "-c" not in line:
                continue
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if "-c" not in tokens:
                continue

            src_name = find_source_after_c(tokens)
            if not src_name:
                continue
            src = Path(src_name)
            if not src.is_absolute():
                src = cwd / src

            entries.append(
                {
                    "directory": str(cwd),
                    "command": line,
                    "file": str(src.resolve()),
                }
            )

    return entries


def main() -> int:
    entries = generate()
    output = REPO_ROOT / "compile_commands.json"
    output.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"生成 {output}，共 {len(entries)} 条编译命令")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
