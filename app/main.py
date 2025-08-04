# main.py
import time
import socket
import secrets
import subprocess
import os
import configs  
import methods.auth as auth
from sqlalchemy.orm import Session
from methods.database.database import get_db
from methods.database.models import User
from methods.database.database import SessionLocal
from pathlib import Path
from typing import Dict
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from methods.manager.OverlayManager import QemuOverlayManager
from methods.auth.auth import Authentification
from methods.auth.auth import get_current_user



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
async def run_vm_script(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = str(user.id)
        vmid = secrets.token_hex(6)

        manager = QemuOverlayManager(user_id)
        manager.create_overlay()
        meta = manager.boot_vm(vmid)

        port = find_free_port()
        proc = start_websockify(port, meta["vnc_socket"])

        SESSIONS[vmid] = {**meta, "http_port": port}
        WEBSOCKIFY_PROCS[vmid] = proc

        web_dir = (Path(__file__).parent.parent / "app" / "static" / "novnc-ui").resolve()
        # web_dir = (Path(__file__).parent.parent / "static" / "novnc-ui").resolve()
        print(web_dir)
        command = f"~/noVNC/utils/novnc_proxy --listen localhost:6080 --vnc localhost:{port} --web {web_dir}"
        subprocess.Popen(command, shell=True)

        print(f"[INFO] VNC WebSocket running at: localhost:{port}")
        print(f"[INFO] Serving UI from: {web_dir}")

        return JSONResponse({
            "message": f"VM for user {user.login} launched (vmid={vmid})",
            "vm": meta,
            "redirect": f"http://localhost:6080/vnc.html?host=localhost&port={port}"
        })

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



@app.post("/register")
async def register_user(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    login = body.get("login")
    password = body.get("password")

    if not login or not password:
        raise HTTPException(status_code=400, detail="Missing login or password")

    existing_user = db.query(User).filter(User.login == login).first()

    #User exists → try to authenticate
    if existing_user:
        if Authentification.verify_password(password, existing_user.hashed_password):
            token = Authentification.create_access_token({"sub": existing_user.login})
            return {
                "message": "Logged in",
                "id": existing_user.id,
                "access_token": token,
                "token_type": "bearer"
            }
        else:
            raise HTTPException(status_code=401, detail="User already exists, wrong password")

    #New user → register and login
    hashed_pw = Authentification.hash_password(password)
    new_user = User(login=login, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = Authentification.create_access_token({"sub": new_user.login})

    return {
        "message": "User registered",
        "id": new_user.id,
        "access_token": token,
        "token_type": "bearer"
    }

@app.post("/token")
def login_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    auth = Authentification(form_data.username, form_data.password)
    user = auth.authenticate_user(db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth.create_access_token({"sub": user.login})
    return {"access_token": token, "token_type": "bearer"}

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