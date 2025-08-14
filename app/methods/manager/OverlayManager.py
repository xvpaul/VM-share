# /app/methods/manager/OverlayManager.py
import subprocess
import socket
import json
import time
import os
import configs.vm_profiles as vm_profiles
import configs.log_config as logs
import logging
from pathlib import Path
from datetime import datetime, timezone

"""
Logging configuration 
"""

log_file_path = os.path.join(logs.LOG_DIR, logs.LOG_NAME)

try:
    os.makedirs(logs.LOG_DIR, exist_ok=True)
    logging.basicConfig(
        filename=log_file_path,
        level=logging.INFO,
        format='%(asctime)s.%(msecs)05d %(message)s',
        datefmt='%Y-%m-%d %H-%M-%S',
    )

except Exception as e:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s.%(msecs)05d %(message)s',
        datefmt='%Y-%m-%d %H-%M-%S',
    )
    logging.error(f"Failed to initialize file logging: {e}")


RUN_DIR = Path("/tmp/qemu")
RUN_DIR.mkdir(parents=True, exist_ok=True)

class QemuOverlayManager:
    """
    Manages a user's qcow2 overlay and a headless QEMU instance with VNC+QMP on UNIX sockets,
    supporting multiple OS profiles (e.g., alpine, ubuntu).
    """
    def __init__(self, user_id: str, vmid: str, os_type: str = "alpine"):
        if os_type not in vm_profiles.VM_PROFILES:
            raise ValueError(f"Unsupported OS type: {os_type}")
        
        self.profile = vm_profiles.VM_PROFILES[os_type]
        self.user_id = user_id
        self.vmid = vmid
        self.os_type = os_type

    def overlay_path(self) -> Path:
        prefix = self.profile["overlay_prefix"]
        return self.profile["overlay_dir"] / f"{prefix}_{self.vmid}.qcow2"

    def create_overlay(self) -> Path:
        try:
            overlay = self.overlay_path()
            if overlay.exists():
                logging.info(f"Overlay already exists for user {self.user_id}: {overlay}")
                return overlay

            subprocess.check_call([
                "qemu-img", "create",
                "-f", "qcow2",
                "-F", "qcow2",
                "-b", str(self.profile["base_image"]),
                str(overlay)
            ])
            logging.info(f"Created overlay for user {self.user_id}: {overlay}")
            return overlay

        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to create overlay for user {self.user_id}. Command failed: {e}")
            raise
        except Exception as e:
            logging.exception(f"Unexpected error during overlay creation for user {self.user_id}: {e}")
            raise

    def _socket_paths(self, vmid: str):
        vnc = RUN_DIR / f"vnc-{vmid}.sock"
        qmp = RUN_DIR / f"qmp-{vmid}.sock"
        return vnc, qmp

    def boot_vm(self, vmid: str, memory_mb: int = None) -> dict:
        overlay = self.overlay_path()
        if not overlay.exists():
            error_msg = f"Overlay missing for user {self.user_id}: {overlay}"
            logging.error(error_msg)
            raise FileNotFoundError(error_msg)

        vnc_sock, qmp_sock = self._socket_paths(vmid)
        for s in (vnc_sock, qmp_sock):
            if s.exists():
                s.unlink()
                logging.warning(f"Removed existing socket: {s}")

        mem = str(memory_mb or self.profile["default_memory"])
        cmd = [
            "qemu-system-x86_64",
            "-m", mem,
            "-drive", f"file={overlay},format=qcow2,if=virtio,cache=writeback,discard=unmap",
            "-nic", "user,model=virtio-net-pci",
            "-vnc", f"unix:{vnc_sock}",
            "-qmp", f"unix:{qmp_sock},server,nowait",
            "-display", "none",
            "-daemonize",
        ]

        logging.info(f"Launching QEMU for user {self.user_id} with vmid={vmid}, os_type={self.os_type}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = (
                f"QEMU failed for user {self.user_id} (vmid={vmid})\n"
                f"Return code: {result.returncode}\n"
                f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        logging.info(f"QEMU successfully started for user {self.user_id} (vmid={vmid})")

        return {
            "user_id": self.user_id,
            "vmid": vmid,
            "os_type": self.os_type,
            "overlay": str(overlay),
            "vnc_socket": str(vnc_sock),
            "qmp_socket": str(qmp_sock),
            "started_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }