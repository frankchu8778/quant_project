#!/bin/bash

# --- 配置區 ---
# 請將這裡改為你 SSD 數據的真實路徑
SSD_SOURCE="/home/newt/quant_project/data/tw/raw/stock/daily_update"  
# 這是記憶體掛載點
RAM_PATH="/dev/shm/qlib_ram"    
# 分配 40GB (你有 128G 非常夠用)
RAM_SIZE="5G"                  

echo "🚀 開始準備 RAMDisk 加速環境..."

# 1. 檢查並掛載 tmpfs
if ! mountpoint -q "$RAM_PATH"; then
    echo "  -> 正在掛載 $RAM_SIZE 記憶體空間到 $RAM_PATH..."
    sudo mkdir -p "$RAM_PATH"
    sudo mount -t tmpfs -o size=$RAM_SIZE tmpfs "$RAM_PATH"
fi

# 2. 同步數據 (rsync 只會複製有變動的檔案)
echo "  -> 正在同步數據 (SSD -> RAM)..."
sudo rsync -av --delete "$SSD_SOURCE/" "$RAM_PATH/"

# 3. 調整權限 (確保 Python 有權限讀取)
sudo chmod -R 777 "$RAM_PATH"

echo "✅ 環境就緒！數據已駐留在記憶體。"

# 掛載指令
# bash /home/newt/quant_project/setting_files/prepare_ramdisk.sh