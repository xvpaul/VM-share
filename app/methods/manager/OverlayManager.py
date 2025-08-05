# app/methods/vm.py
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import socket
import json
import time
import configs.vm_config as configs

RUN_DIR = Path("/tmp/qemu")
RUN_DIR.mkdir(parents=True, exist_ok=True)

class QemuOverlayManager:
    """
    Manages a user's qcow2 overlay and a headless QEMU instance with VNC+QMP on UNIX sockets.
    Integrate with a small session registry (DB/Redis) outside this class.
    """
    def __init__(self, user_id: str):
        self.base_image = Path(configs.ALPINE_IMAGE_PATH)
        self.overlay_dir = Path(configs.ALPINE_OVERLAYS_DIR)
        # self.overlay_dir.mkdir(parents=True, exist_ok=True)
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
            "-enable-kvm",
            "-m", mem,
            "-drive", f"file={overlay},format=qcow2,if=virtio,cache=writeback,discard=unmap",
            "-nic", "user,model=virtio-net-pci",
            "-vnc", f"unix:{vnc_sock}",
            "-qmp", f"unix:{qmp_sock},server,nowait",
            "-display", "none",
            "-daemonize",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"[QEMU ERROR]\nReturn code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        print(f"[>] QEMU started for user {self.user_id} (vmid={vmid})")

        return {
            "user_id": self.user_id,
            "vmid": vmid,
            "overlay": str(overlay),
            "vnc_socket": str(vnc_sock),
            "qmp_socket": str(qmp_sock),
            "started_at": datetime.utcnow().isoformat() + "Z",
        }
    
    @staticmethod
    def cleanup_unused_overlays(overlays_root: Path, older_than_seconds: int = 3600):
        """
        Remove overlay directories older than a given threshold.

        :param overlays_root: Path to the directory containing VM overlay folders
        :param older_than_seconds: Age threshold in seconds; directories older than this are removed
        """
        now = time.time()
        if not overlays_root.exists() or not overlays_root.is_dir():
            return

        for overlay_dir in overlays_root.iterdir():
            try:
                if overlay_dir.is_dir():
                    mtime = overlay_dir.stat().st_mtime
                    if now - mtime > older_than_seconds:
                        shutil.rmtree(overlay_dir)
                        print(f"[CLEANUP] Removed stale overlay: {overlay_dir}")
            except Exception as e:
                print(f"[CLEANUP ERROR] Cannot remove {overlay_dir}: {e}")

    @staticmethod
    def cleanup_stale_processes(procs: dict, older_than_seconds: int = 3600):
        """
        Terminate websockify processes that have exited or been running too long.

        :param procs: Dict mapping vmid to (subprocess.Popen, start_time)
        :param older_than_seconds: Maximum allowed runtime; processes older than this are killed
        """
        now = time.time()
        for vmid, (proc, start_time) in list(procs.items()):
            # If process has already exited, remove from tracking
            if proc.poll() is not None:
                procs.pop(vmid, None)
                print(f"[CLEANUP] Removed completed process for VM {vmid}")
                continue

            # If running too long, terminate it
            if now - start_time > older_than_seconds:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                finally:
                    procs.pop(vmid, None)
                    print(f"[CLEANUP] Killed stale process for VM {vmid}")
