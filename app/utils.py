# /utils.py
import socket
import subprocess
import logging
import os
import configs.vm_profiles as vm_profiles
from threading import Thread
from pathlib import Path


RUN_DIR = Path("/tmp/qemu")

def find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    
def cleanup_vm(vmid: str, sessions: dict):
    """
    Cleans up QEMU VM processes, sockets, and overlay file for a given VM ID.
    """
    try:
        session = sessions.pop(vmid, None)
        if not session:
            logging.warning(f"[cleanup_vm] No active session found for VM {vmid}")
            return

        user_id = session.get("user_id")
        os_type = session.get("os_type")
        if not os_type or os_type not in vm_profiles.VM_PROFILES:
            logging.error(f"[cleanup_vm] Unknown or missing os_type '{os_type}' for VM {vmid}")
            return

        profile = vm_profiles.VM_PROFILES[os_type]
        overlay_path = profile["overlay_dir"] / f"{profile['overlay_prefix']}_{vmid}.qcow2"

        logging.info(f"[cleanup_vm] Cleaning up VM {vmid} for user {user_id} with OS type {os_type}")

        subprocess.run(["pkill", "-f", str(overlay_path)], check=False)
        logging.info(f"[cleanup_vm] Killed QEMU processes using {overlay_path}")

        subprocess.run(["pkill", "-f", vmid], check=False)
        logging.info(f"[cleanup_vm] Killed Websockify processes containing {vmid}")

        if overlay_path.exists():
            overlay_path.unlink()
            logging.info(f"[cleanup_vm] Deleted overlay file {overlay_path}")
        else:
            logging.warning(f"[cleanup_vm] Overlay file not found: {overlay_path}")

        vnc_sock = RUN_DIR / f"vnc-{vmid}.sock"
        qmp_sock = RUN_DIR / f"qmp-{vmid}.sock"
        for sock in (vnc_sock, qmp_sock):
            if sock.exists():
                sock.unlink()
                logging.info(f"[cleanup_vm] Removed socket: {sock}")

    except Exception as e:
        logging.exception(f"[cleanup_vm] Error while cleaning up VM {vmid}: {e}")

    
def start_websockify(vmid: str, port: int, vnc_unix_sock: str, sessions: dict) -> subprocess.Popen:
    static_dir = Path(__file__).parent / "static"

    cmd = [
        "websockify",
        "--web", str(static_dir),
        "--verbose",  # <-- testing stdout for this fuck
        f"0.0.0.0:{port}",
        "--unix-target", vnc_unix_sock,
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def monitor_output():
        for line in proc.stdout:
            line = line.strip()
            logging.info(f"[websockify:{vmid}] {line}")
            if "client closed connection" in line.lower():
                logging.info(f"[websockify:{vmid}] Client disconnected. Clean-up starts.")
                cleanup_vm(vmid, sessions)
                # Client connected
            elif "connecting to unix socket" in line.lower():
                logging.info(f"[websockify:{vmid}] Client connected.")

    Thread(target=monitor_output, daemon=True).start()

    return proc
