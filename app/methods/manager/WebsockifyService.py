# /app/methods/manager/WebsockifyService.py
import os
import shlex
import subprocess
from typing import Optional
from utils import find_free_port
from .ProcessManager import ProcRegistry

class WebsockifyService:
    """
    Starts/stops a websockify process to bridge a VM's VNC endpoint to a local TCP port.
    Target can be a unix socket (e.g. /tmp/vm-<id>.sock) or host:port.
    """
    def __init__(self, registry: ProcRegistry) -> None:
        self._registry = registry
        self._bin = os.environ.get("WEBSOCKIFY_BIN", "websockify")

    def start(self, vmid: str, target: str, port: Optional[int] = None) -> int:
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
        return port

    def stop(self, vmid: str) -> None:
        self._registry.stop(f"ws:{vmid}")
