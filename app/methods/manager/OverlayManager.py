#VM_share/app/methods/manager/OverlayManager.py
import subprocess
import socket
import json
import time
import os
import configs.vm_config as configs
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
    print(f'Error: {e}')
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
    Manages a user's qcow2 overlay and a headless QEMU instance with VNC+QMP on UNIX sockets.
    """
    def __init__(self, user_id: str, vmid: str):
        self.base_image = Path(configs.ALPINE_IMAGE_PATH)
        self.overlay_dir = Path(configs.ALPINE_OVERLAYS_DIR)
        # self.overlay_dir.mkdir(parents=True, exist_ok=True) <-- of no use anymore 
        self.user_id = user_id
        self.vmid = vmid

    def overlay_path(self) -> Path:
        return self.overlay_dir / f"alpine_{self.vmid}.qcow2"

    def create_overlay(self) -> Path:
        try:
            overlay = self.overlay_path()
            if overlay.exists():
                logging.info(f"VM_share/app/methods/OverlayManager.py: Overlay already exists for user {self.user_id}: {overlay}")
                return overlay

            subprocess.check_call([
                "qemu-img", "create",
                "-f", "qcow2",
                "-F", "qcow2",
                "-b", str(self.base_image),
                str(overlay)
            ])
            logging.info(f"VM_share/app/methods/OverlayManager.py: Created overlay for user {self.user_id}: {overlay}")
            return overlay
        except subprocess.CalledProcessError as e:
            logging.error(f"VM_share/app/methods/OverlayManager.py: Failed to create overlay for user {self.user_id}. Command failed: {e}")
            raise
        except Exception as e:
            logging.exception(f"VM_share/app/methods/OverlayManager.py: Unexpected error during overlay creation for user {self.user_id}: {e}")
            raise


    def _socket_paths(self, vmid: str):
        vnc = RUN_DIR / f"vnc-{vmid}.sock"
        qmp = RUN_DIR / f"qmp-{vmid}.sock"
        return vnc, qmp

    def boot_vm(self, vmid: str, memory_mb: int = None) -> dict:
        overlay = self.overlay_path()
        if not overlay.exists():
            error_msg = f"VM_share/app/methods/OverlayManager.py: Overlay missing for user {self.user_id}: {overlay}"
            logging.error(error_msg)
            raise FileNotFoundError(error_msg)

        vnc_sock, qmp_sock = self._socket_paths(vmid)
        for s in (vnc_sock, qmp_sock):
            if s.exists():
                s.unlink()
                logging.warning(f"VM_share/app/methods/OverlayManager.py: Removed existing socket: {s}")

        mem = str(memory_mb or configs.ALPINE_MEMORY)
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
        logging.info(f"VM_share/app/methods/OverlayManager.py: Launching QEMU for user {self.user_id} with vmid={vmid}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = (
                f"VM_share/app/methods/OverlayManager.py:\n"
                f"QEMU failed for user {self.user_id} (vmid={vmid})\n"
                f"Return code: {result.returncode}\n"
                f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        logging.info(f"VM_share/app/methods/OverlayManager.py: QEMU successfully started for user {self.user_id} (vmid={vmid})")

        return {
            "user_id": self.user_id,
            "vmid": vmid,
            "overlay": str(overlay),
            "vnc_socket": str(vnc_sock),
            "qmp_socket": str(qmp_sock),
            "started_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
