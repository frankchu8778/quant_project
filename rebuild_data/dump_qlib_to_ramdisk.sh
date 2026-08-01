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

# --- 使用說明 ---
# 前置：需有 duckdb/daily_data.duckdb，以及 quant_research conda 環境（可改 PYTHON 變數）
#
# 基本用法（專案根目錄）：
#   bash rebuild_data/dump_qlib_to_ramdisk.sh
# 或絕對路徑：
#   bash /home/newt/quant_project/rebuild_data/dump_qlib_to_ramdisk.sh
#
# 流程：掛載 40G tmpfs → /dev/shm/qlib_ram → 從 DuckDB dump qlib bin
# 掛載需 sudo，執行時會提示輸入密碼。
#
# 指定其他 Python：
#   PYTHON=/path/to/python bash rebuild_data/dump_qlib_to_ramdisk.sh
#
# 卸載 ramdisk（重開機也會清掉）：
#   sudo umount /dev/shm/qlib_ram
#
# 注意：此腳本是「DuckDB 重建 qlib」；若只是把已有 SSD qlib 同步到 RAM，
# 請改用 setting_files/prepare_ramdisk.sh
