# app/methods/vm.py
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

import configs.vm_config as configs

RUN_DIR = Path("/tmp/qemu")
RUN_DIR.mkdir(parents=True, exist_ok=True)

class QemuOverlayManager:
    """
    Manages a user's qcow2 overlay and a headless QEMU instance with VNC+QMP on UNIX sockets.
    Integrate with a small session registry (DB/Redis) outside this class.
    """
    def __init__(self, user_id: str):
        self.base_image = Path(configs.ALPINE_IMAGE_NAME)
        self.overlay_dir = Path(configs.ALPINE_OVERLAYS_DIR)
        self.overlay_dir.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id

    def overlay_path(self) -> Path:
        return self.overlay_dir / f"alpine_{self.user_id}.qcow2"

    def create_overlay(self) -> Path:
        try:
            overlay = self.overlay_path()
            if overlay.exists():
                print(f"[!] Overlay already exists for user {self.user_id}: {overlay}")
                return overlay

            subprocess.check_call([
                "qemu-img", "create",
                "-f", "qcow2",
                "-F", "qcow2",
                "-b", str(self.base_image),
                str(overlay)
            ])
            print(f"[+] Created overlay for user {self.user_id}: {overlay}")
            return overlay
        except Exception as e:
            print(f'create_overlay error: {e}')

    def _socket_paths(self, vmid: str):
        vnc = RUN_DIR / f"vnc-{vmid}.sock"
        qmp = RUN_DIR / f"qmp-{vmid}.sock"
        return vnc, qmp

    def boot_vm(self, vmid: str, memory_mb: int = None) -> dict:
        """
        Start QEMU in the background with VNC+QMP UNIX sockets. Returns session metadata.
        """
        overlay = self.overlay_path()
        if not overlay.exists():
            raise FileNotFoundError(f"Overlay missing: {overlay}")
        vnc_sock, qmp_sock = self._socket_paths(vmid)
        for s in (vnc_sock, qmp_sock):
            if s.exists():
                s.unlink()

        mem = str(memory_mb or configs.ALPINE_MEMORY)
        cmd = [
            "qemu-system-x86_64",
            "-accel", "hvf",
            "-m", mem,
            "-drive", f"file={overlay},format=qcow2,if=virtio,cache=writeback,discard=unmap",
            "-nic", "user,model=virtio-net-pci",
            "-vnc", f"unix:{vnc_sock}",
            "-qmp", f"unix:{qmp_sock},server,nowait",
            "-display", "none",
            "-daemonize",
        ]
        subprocess.check_call(cmd)
        print(f"[>] QEMU started for user {self.user_id} (vmid={vmid})")

        return {
            "user_id": self.user_id,
            "vmid": vmid,
            "overlay": str(overlay),
            "vnc_socket": str(vnc_sock),
            "qmp_socket": str(qmp_sock),
            "started_at": datetime.utcnow().isoformat() + "Z",
        }

    # def powerdown(self, vmid: str) -> bool:
    #     """
    #     Graceful ACPI shutdown via QMP; fall back to kill if needed outside this class.
    #     """
    #     import json
    #     import time

    #     _, qmp_sock = self._socket_paths(vmid)
    #     try:
    #         with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
    #             s.settimeout(2.0)
    #             s.connect(str(qmp_sock))

    #             def send(obj):
    #                 s.sendall((json.dumps(obj) + "\n").encode("utf-8"))

    #             # Read greeting
    #             s.recv(4096)

    #             send({"execute": "qmp_capabilities"})
    #             s.recv(4096)

    #             send({"execute": "system_powerdown"})
    #             # Give the guest some time to shutdown
    #             time.sleep(2)
    #             return True
    #     except Exception as e:
    #         print(f"[!] QMP powerdown failed: {e}")
    #         return False
