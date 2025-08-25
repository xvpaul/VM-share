# /app/routers/vm.py
import secrets, logging, subprocess, json, socket
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from configs.config import server, VM_PROFILES, SNAPSHOTS_PATH
from methods.manager.OverlayManager import QemuOverlayManager, OnlineSnapshotError
from methods.database.database import get_db
from methods.auth.auth import get_current_user
from methods.database.models import User

from methods.manager.SessionManager import get_session_store, SessionStore
from methods.manager import get_websockify_service
from methods.manager.WebsockifyService import WebsockifyService


logger = logging.getLogger(__name__)


router = APIRouter()

class RunScriptRequest(BaseModel):
    os_type: str
    snapshot: str | None = None  # optional, used by /run_snaphot

class SnapshotRequest(BaseModel):
    os_type: str
    vmid: str | None = None  # allow FE to pass vmid; fallback to store if omitted

class RemoveSnapshotRequest(BaseModel):
    snapshot: str | None = None
    os_type: str | None = None   # optional fallbacks
    vmid: str | None = None

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
                "redirect": f"http://{server.SERVER_HOST}:8000/novnc/vnc.html?host={server.SERVER_HOST}&port={existing['http_port']}"
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
            "redirect": f"http://{server.SERVER_HOST}:8000/novnc/vnc.html?host={server.SERVER_HOST}&port={http_port}",
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
                "redirect": f"http://{server.SERVER_HOST}:8000/novnc/vnc.html"
                            f"?host={server.SERVER_HOST}&port={existing['http_port']}"
            })

        # ---- FIXED: build ISO path correctly ----
        prof = VM_PROFILES["custom"]
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
            "redirect": f"http://{server.SERVER_HOST}:8000/novnc/vnc.html"
                        f"?host={server.SERVER_HOST}&port={http_port}",
        })

    except FileNotFoundError as e:
        logger.exception(f"[run_custom_iso] ISO not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"[run_custom_iso] Failed for {user.login}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

def _bytes_to_mb(n: int) -> int:
    # ceil(n / (1024*1024)) without floats
    return (int(n) + (1024*1024 - 1)) // (1024*1024)

def _img_actual_mb(img: Path) -> int:
    """On-disk MiB for qcow/raw (ceil). Prefer qemu-img 'actual-size'."""
    try:
        p = subprocess.run(["qemu-img", "info", "--output=json", str(img)],
                           capture_output=True, text=True)
        if p.returncode == 0 and p.stdout:
            info = json.loads(p.stdout)
            n = int(info.get("actual-size") or info.get("virtual-size") or img.stat().st_size)
        else:
            n = img.stat().st_size
    except Exception:
        n = img.stat().st_size
    return (n + (1024*1024 - 1)) // (1024*1024)

@router.post("/snapshot")
async def create_snapshot(
    request: SnapshotRequest,
    user: User = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
    db: Session = Depends(get_db),
):
    vmid = None
    try:
        os_type = (request.os_type or "").strip()
        if not os_type:
            raise HTTPException(status_code=400, detail="Missing os_type")

        # vmid from client, else from store
        sess = store.get_running_by_user(user.id) or {}
        vmid = (request.vmid or "").strip() or (sess.get("vmid") or "")
        logger.info("[snapshot] request user=%s os_type=%s vmid=%s", user.id, os_type, vmid)
        if not vmid:
            raise HTTPException(status_code=404, detail="No running VM found for this user")

        mgr = QemuOverlayManager(user_id=str(user.id), vmid=vmid, os_type=os_type)

        # VM must be running (create_disk_snapshot uses QMP)
        _, qmp_sock = mgr._socket_paths(vmid)
        logger.info("[snapshot] qmp_sock=%s exists=%s", qmp_sock, qmp_sock.exists())
        if not qmp_sock.exists():
            raise HTTPException(status_code=409, detail="VM is not running (no QMP socket)")

        # -------- Source selection with full logging --------
        from pathlib import Path
        snap_dir = Path(SNAPSHOTS_PATH)
        try:
            logger.info("[snapshot] SNAPSHOTS_PATH=%s exists=%s is_dir=%s",
                        snap_dir, snap_dir.exists(), snap_dir.is_dir())
        except Exception as e:
            logger.warning("[snapshot] SNAPSHOTS_PATH inspect failed: %s", e)

        # Candidate 1 (best): what the VM is actually using right now (set by boot_vm)
        sess_overlay = sess.get("overlay") or ""
        cand_session = Path(sess_overlay) if sess_overlay else None

        # Candidate 2: expected snapshot name for this vmid
        cand_snapshot = snap_dir / f"{user.id}__{os_type}__{vmid}.qcow2"

        # Candidate 3: overlay path by convention (prefix == os_type)
        try:
            cand_overlay = mgr.overlay_path()
        except Exception as e:
            logger.warning("[snapshot] overlay_path() failed: %s", e)
            cand_overlay = None

        candidates = [
            ("session", cand_session),
            ("snapshot", cand_snapshot),
            ("overlay", cand_overlay),
        ]

        chosen = None
        src = None
        for label, path in candidates:
            if not path:
                logger.info("[snapshot] candidate %s: (none)", label)
                continue
            try:
                exists = path.exists()
            except Exception as e:
                logger.info("[snapshot] candidate %s: %s exists=error(%s)", label, path, e)
                continue
            logger.info("[snapshot] candidate %s: %s exists=%s", label, path, exists)
            if exists and path.is_file():
                chosen, src = label, path
                break

        if not src:
            raise HTTPException(
                status_code=409,
                detail=("No source disk image found; tried:\n"
                        f" - session:  {cand_session}\n"
                        f" - snapshot: {cand_snapshot}\n"
                        f" - overlay:  {cand_overlay}")
            )

        logger.info("[snapshot] using %s as billing source: %s", chosen, src)

        # -------- Quota / size accounting --------
        db_user = db.get(User, user.id)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        cap_mb  = int(db_user.snapshot_storage_capacity or 0)
        used_mb = int(db_user.snapshot_stored or 0)

        # Rich size probe for logs
        qimg_fmt = qimg_actual = qimg_virtual = None
        try:
            p = subprocess.run(["qemu-img", "info", "--output=json", str(src)],
                               capture_output=True, text=True)
            if p.returncode == 0 and p.stdout:
                j = json.loads(p.stdout)
                qimg_fmt     = j.get("format")
                qimg_actual  = int(j.get("actual-size")) if j.get("actual-size") is not None else None
                qimg_virtual = int(j.get("virtual-size")) if j.get("virtual-size") is not None else None
        except Exception as e:
            logger.warning("[snapshot] qemu-img info failed for %s: %s", src, e)

        try:
            stat_bytes = src.stat().st_size
        except Exception:
            stat_bytes = None

        bill_mb = _img_actual_mb(src)   # your helper: bill by actual on-disk MiB (ceil)
        new_total = used_mb + bill_mb

        logger.info(
            "[snapshot] size probe src=%s fmt=%s actual=%sB virtual=%sB stat=%sB billed=%sMB used=%sMB cap=%sMB new_total=%sMB",
            src, (qimg_fmt or "?"),
            (qimg_actual if qimg_actual is not None else "n/a"),
            (qimg_virtual if qimg_virtual is not None else "n/a"),
            (stat_bytes if stat_bytes is not None else "n/a"),
            bill_mb, used_mb, cap_mb, new_total
        )

        if new_total > cap_mb:
            deficit = new_total - cap_mb
            logger.warning("[snapshot] quota exceeded user=%s need+%sMB used=%sMB cap=%sMB billed=%sMB src=%s",
                           user.id, deficit, used_mb, cap_mb, bill_mb, src)
            raise HTTPException(
                status_code=413,
                detail=f"Not enough snapshot storage (need +{deficit} MB). "
                       f"Used={used_mb} MB, WouldBe={new_total} MB, Cap={cap_mb} MB."
            )

        # -------- Create the snapshot (QMP drive-backup) --------
        snap_name = f"{user.id}__{os_type}__{vmid}"
        out_path: Path = mgr.create_disk_snapshot(snap_name)

        try:
            out_bytes = out_path.stat().st_size
        except Exception:
            out_bytes = None
        logger.info("[snapshot] created file=%s size_bytes=%s (billed=%sMB)",
                    out_path, (out_bytes if out_bytes is not None else "n/a"), bill_mb)

        # Persist usage
        db_user.snapshot_stored = new_total
        db.commit()

        logger.info("[snapshot] ok user=%s vmid=%s billed_src=%s billed_mb=%s total_mb=%s/%s out=%s",
                    user.id, vmid, src, bill_mb, new_total, cap_mb, out_path)

        return {"status": "ok", "snapshot": out_path.name, "path": str(out_path), "size_mb": bill_mb}

    except HTTPException:
        raise
    except OnlineSnapshotError as e:
        logger.error("[snapshot] failed user=%s vmid=%s error=%s", user.id, vmid, e)
        raise HTTPException(status_code=500, detail=f"Snapshot error: {e}")
    except Exception as e:
        logger.exception("[snapshot] unexpected user=%s vmid=%s", user.id, vmid)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/run_snaphot")
async def run_snapshot(
    request: RunScriptRequest,
    user: User = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
    ws: WebsockifyService = Depends(get_websockify_service),
):
    try:
        user_id = str(user.id)
        os_type = request.os_type
        snap_name = (request.snapshot or "").strip()
        if not snap_name:
            raise HTTPException(status_code=400, detail="Missing snapshot")

        existing = store.get_running_by_user(user_id)
        if existing is not None:
            logger.info(f"[run_snapshot] User {user_id} already has VM {existing['vmid']}")
            return JSONResponse({
                "message": f"VM already running for user {user.login}",
                "vm": existing,
                "redirect": f"http://{server.SERVER_HOST}:8000/novnc/vnc.html?host={server.SERVER_HOST}&port={existing['http_port']}"
            })

        vmid = secrets.token_hex(6)
        logger.info(f"[run_snapshot] Launch from snapshot requested by {user.login} (id={user_id}); vmid={vmid}; snap={snap_name}")

        # Resolve snapshot path (accept absolute or basename)
        snap_path = Path(snap_name)
        if not snap_path.is_absolute():
            snap_path = Path(SNAPSHOTS_PATH) / snap_path.name
        if not snap_path.exists():
            raise HTTPException(status_code=404, detail=f"Snapshot not found: {snap_path}")

        manager = QemuOverlayManager(user_id, vmid, os_type)

        # Boot directly from the snapshot image
        meta = manager.boot_vm(vmid, drive_path=str(snap_path))
        logger.info(f"[run_snapshot] VM booted from snapshot (vmid={vmid})")

        # Target for websockify
        target = meta["vnc_socket"] if "vnc_socket" in meta else f"{meta['vnc_host']}:{meta['vnc_port']}"
        http_port = ws.start(vmid, target)
        logger.info(f"[run_snapshot] Websockify on :{http_port} for VM {vmid}")

        store.set(vmid, {
            **meta,
            "user_id": user_id,
            "http_port": http_port,
            "os_type": os_type,
            "pid": meta['pid'],
        })

        return JSONResponse({
            "message": f"VM for user {user.login} launched from snapshot (vmid={vmid})",
            "vm": {"vmid": vmid, **meta},
            "redirect": f"http://{server.SERVER_HOST}:8000/novnc/vnc.html?host={server.SERVER_HOST}&port={http_port}",
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[run_snapshot] Failed for user {user.login} (id={user.id}): {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/get_user_snapshots")
async def get_user_snapshots(user: User = Depends(get_current_user)):
    try:
        items = []
        for p in SNAPSHOTS_PATH.glob(f"{user.id}__*"):
            if not p.is_file():
                continue
            stat = p.stat()
            stem = p.stem  # name without extension
            parts = stem.split("__", 2)
            os_type = parts[1] if len(parts) > 1 else None
            vmid    = parts[2] if len(parts) > 2 else None
            items.append({
                "name": p.name,  # keep original filename (with extension if any)
                "os_type": os_type,
                "vmid": vmid,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "path": str(p),
            })

        items.sort(key=lambda x: x["modified"], reverse=True)
        logger.info("[snapshots] user=%s count=%d", user.id, len(items))
        return items
    except Exception:
        logger.exception("[snapshots] list failed user=%s", user.id)
        return []
    
@router.post("/remove_snapshot")
async def remove_snapshot(
    request: RemoveSnapshotRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        # Determine filename: prefer explicit `snapshot`, else compose from os_type + vmid
        snap_name = (getattr(request, "snapshot", None) or "").strip()
        if not snap_name:
            os_type = (getattr(request, "os_type", "") or "").strip()
            vmid = (getattr(request, "vmid", "") or "").strip()
            if not (os_type and vmid):
                raise HTTPException(status_code=400, detail="Provide `snapshot` or both `os_type` and `vmid`")
            snap_name = f"{user.id}__{os_type}__{vmid}.qcow2"

        # Always resolve to basename inside snapshots dir (no path traversal)
        snap_path = Path(SNAPSHOTS_PATH) / Path(snap_name).name

        # Load user for quota update
        db_user = db.get(User, user.id)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        freed_mb = 0
        if snap_path.exists():
            try:
                freed_mb = _bytes_to_mb(snap_path.stat().st_size)
            except Exception:
                freed_mb = 0
            try:
                snap_path.unlink()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to remove snapshot file: {e}")
        else:
            return {"status": "ok", "removed": False, "snapshot": snap_path.name, "freed_mb": 0, "total_mb": int(db_user.snapshot_stored or 0)}

        current_mb = int(db_user.snapshot_stored or 0)
        new_total = max(0, current_mb - freed_mb)
        db_user.snapshot_stored = new_total
        db.commit()

        logger.info("[snapshot] removed user=%s file=%s freed=%sMB total=%sMB",
                    user.id, snap_path.name, freed_mb, new_total)

        return {"status": "ok", "removed": True, "snapshot": snap_path.name, "freed_mb": freed_mb, "total_mb": new_total}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[snapshot] remove failed user=%s", user.id)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")