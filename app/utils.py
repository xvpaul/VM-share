# /app/utils.py
import socket
import subprocess
import logging
from threading import Thread
import os
from pathlib import Path
import configs.vm_profiles as vm_profiles

RUN_DIR = Path("/tmp/qemu")

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def cleanup_vm(vmid: str, store) -> None:
    """
    Cleans up QEMU VM processes, sockets, and overlay file for a given VM ID.
    `store` is a SessionStore-like object with `.get(vmid)` and `.delete(vmid)`.
    """
    try:
        session = store.get(vmid)
        if not session:
            logging.warning(f"[cleanup_vm] No active session found for VM {vmid}")
            return

        user_id  = session.get("user_id")
        os_type  = session.get("os_type")
        overlay_path = session.get("overlay_path")  
        if not overlay_path:
            if not os_type or os_type not in vm_profiles.VM_PROFILES:
                logging.error(f"[cleanup_vm] Unknown or missing os_type '{os_type}' for VM {vmid}")
                store.delete(vmid)  
            profile = vm_profiles.VM_PROFILES[os_type]
            overlay_path = profile["overlay_dir"] / f"{profile['overlay_prefix']}_{vmid}.qcow2"

        logging.info(f"[cleanup_vm] Cleaning VM {vmid} (user={user_id}, os={os_type})")

        qemu_pid = session.get("qemu_pid")
        ws_pid   = session.get("websockify_pid")

        if ws_pid:
            try:
                os.kill(ws_pid, 15)
                logging.info(f"[cleanup_vm] SIGTERM → websockify pid={ws_pid}")
            except ProcessLookupError:
                logging.info(f"[cleanup_vm] websockify pid={ws_pid} already gone")
            except Exception:
                logging.exception(f"[cleanup_vm] failed to SIGTERM websockify pid={ws_pid}")

        if qemu_pid:
            try:
                os.kill(qemu_pid, 15)
                logging.info(f"[cleanup_vm] SIGTERM → qemu pid={qemu_pid}")
            except ProcessLookupError:
                logging.info(f"[cleanup_vm] qemu pid={qemu_pid} already gone")
            except Exception:
                logging.exception(f"[cleanup_vm] failed to SIGTERM qemu pid={qemu_pid}")
        else:
            subprocess.run(["pkill", "-f", str(overlay_path)], check=False)
            subprocess.run(["pkill", "-f", vmid], check=False)
            logging.info(f"[cleanup_vm] pkill by overlay/vmid issued")

        try:
            overlay_path = Path(overlay_path)
            if overlay_path.exists():
                overlay_path.unlink()
                logging.info(f"[cleanup_vm] Deleted overlay {overlay_path}")
            else:
                logging.warning(f"[cleanup_vm] Overlay not found: {overlay_path}")
        except Exception:
            logging.exception(f"[cleanup_vm] Failed to delete overlay {overlay_path}")

        for sock in (RUN_DIR / f"vnc-{vmid}.sock", RUN_DIR / f"qmp-{vmid}.sock"):
            try:
                if sock.exists():
                    sock.unlink()
                    logging.info(f"[cleanup_vm] Removed socket {sock}")
            except Exception:
                logging.exception(f"[cleanup_vm] Failed to remove socket {sock}")

        try:
            store.delete(vmid)
        except Exception:
            logging.exception(f"[cleanup_vm] store.delete failed for {vmid}")

    except Exception as e:
        logging.exception(f"[cleanup_vm] Error while cleaning up VM {vmid}: {e}")


    
def start_websockify(vmid: str, port: int, vnc_unix_sock: str, store) -> subprocess.Popen:
    
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
