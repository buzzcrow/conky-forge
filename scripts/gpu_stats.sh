#!/bin/bash
# gpu_stats.sh — Query all NVIDIA GPU metrics in one nvidia-smi call
# and write each value to a separate file for conky ${cat} usage.
#
# This avoids spawning 14+ nvidia-smi processes per update cycle.

CACHE_DIR="/tmp/conky-gpu"
mkdir -p "$CACHE_DIR"

output=$(nvidia-smi --query-gpu=temperature.gpu,fan.speed,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,driver_version --format=csv,noheader,nounits 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$output" ]; then
    # nvidia-smi failed — write placeholders
    for f in temp fan gpu_util mem_util mem_used mem_total power; do
        echo "0" > "$CACHE_DIR/$f"
    done
    echo "N/A" > "$CACHE_DIR/driver"
    exit 0
fi

IFS=', ' read -r temp fan gpu_util mem_util mem_used mem_total power driver <<< "$output"

echo "$temp"     > "$CACHE_DIR/temp"
echo "$fan"      > "$CACHE_DIR/fan"
echo "$gpu_util" > "$CACHE_DIR/gpu_util"
echo "$mem_util" > "$CACHE_DIR/mem_util"
echo "$mem_used" > "$CACHE_DIR/mem_used"
echo "$mem_total"> "$CACHE_DIR/mem_total"
echo "$power"    > "$CACHE_DIR/power"
echo "$driver"   > "$CACHE_DIR/driver"
