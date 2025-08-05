import secrets
import subprocess
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

router = APIRouter()
SESSIONS: Dict[str, dict] = {}
WEBSOCKIFY_PROCS: Dict[str, subprocess.Popen] = {}

@router.post("/run-script")
async def run_vm_script(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        print("🚀 [run_vm_script] got user:", user)
        user_id = str(user.id)
        vmid = secrets.token_hex(6)

        manager = QemuOverlayManager(user_id)
        manager.create_overlay()
        meta = manager.boot_vm(vmid)

        port = find_free_port()
        proc = start_websockify(port, meta["vnc_socket"])

        SESSIONS[vmid] = {**meta, "http_port": port}
        WEBSOCKIFY_PROCS[vmid] = proc

        web_dir = (Path(__file__).parent.parent / "static" / "novnc-ui").resolve()
        novnc_proxy = Path.home() / "noVNC/utils/novnc_proxy"

        subprocess.Popen(
            f"{novnc_proxy} --listen localhost:6080 --vnc localhost:{port} --web {web_dir}",
            shell=True
        )

        return JSONResponse({
            "message": f"VM for user {user.login} launched (vmid={vmid})",
            "vm": meta,
            "redirect": f"http://{server_config.SERVER_HOST}:6080/vnc.html?host={server_config.SERVER_HOST}&port={port}"
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
