# main.py
import time
import socket
import secrets
import subprocess
from pathlib import Path
from typing import Dict
from pathlib import Path
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from methods.vm import QemuOverlayManager
import configs  

app = FastAPI()

@app.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")

SESSIONS: Dict[str, dict] = {}           
WEBSOCKIFY_PROCS: Dict[str, subprocess.Popen] = {}  


def find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_websockify(port: int, vnc_unix_sock: str) -> subprocess.Popen:
    """
    Bridge the QEMU UNIX VNC socket to TCP/WebSocket and serve /static on the same port.
    Requires websockify to be installed and in PATH.
    """
    static_dir = Path(__file__).parent / "static"
    cmd = [
        "websockify",
        "--web", str(static_dir),        
        f"0.0.0.0:{port}",               
        "--unix-target", vnc_unix_sock,   
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

@app.post("/api/run-script")
async def run_vm_script(request: Request):
    """
    Launch a VM for this user, expose VNC via websockify via noVNC, and redirect to custom UI.
    """
    try:
        # Create unique VM ID and session ID
        user_id = str(int(time.time()))
        vmid = secrets.token_hex(6)

        # Prepare and boot VM
        manager = QemuOverlayManager(user_id)
        manager.create_overlay()
        meta = manager.boot_vm(vmid)

        # Find an available local port and start websockify
        port = find_free_port()
        proc = start_websockify(port, meta["vnc_socket"])

        # Track session and process
        SESSIONS[vmid] = {**meta, "http_port": port}
        WEBSOCKIFY_PROCS[vmid] = proc

        # Resolve path to custom UI directory
        web_dir = (Path(__file__).parent.parent / "static" / "novnc-ui").resolve()

        # Start noVNC proxy (pointing to your custom web interface)
        command = f"~/noVNC/utils/novnc_proxy --listen localhost:6080 --vnc localhost:{port} --web /Users/soledaco/Desktop/pet/VM_share/app/static/novnc-ui"
        subprocess.Popen(command, shell=True)

        print(f"[INFO] VNC WebSocket running at: localhost:{port}")
        print(f"[INFO] Serving UI from: {web_dir}")

        # Redirect to your custom UI page (alpine.html)
        return JSONResponse({
            "message": f"VM {user_id} launched (vmid={vmid})",
            "vm": meta,
            "redirect": f"http://localhost:6080/vnc.html?host=localhost&port={port}"
        })

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr.strip() or str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr.strip() or str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vm/{vmid}/powerdown")
async def powerdown(vmid: str):
    """
    Graceful ACPI shutdown via QMP, then stop the websockify bridge.
    """
    session = SESSIONS.get(vmid)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown vmid")

    manager = QemuOverlayManager(session["user_id"])
    ok = manager.powerdown(vmid)

    proc = WEBSOCKIFY_PROCS.pop(vmid, None)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    return JSONResponse({"ok": bool(ok)})


"""
 print(port)
        web_dir = Path(__file__).parent / "static" / "novnc-ui"
        command = [
        "~/noVNC/utils/novnc_proxy",
        "--listen", f'localhost:6080',
        "--vnc", f'localhost:{port}',
        "--web", str(web_dir)
            ]
        subprocess.Popen(
            command,
            shell=True
        )
"""