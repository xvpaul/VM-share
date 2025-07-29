#!/usr/bin/env bash
BASE_IMG="../../../../alpine.qcow2"
SESSION_DIR="/var/lib/vm-sessions"
VM_MEMORY="1024M"
VNC_BASE=5900
NOVNC_BASE=6080
NOVNC_WEB_PATH="/usr/share/novnc/"
QEMU_BINARY="qemu-system-x86_64"
enable_kvm=true

# How to use:
# In your launch script (e.g., launch-user-vm.sh), add at the top:
#   source /path/to/vm_config.sh
# Then refer to the variables above instead of hardcoding paths/ports/etc.
IMG="/Users/soledaco/Desktop/pet/alpine.qcow2"