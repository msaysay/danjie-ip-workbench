#!/bin/sh
set -eu
[ "$(uname -s)" = Darwin ] || { echo "请在Mac运行这个启动文件"; exit 1; }
[ "$(uname -s)" = Darwin ] || { echo "请在Mac运行这个启动文件"; exit 1; }
[ "$(uname -s)" = Darwin ] || { echo "请在Mac运行这个启动文件"; exit 1; }
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$(uname -m)" in arm64|aarch64) TARGET=mac-arm64;; x86_64) TARGET=mac-x64;; *) echo "暂不支持此Mac架构"; exit 1;; esac
mkdir -p "$ROOT/.runtime"
if [ ! -x "$ROOT/.runtime/python/bin/python3" ]; then
 /usr/bin/tar -xzf "$ROOT/assets/runtimes/$TARGET.tar.gz" -C "$ROOT/.runtime"
fi
exec "$ROOT/.runtime/python/bin/python3" -I -X utf8 "$ROOT/scripts/launch.py" "$@"
