import secrets
import subprocess
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from methods.manager.OverlayManager import QemuOverlayManager
from methods.database.database import get_db
from methods.auth.auth    import get_current_user
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
        subprocess.Popen(
            f"~/noVNC/utils/novnc_proxy --listen localhost:6080 --vnc localhost:{port} --web {web_dir}",
            shell=True
        )

        return JSONResponse({
            "message": f"VM for user {user.login} launched (vmid={vmid})",
            "vm": meta,
            "redirect": f"http://localhost:6080/vnc.html?host=localhost&port={port}"
        })

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr.strip() or str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{vmid}/powerdown")
async def powerdown(vmid: str):
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
