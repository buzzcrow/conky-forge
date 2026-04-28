#!/bin/bash
# start_conky.sh — Generate conky config from hardware detection and launch conky
#
# Usage:
#   ./start_conky.sh [--scheme NAME] [--market CODE] [--interval HOURS]
#
# Add to autostart (GNOME):
#   cp start_conky.desktop ~/.config/autostart/
#
# Or add to crontab:
#   @reboot sleep 10 && /path/to/start_conky.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONKY_CONF="$HOME/.config/conky/conky.conf"

# Parse --market and --interval from args (pass remaining args to generate_conky.py)
MARKET="en-US"
INTERVAL="0.5"
CONKY_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --market)
            MARKET="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        *)
            CONKY_ARGS+=("$1")
            shift
            ;;
    esac
done

# Kill existing conky
killall conky 2>/dev/null
sleep 1

# Generate config first (wallpaper script reads layout from it)
python3 "$SCRIPT_DIR/scripts/generate_conky.py" \
    --output "$CONKY_CONF" \
    --blacklist "$SCRIPT_DIR/blacklist.conf" \
    "${CONKY_ARGS[@]}"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate conky config" >&2
    exit 1
fi

# Download Bing wallpaper gallery and set current wallpaper
# (reads gap_x and panel width from generated conky.conf)
echo "Setting Bing wallpaper (interval=${INTERVAL}h)..."
python3 "$SCRIPT_DIR/scripts/bing_wallpaper.py" \
    --market "$MARKET" --interval "$INTERVAL" || \
    echo "WARN: Wallpaper script failed, continuing without wallpaper update"

# Start conky
echo "Starting conky..."
conky -c "$CONKY_CONF" -d
echo "Conky started (pid: $(pgrep -n conky))"
