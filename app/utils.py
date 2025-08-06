import socket
import subprocess
import logging
import os
from threading import Thread
from pathlib import Path

def find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    
def cleanup_vm(vmid: str):
    """
    Cleans up QEMU VM processes and overlay file for a given VM ID and user ID.
    """
    overlay_path = f"/root/myapp/overlays/Alpine_Linux/alpine_{vmid}.qcow2"

    try:
        subprocess.run(
            ["pkill", "-f", overlay_path],
            check=False
        )
        logging.info(f"[cleanup_vm] Killed QEMU processes using {overlay_path}")

        subprocess.run(
            ["pkill", "-f", vmid],
            check=False
        )
        logging.info(f"[cleanup_vm] Killed Websockify processes containing {vmid}")

        if os.path.exists(overlay_path):
            os.remove(overlay_path)
            logging.info(f"[cleanup_vm] Deleted overlay file {overlay_path}")
        else:
            logging.warning(f"[cleanup_vm] Overlay file not found: {overlay_path}")

    except Exception as e:
        logging.error(f"[cleanup_vm] Error while cleaning up VM {vmid}: {e}")

    
def start_websockify(vmid: str, port: int, vnc_unix_sock: str) -> subprocess.Popen:
    static_dir = Path(__file__).parent / "static"

    cmd = [
        "websockify",
        "--web", str(static_dir),
        "--verbose",  # <-- this is essential
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
            if "client disconnected" in line.lower():
                logging.info(f"[websockify:{vmid}] Client disconnected. Clean-up starts.")
                cleanup_vm(vmid)
            elif "client connected" in line.lower():
                logging.info(f"[websockify:{vmid}] Client connected.")

    Thread(target=monitor_output, daemon=True).start()

    return proc
