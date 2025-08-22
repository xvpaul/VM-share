# /app/methods/manager/WebsockifyService.py
import logging
import os
import shlex
import subprocess
from pathlib import Path
from threading import Thread
from typing import Optional, Any

from utils import find_free_port, cleanup_vm
from .ProcessManager import ProcRegistry


class WebsockifyService:
    """
    Starts/stops a websockify process to bridge a VM's VNC endpoint to a local TCP port.
    Target can be a unix socket (e.g. /tmp/vm-<id>.sock) or host:port.
    Monitors stdout to detect connects/disconnects and trigger cleanup.
    """

    def __init__(self, registry: ProcRegistry) -> None:
        self._registry = registry
        self._bin = os.environ.get("WEBSOCKIFY_BIN", "websockify")

        # Allow overriding where the static files live (for --web).
        # Fallback tries ../../static relative to this file: /app/static
        static_env = os.environ.get("WEBSOCKIFY_WEB_DIR")
        if static_env:
            self._static_dir = Path(static_env)
        else:
            # .../methods/manager/WebsockifyService.py -> /app/static
            self._static_dir = Path(__file__).resolve().parents[2] / "static"

    def start(self, vmid: str, target: str, port: Optional[int] = None, store: Optional[Any] = None) -> int:
        """
        Start websockify for this VM and tail its stdout to react to connects/disconnects.
        Returns the public TCP port that websockify listens on.

        Args:
            vmid: VM identifier (used in logs/registry keys).
            target: Either a unix socket path ("/tmp/vm-<id>.sock") or "host:port".
            port: Optional explicit public TCP port. If None, a free port is chosen.
            store: Optional Redis-backed SessionStore with `update(vmid, last_seen=...)`.
        """
        if port is None:
            port = find_free_port()

        # Build argv (no shell) + normalize target form websockify expects.
        argv = [
            self._bin,
            "--web", str(self._static_dir),
            "--verbose",
            f"0.0.0.0:{port}",
        ]

        if target.startswith("/"):
            argv += ["--unix-target", target]
        else:
            # host:port -> pass as-is; quote only if we ever go through shell (we don't).
            argv.append(target)

        logging.info(f"[WebsockifyService.start:{vmid}] launching: {' '.join(shlex.quote(a) for a in argv)}")

        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Register before we spin up the monitor, so stop() can find it immediately
        self._registry.set(f"ws:{vmid}", proc)

        def _monitor_output() -> None:
            try:
                if not proc.stdout:
                    return

                for raw in proc.stdout:
                    line = raw.strip()
                    logging.info(f"[websockify:{vmid}] {line}")
                    lower = line.lower()

                    # Heuristics based on typical websockify logs
                    if "client closed connection" in lower:
                        # Best-effort: bump last_seen
                        try:
                            # Keep your original pattern: use fs mtime in ms
                            last_seen_ms = int(Path().stat().st_mtime_ns // 1_000_000)
                            if store is not None:
                                store.update(vmid, last_seen=str(last_seen_ms))
                        except Exception:
                            pass

                        logging.info(f"[websockify:{vmid}] Client disconnected. Clean-up starts.")
                        try:
                            cleanup_vm(vmid, store)
                        except Exception:
                            logging.exception(f"[websockify:{vmid}] cleanup_vm failed after disconnect")

                    elif ("connecting to unix socket" in lower) or ("accepted connection" in lower):
                        # Connection established/attempted -> update last_seen
                        try:
                            last_seen_ms = int(Path().stat().st_mtime_ns // 1_000_000)
                            if store is not None:
                                store.update(vmid, last_seen=str(last_seen_ms))
                        except Exception:
                            pass

            except Exception:
                logging.exception(f"[websockify:{vmid}] monitor error")
            finally:
                try:
                    # If process exited, ensure cleanup
                    if proc.poll() is not None:
                        logging.info(f"[websockify:{vmid}] process exited with code {proc.returncode}, cleanup")
                        try:
                            cleanup_vm(vmid, store)
                        except Exception:
                            logging.exception(f"[websockify:{vmid}] finalizer cleanup failed")
                except Exception:
                    logging.exception(f"[websockify:{vmid}] finalizer state check failed")

        Thread(target=_monitor_output, daemon=True).start()
        return port

    def stop(self, vmid: str) -> None:
        self._registry.stop(f"ws:{vmid}")
