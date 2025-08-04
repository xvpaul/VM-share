import socket
import subprocess
from pathlib import Path

def find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def start_websockify(port: int, vnc_unix_sock: str) -> subprocess.Popen:
    """
    Bridge the QEMU UNIX VNC socket to TCP/WebSocket and serve /static on the same port.
    Requires `websockify` in PATH.
    """
    static_dir = Path(__file__).parent / "static"
    cmd = [
        "websockify",
        "--web", str(static_dir),
        f"0.0.0.0:{port}",
        "--unix-target", vnc_unix_sock,
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
