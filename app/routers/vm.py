#VM_share/app/routers/vm.py
import secrets
import subprocess
import logging
import os
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from configs import server_config
from methods.manager.OverlayManager import QemuOverlayManager
from methods.database.database import get_db
from methods.auth.auth import Authentification, get_current_user
from methods.database.models import User
from utils import find_free_port, start_websockify
import configs.log_config as logs


"""
Logging configuration 
"""

log_file_path = os.path.join(logs.LOG_DIR, logs.LOG_NAME)

try:
    os.makedirs(logs.LOG_DIR, exist_ok=True)
    logging.basicConfig(
        filename=log_file_path,
        level=logging.INFO,
        format='%(asctime)s.%(msecs)05d %(message)s',
        datefmt='%Y-%m-%d %H-%M-%S',
    )

except Exception as e:
    print(f'Error: {e}')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s.%(msecs)05d %(message)s',
        datefmt='%Y-%m-%d %H-%M-%S',
    )
    logging.error(f"Failed to initialize file logging: {e}")


router = APIRouter()
SESSIONS: Dict[str, dict] = {}
WEBSOCKIFY_PROCS: Dict[str, subprocess.Popen] = {}

@router.post("/run-script")
async def run_vm_script(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = str(user.id)
        vmid = secrets.token_hex(6)
        for existing_vmid, session in SESSIONS.items():
            if session["user_id"] == user_id:
                logging.info(f"User {user_id} already has VM {existing_vmid}, returning existing session")
                return JSONResponse({
                    "message": f"VM already running for user {user.login}",
                    "vm": session,
                    "redirect": f"http://{server_config.SERVER_HOST}:6080/vnc.html?host={server_config.SERVER_HOST}&port={session['http_port']}"
                })
        logging.info(f"VM_share/app/routers/vm.py: [run_vm_script] Requested by user '{user.login}' (id={user_id})")
        logging.info(f"VM_share/app/routers/vm.py: Generated VMID: {vmid}")

        manager = QemuOverlayManager(user_id)
        overlay_path = manager.create_overlay()
        logging.info(f"VM_share/app/routers/vm.py: Overlay ready at {overlay_path}")

        meta = manager.boot_vm(vmid)
        logging.info(f"VM_share/app/routers/vm.py: VM booted for user {user.login} (vmid={vmid})")

        port = find_free_port()
        proc = start_websockify(port, meta["vnc_socket"])
        logging.info(f"VM_share/app/routers/vm.py: Websockify started on port {port} for VM {vmid}")

        SESSIONS[vmid] = {**meta, "http_port": port}
        WEBSOCKIFY_PROCS[vmid] = proc

        web_dir = (Path(__file__).parent.parent / "static" / "novnc-ui").resolve()
        novnc_proxy = Path.home() / "noVNC/utils/novnc_proxy"

        subprocess.Popen(
            f"{novnc_proxy} --listen 0.0.0.0:6080 --vnc localhost:{port} --web {web_dir}",
            shell=True
        )
        logging.info(f"VM_share/app/routers/vm.py: noVNC proxy started for VM {vmid} on port 6080")

        response = {
            "message": f"VM for user {user.login} launched (vmid={vmid})",
            "vm": meta,
            "redirect": f"http://{server_config.SERVER_HOST}:6080/vnc.html?host={server_config.SERVER_HOST}&port={port}"
        }
        logging.info(f"VM_share/app/routers/vm.py: VM launch complete: {response['message']}")

        return JSONResponse(response)

    except Exception as e:
        logging.exception(f"VM_share/app/routers/vm.py: Failed to launch VM for user {user.login} (id={user.id}): {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
