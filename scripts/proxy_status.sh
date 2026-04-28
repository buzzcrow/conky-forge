#!/bin/bash
# Check proxy status (192.168.0.106:8089)
# Outputs: "ON  host:port" or "OFF host:port"
PROXY_HOST="192.168.0.106"
PROXY_PORT="8089"

if timeout 2 bash -c "echo >/dev/tcp/$PROXY_HOST/$PROXY_PORT" 2>/dev/null; then
    echo "ON  $PROXY_HOST:$PROXY_PORT"
else
    echo "OFF $PROXY_HOST:$PROXY_PORT"
fi
