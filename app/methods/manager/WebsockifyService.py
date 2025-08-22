# /app/methods/manager/WebsockifyService.py
import os
import shlex
import subprocess
from typing import Optional
from utils import find_free_port, cleanup_vm
import logging
from threading import Thread
from .ProcessManager import ProcRegistry

class WebsockifyService:
    """
    Starts/stops a websockify process to bridge a VM's VNC endpoint to a local TCP port.
    Target can be a unix socket (e.g. /tmp/vm-<id>.sock) or host:port.
    """
    def __init__(self, registry: ProcRegistry) -> None:
        self._registry = registry
        self._bin = os.environ.get("WEBSOCKIFY_BIN", "websockify")

    def start(self, vmid: str, target: str, port: int, store) -> int:
        """
        Returns the public TCP port that websockify listens on.
        """
        if port is None:
            port = find_free_port()

        if target.startswith("/"):
            # unix socket
            cmd = f"{self._bin} {port} --unix-target {shlex.quote(target)}"
        else:
            # host:port
            cmd = f"{self._bin} {port} {shlex.quote(target)}"

        proc = subprocess.Popen(cmd, shell=True)
        self._registry.set(f"ws:{vmid}", proc)
        def monitor_output():
            try:
                if not proc.stdout:
                    return
                for line in proc.stdout:
                    line = line.strip()
                    logging.info(f"[websockify:{vmid}] {line}")

                    lower = line.lower()
                    if "client closed connection" in lower:
                        try:
                            store.update(vmid, last_seen=str(int(Path().stat().st_mtime_ns // 1_000_000)))
                        except Exception:
                            pass
                        logging.info(f"[websockify:{vmid}] Client disconnected. Clean-up starts.")
                        cleanup_vm(vmid, store)

                    elif "connecting to unix socket" in lower or "accepted connection" in lower:
                        try:
                            store.update(vmid, last_seen=str(int(Path().stat().st_mtime_ns // 1_000_000)))
                        except Exception:
                            pass

            except Exception:
                logging.exception(f"[websockify:{vmid}] monitor error")
            finally:
                try:
                    if proc.poll() is not None:
                        logging.info(f"[websockify:{vmid}] process exited with code {proc.returncode}, cleanup")
                        cleanup_vm(vmid, store)
                except Exception:
                    logging.exception(f"[websockify:{vmid}] finalizer cleanup failed")

        Thread(target=monitor_output, daemon=True).start()
        return port

    def stop(self, vmid: str) -> None:
        self._registry.stop(f"ws:{vmid}")
