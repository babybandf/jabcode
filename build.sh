#!/usr/bin/env bash
# 完整构建 jabcode 核心库、Writer、Reader，并生成 compile_commands.json
# 用法：
#   ./build.sh         完整构建
#   ./build.sh clean   执行 make clean 并删除 compile_commands.json
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

if [[ "${1:-}" == "clean" ]]; then
    echo "=== 清理 ==="
    make -C "$REPO_ROOT/src/jabcode" clean
    make -C "$REPO_ROOT/src/jabcodeWriter" clean
    make -C "$REPO_ROOT/src/jabcodeReader" clean
    rm -f "$REPO_ROOT/compile_commands.json"
    echo "=== 清理完成 ==="
    exit 0
fi

echo "=== 构建核心库 ==="
make -C "$REPO_ROOT/src/jabcode" clean
make -C "$REPO_ROOT/src/jabcode"

echo "=== 构建 jabcodeWriter ==="
make -C "$REPO_ROOT/src/jabcodeWriter" clean
make -C "$REPO_ROOT/src/jabcodeWriter"

echo "=== 构建 jabcodeReader ==="
make -C "$REPO_ROOT/src/jabcodeReader" clean
make -C "$REPO_ROOT/src/jabcodeReader"

echo "=== 生成 compile_commands.json ==="
python3 "$REPO_ROOT/gen_compile_commands.py"

echo "=== 完成 ==="
ls -l "$REPO_ROOT/src/jabcode/build/libjabcode.a"
ls -l "$REPO_ROOT/src/jabcodeWriter/bin/jabcodeWriter"
ls -l "$REPO_ROOT/src/jabcodeReader/bin/jabcodeReader"
