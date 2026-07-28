#!/bin/bash
# 從 DuckDB 拉 daily_data → 轉 qlib → 寫入 /dev/shm/qlib_ram
# 用法：bash rebuild_data/dump_qlib_to_ramdisk.sh
# （sudo 會提示輸入密碼）

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAM_PATH="/dev/shm/qlib_ram"
RAM_SIZE="40G"
PYTHON="${PYTHON:-/home/newt/miniconda3/envs/quant_research/bin/python}"

echo "開始準備 RAMDisk 並 dump qlib..."

if ! mountpoint -q "$RAM_PATH"; then
    echo "  -> 掛載 $RAM_SIZE → $RAM_PATH"
    sudo mkdir -p "$RAM_PATH"
    sudo mount -t tmpfs -o size="$RAM_SIZE" tmpfs "$RAM_PATH"
else
    echo "  -> 已掛載: $RAM_PATH"
fi
sudo chmod 777 "$RAM_PATH"

echo "  -> DuckDB → qlib dump..."
cd "$PROJECT_ROOT"
"$PYTHON" "$PROJECT_ROOT/rebuild_data/dump_qlib_to_ramdisk.py"

echo "完成：$RAM_PATH"
