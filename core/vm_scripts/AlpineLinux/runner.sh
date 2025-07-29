#!/usr/bin/env bash
set -euo pipefail

IMG="/Users/soledaco/Desktop/pet/alpine.qcow2"
VNC_PORT=5901
NOVNC_PORT=6080
NOVNC_DIR="$HOME/noVNC"

# Check image
if [[ ! -f "$IMG" ]]; then
  echo "Error: '$IMG' not found"
  exit 1
fi

# Kill any previous QEMU or noVNC on those ports
lsof -ti tcp:$VNC_PORT | xargs -r kill -9 || true
lsof -ti tcp:$NOVNC_PORT | xargs -r kill -9 || true

# Launch QEMU VM in background
qemu-system-x86_64 \
  -m 512 \
  -drive file="$IMG",format=qcow2,if=virtio \
  -boot c \
  -netdev user,id=net0,hostfwd=tcp::8000-:8000 \
  -device virtio-net-pci,netdev=net0 \
  -vnc 127.0.0.1:1 \
  -daemonize

# Start noVNC WebSocket proxy
"$NOVNC_DIR/utils/novnc_proxy" --vnc 127.0.0.1:$VNC_PORT --listen $NOVNC_PORT &

