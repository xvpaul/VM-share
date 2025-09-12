# /app/routers/post.py
import logging, html
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from configs.config import VM_PROFILES, MAX_ISO_BYTES, CHUNK_SIZE
from methods.database.database import get_db
from methods.auth.auth import get_current_user
from methods.database.models import User
from methods.manager.SessionManager import get_session_store, SessionStore

from observability.report import telegram_reporting

router = APIRouter()
logger = logging.getLogger(__name__)

async def _save_stream_with_limit(src: UploadFile, dest: Path, max_bytes: int) -> int:
    """Stream-save UploadFile to dest with a hard size cap."""
    logger.info("post.py: [_save_stream_with_limit] Uploading ISO user")
    total = 0
    # ensure clean target file
    if dest.exists():
        dest.unlink()
    with dest.open("wb") as f:
        while True:
            chunk = await src.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                # stop writing and remove partial file
                f.flush()
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large")
            f.write(chunk)
    return total

@router.post("/api/post")
async def send_post(
    user: User = Depends(get_current_user),
    # db: Session = Depends(get_db),
    # store: SessionStore = Depends(get_session_store),
    file: UploadFile = File(...), 
):
    try:
        user_id = str(user.id)
        # derive destination path from vm_profiles["custom"]
        profile = VM_PROFILES.get("custom")
        if not profile or "base_image" not in profile:
            logger.error("post.py: [send_post] Missing 'custom.base_image' in vm_profiles")
            raise HTTPException(status_code=500, detail="Server misconfiguration")

        base_tpl = str(profile["base_image"])
        prefix_tpl = str(profile.get("prefix", "{uid}.iso"))

        # build filename from prefix (defaults to "{uid}.iso")
        try:
            fname = prefix_tpl.format(uid=user_id)
        except Exception:
            # fallback if someone misconfigured the template
            fname = f"{user_id}.iso"

        if not fname.lower().endswith(".iso"):
            fname = f"{fname}.iso"

        # allow: (a) path template containing {uid}, (b) fixed .iso path, (c) directory path
        if "{uid}" in base_tpl:
            iso_dest = Path(base_tpl.format(uid=user_id))
        else:
            p = Path(base_tpl)
            if p.suffix.lower() == ".iso":
                # fixed file path; ignore prefix
                iso_dest = p
            else:
                # treat as directory
                iso_dest = p / fname

        # ensure parent exists
        iso_dest.parent.mkdir(parents=True, exist_ok=True)

        # enforce .iso suffix even if base_tpl had a wrong suffix
        if iso_dest.suffix.lower() != ".iso":
            iso_dest = iso_dest.with_suffix(".iso")


        # log and save
        logger.info(
            "post.py: [send_post] Saving uploaded file for user=%s to %s (orig=%s, ctype=%s)",
            user_id, iso_dest, getattr(file, "filename", None), getattr(file, "content_type", None)
        )

        total_size = await _save_stream_with_limit(file, iso_dest, MAX_ISO_BYTES)

        logger.info(
            "post.py: [send_post] Saved ISO for user=%s path=%s size=%s",
            user_id, iso_dest, total_size
        )

        # respond (no DB write here; you didn’t ask for it)
        return JSONResponse({
            "message": "ISO uploaded",
            "user_id": user_id,
            "iso_path": str(iso_dest),
            "size": total_size,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("post.py: [send_post] Failed to save ISO: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")



@router.post("/feedback")
async def send_post(
    data: dict,
    user: User = Depends(get_current_user),
):
    # Accept either {"message": "..."} or {"text": "..."}
    msg = (data.get("message") or data.get("text") or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message required")

    # Minimal user info (best-effort)
    name = getattr(user, "username", None) or getattr(user, "login", None) or getattr(user, "email", None) or "user"
    uid  = getattr(user, "id", None) or getattr(user, "user_id", None) or ""

    # Escape for Telegram HTML
    safe_name = html.escape(str(name))
    safe_uid  = html.escape(str(uid))
    safe_msg  = html.escape(msg)

    telegram_reporting(
        f"<b>Feedback</b>\n<b>User:</b> {safe_name} (id: {safe_uid})\n\n{safe_msg}"
    )

    return {"ok": True}