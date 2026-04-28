#!/bin/bash

# Install Conky to GNOME autostart
set -e

# Get the current project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
DESKTOP_FILE="start_conky.desktop"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/$DESKTOP_FILE"

# Check if the desktop file exists
if [ ! -f "$PROJECT_DIR/$DESKTOP_FILE" ]; then
    echo "Error: $DESKTOP_FILE not found in $PROJECT_DIR"
    exit 1
fi

# Create autostart directory if it doesn't exist
if [ ! -d "$AUTOSTART_DIR" ]; then
    echo "Creating autostart directory: $AUTOSTART_DIR"
    mkdir -p "$AUTOSTART_DIR"
fi

# Replace the Exec path with the current project directory
echo "Installing conky autostart file to $AUTOSTART_FILE"
sed "s|Exec=.*|Exec=bash -c 'sleep 5 \&\& $PROJECT_DIR/start_conky.sh'|" "$PROJECT_DIR/$DESKTOP_FILE" > "$AUTOSTART_FILE"

# Set correct permissions
chmod 644 "$AUTOSTART_FILE"

echo "Success! Conky will start automatically on next boot."
echo "To test it immediately, you can run:"
echo "  bash -c 'sleep 5 && $PROJECT_DIR/start_conky.sh'"
