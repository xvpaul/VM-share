# /app/utils.py
import socket
import subprocess
import logging
from threading import Thread
import os
from pathlib import Path
from typing import Optional
import configs.config as VM_PROFILES

logger = logging.getLogger(__name__)


RUN_DIR = Path("/tmp/qemu")


def find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _to_int(val: Optional[str]) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def cleanup_vm(vmid: str, store) -> None:
    """
    Cleans up QEMU VM processes, sockets, overlay/scratch/custom ISO file for a given VM ID.
    `store` is a Redis-backed SessionStore with `.get(vmid)` and `.delete(vmid)`.
    """
    try:
        session = store.get(vmid)
        if not session:
            logger.warning(f"[cleanup_vm] No active session found for VM {vmid}")
            return

        user_id = session.get("user_id")
        os_type = session.get("os_type")

        logger.info(f"[cleanup_vm] Cleaning VM {vmid} (user={user_id}, os={os_type})")

        # Figure out what to remove later
        files_to_remove = []

        if os_type == "custom":
            iso_path = session.get("iso")
            if iso_path:
                files_to_remove.append(Path(iso_path))
        else:
            overlay_path = session.get("overlay_path")
            if overlay_path:
                files_to_remove.append(Path(overlay_path))
            else:
                if os_type and os_type in VM_PROFILES:
                    profile = VM_PROFILES[os_type]
                    files_to_remove.append(
                        profile["overlay_dir"] / f"{profile['overlay_prefix']}_{vmid}.qcow2"
                    )

        # Kill processes
        qemu_pid = _to_int(session.get("qemu_pid") or session.get("pid"))
        ws_pid = _to_int(session.get("websockify_pid") or session.get("ws_pid"))

        if ws_pid:
            try:
                os.kill(ws_pid, 15)
                logger.info(f"[cleanup_vm] SIGTERM → websockify pid={ws_pid}")
            except ProcessLookupError:
                logger.info(f"[cleanup_vm] websockify pid={ws_pid} already gone")
            except Exception:
                logger.exception(f"[cleanup_vm] failed to SIGTERM websockify pid={ws_pid}")

        if qemu_pid:
            try:
                os.kill(qemu_pid, 15)
                logger.info(f"[cleanup_vm] SIGTERM → qemu pid={qemu_pid}")
            except ProcessLookupError:
                logger.info(f"[cleanup_vm] qemu pid={qemu_pid} already gone")
            except Exception:
                logger.exception(f"[cleanup_vm] failed to SIGTERM qemu pid={qemu_pid}")
        else:
            subprocess.run(["pkill", "-f", vmid], check=False)

        # Remove overlay/ISO files
        for f in files_to_remove:
            try:
                if f and f.exists():
                    f.unlink()
                    logger.info(f"[cleanup_vm] Deleted {f}")
            except Exception:
                logger.exception(f"[cleanup_vm] Failed to delete {f}")

        # Remove sockets
        for sock in (RUN_DIR / f"vnc-{vmid}.sock", RUN_DIR / f"qmp-{vmid}.sock"):
            try:
                if sock.exists():
                    sock.unlink()
                    logger.info(f"[cleanup_vm] Removed socket {sock}")
            except Exception:
                logger.exception(f"[cleanup_vm] Failed to remove socket {sock}")

        # Finally drop from Redis
        try:
            store.delete(vmid)
        except Exception:
            logger.exception(f"[cleanup_vm] store.delete failed for {vmid}")

    except Exception as e:
        logger.exception(f"[cleanup_vm] Error while cleaning up VM {vmid}: {e}")

#legacy code

# def start_websockify(vmid: str, port: int, vnc_unix_sock: str, store) -> subprocess.Popen:
#     """
#     Start websockify for this VM and tail its stdout to react to connects/disconnects.
#     `store` is the Redis-backed SessionStore (used to update last_seen and cleanup).
#     """
#     logger.info(f"[start_websockify] : Started.")
#     static_dir = Path(__file__).parent / "static"

#     cmd = [
#         "websockify",
#         "--web", str(static_dir),
#         "--verbose",
#         f"0.0.0.0:{port}",
#         "--unix-target", vnc_unix_sock,
#     ]

#     proc = subprocess.Popen(
#         cmd,
#         stdout=subprocess.PIPE,
#         stderr=subprocess.STDOUT,
#         text=True,
#     )

#     def monitor_output():
#         try:
#             if not proc.stdout:
#                 return
#             for line in proc.stdout:
#                 line = line.strip()
#                 logger.info(f"[websockify:{vmid}] {line}")

#                 lower = line.lower()
#                 if "client closed connection" in lower:
#                     try:
#                         store.update(vmid, last_seen=str(int(Path().stat().st_mtime_ns // 1_000_000)))
#                     except Exception:
#                         pass
#                     logger.info(f"[websockify:{vmid}] Client disconnected. Clean-up starts.")
#                     cleanup_vm(vmid, store)

#                 elif "connecting to unix socket" in lower or "accepted connection" in lower:
#                     try:
#                         store.update(vmid, last_seen=str(int(Path().stat().st_mtime_ns // 1_000_000)))
#                     except Exception:
#                         pass

#         except Exception:
#             logger.exception(f"[websockify:{vmid}] monitor error")
#         finally:
#             try:
#                 if proc.poll() is not None:
#                     logger.info(f"[websockify:{vmid}] process exited with code {proc.returncode}, cleanup")
#                     cleanup_vm(vmid, store)
#             except Exception:
#                 logger.exception(f"[websockify:{vmid}] finalizer cleanup failed")

#     Thread(target=monitor_output, daemon=True).start()
#     return proc
