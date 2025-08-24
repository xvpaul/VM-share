# /app/routers/vm.py
import secrets, logging, os
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from configs import server_config, vm_profiles
from methods.manager.OverlayManager import QemuOverlayManager, OnlineSnapshotError
from methods.database.database import get_db
from methods.auth.auth import get_current_user
from methods.database.models import User

from methods.manager.SessionManager import get_session_store, SessionStore
from methods.manager import get_websockify_service
from methods.manager.WebsockifyService import WebsockifyService

import configs.log_config as logs

logger = logging.getLogger(__name__)


router = APIRouter()

class RunScriptRequest(BaseModel):
    os_type: str

@router.post("/run-script")
async def run_vm_script(
    request: RunScriptRequest,
    user: User = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
    ws: WebsockifyService = Depends(get_websockify_service),
):
    try:
        user_id = str(user.id)
        vmid = secrets.token_hex(6)
        os_type = request.os_type
        # todo group-policy
        existing = store.get_running_by_user(user_id)
        # print(existing)
        if existing is not None:
            logger.info(f"[run_vm_script] User {user_id} already has VM {existing['vmid']}")
            return JSONResponse({
                "message": f"VM already running for user {user.login}",
                "vm": existing,
                "redirect": f"http://{server_config.SERVER_HOST}:8000/novnc/vnc.html?host={server_config.SERVER_HOST}&port={existing['http_port']}"
            })

        logger.info(f"[run_vm_script] Launch requested by {user.login} (id={user_id}); vmid={vmid}")

        manager = QemuOverlayManager(user_id, vmid, os_type)
        overlay_path = manager.create_overlay()
        logger.info(f"[run_vm_script] Overlay ready at {overlay_path}")

        meta = manager.boot_vm(vmid)  # should return at least {"vnc_socket": "..."} or {"vnc_host": "...", "vnc_port": ...}
        logger.info(f"[run_vm_script] VM booted (vmid={vmid})")

        # Pick target for websockify based on meta format
        if "vnc_socket" in meta:
            target = meta["vnc_socket"]                    # unix socket path
        else:
            target = f"{meta['vnc_host']}:{meta['vnc_port']}"  # host:port

        http_port = ws.start(vmid, target)  # starts websockify; returns public port
        logger.info(f"[run_vm_script] Websockify on :{http_port} for VM {vmid}")

        store.set(vmid, {
            **meta,
            "user_id": user_id,
            "http_port": http_port,
            "os_type": os_type,
            #!!! PID additition !!!
            "pid": meta['pid']
        })

        response = {
            "message": f"VM for user {user.login} launched (vmid={vmid})",
            "vm": {"vmid": vmid, **meta},
            "redirect": f"http://{server_config.SERVER_HOST}:8000/novnc/vnc.html?host={server_config.SERVER_HOST}&port={http_port}",
        }
        return JSONResponse(response)

    except Exception as e:
        logger.exception(f"[run_vm_script] Failed for user {user.login} (id={user.id}): {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/run-iso")
async def run_custom_iso(
    user: User = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
    ws: WebsockifyService = Depends(get_websockify_service),
):
    try:
        user_id = str(user.id)
        vmid = secrets.token_hex(6)

        # one VM per user
        existing = store.get_running_by_user(user_id)
        if existing:
            return JSONResponse({
                "message": f"VM already running for user {user.login}",
                "vm": existing,
                "redirect": f"http://{server_config.SERVER_HOST}:8000/novnc/vnc.html"
                            f"?host={server_config.SERVER_HOST}&port={existing['http_port']}"
            })

        # ---- FIXED: build ISO path correctly ----
        prof = vm_profiles.VM_PROFILES["custom"]
        base = Path(prof["base_image"])            # may be dir, file, or template with {uid}
        prefix = str(prof.get("prefix", "{uid}.iso"))

        if "{uid}" in str(base):
            iso_path = Path(str(base).format(uid=user_id))
        elif base.suffix.lower() == ".iso":
            iso_path = base
        else:
            # treat as directory + prefix-based filename
            name = prefix.format(uid=user_id)
            if not name.lower().endswith(".iso"):
                name += ".iso"
            iso_path = base / name

        iso_path = iso_path.expanduser()

        # Validate: must exist, be a file, and not be trivially small
        if not iso_path.exists():
            raise FileNotFoundError(f"No ISO found at {iso_path}")
        if iso_path.is_dir():
            raise FileNotFoundError(f"Expected an ISO file but got a directory: {iso_path}")

        size = iso_path.stat().st_size
        MIN_BYTES = 1 * 1024 * 1024  # 1 MiB safety floor; adjust to your policy
        if size < MIN_BYTES:
            raise RuntimeError(f"ISO too small ({size} bytes): {iso_path}")

        iso_abs = str(iso_path.resolve(strict=True))
        logger.info(f"[run_custom_iso] Launching custom ISO for {user.login} (vmid={vmid}) at {iso_abs} (size={size} bytes)")

        # Launch without overlays
        manager = QemuOverlayManager(user_id, vmid, "custom")
        meta = manager.boot_from_iso(vmid=vmid, iso_path=iso_abs)

        target = meta.get("vnc_socket") or f"{meta['vnc_host']}:{meta['vnc_port']}"
        http_port = ws.start(vmid, target)

        store.set(vmid, {**meta, "user_id": user_id, "http_port": http_port, "os_type": "custom", "pid": meta["pid"]})

        return JSONResponse({
            "message": f"Custom ISO VM for {user.login} launched (vmid={vmid})",
            "vm": {"vmid": vmid, **meta},
            "redirect": f"http://{server_config.SERVER_HOST}:8000/novnc/vnc.html"
                        f"?host={server_config.SERVER_HOST}&port={http_port}",
        })

    except FileNotFoundError as e:
        logger.exception(f"[run_custom_iso] ISO not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"[run_custom_iso] Failed for {user.login}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/snapshot")
async def create_snapshot(
    request: RunScriptRequest,
    user: User = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
):
    """
    Create a disk-only snapshot of a running VM's overlay.
    Snapshot name: {os_type}__{vmid}__{user_id}
    """
    vmid = None
    logger.info("[snapshot] started")
    try:
        # Validate input
        os_type = getattr(request, "os_type", None)
        if not os_type:
            raise HTTPException(status_code=400, detail="Missing os_type in request")

        session = store.get_running_by_user(user.id)
        if not session:
            raise HTTPException(status_code=404, detail=f"No active VM found for user {user.id}")

        vmid = session.get("vmid")
        if not vmid:
            raise HTTPException(status_code=500, detail="Session missing vmid")

        # Build snapshot name
        snapshot_name = f"{os_type}__{vmid}__{user.id}"

        # Perform snapshot
        mgr = QemuOverlayManager(user_id=user.id, vmid=vmid, os_type=os_type)
        mgr.create_disk_snapshot(snapshot_name)

        logger.info(
            "[snapshot] success user=%s vmid=%s snapshot=%s",
            user.id, vmid, snapshot_name
        )
        return {"status": "ok", "snapshot": snapshot_name}

    except FileNotFoundError as e:
        logger.error("[snapshot] overlay not found user=%s vmid=%s error=%s", user.id, vmid, e)
        raise HTTPException(status_code=404, detail=f"Overlay not found: {e}")

    except OnlineSnapshotError as e:
        logger.error("[snapshot] failed user=%s vmid=%s error=%s", user.id, vmid, e)
        raise HTTPException(status_code=500, detail=f"Snapshot error: {e}")

    except HTTPException:
        # Re-raise clean FastAPI errors
        raise

    except Exception as e:
        logger.exception("[snapshot] unexpected user=%s vmid=%s", user.id, vmid)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/run_snaphot")
async def run_snapshot(
    request: RunScriptRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
    ws: WebsockifyService = Depends(get_websockify_service),
): ...
