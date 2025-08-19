# /app/routers/sessions.py
from fastapi import APIRouter, Depends, Query
from typing import List, Dict
from methods.auth.auth import get_current_user
from methods.database.models import User
from methods.manager.SessionManager import get_session_store

router = APIRouter(prefix="/api", tags=["sessions"])

EXPOSE_FIELDS = {"vmid","user_id","os_type","state","http_port","created_at","last_seen"}

# @router.get("/sessions/active")
# def my_active_sessions(
#     limit: int = Query(100, ge=1, le=1000),
#     user: User = Depends(get_current_user),
#     store = Depends(get_session_store),
# ) -> List[Dict]:
#     """
#     Return active sessions for the authenticated user.
#     """
#     items = store.items()  # [(vmid, dict), ...] from Redis
#     out = []
#     uid = str(user.id)
#     for vmid, sess in items:
#         if sess.get("user_id") != uid:
#             continue
#         row = {"vmid": vmid}
#         for k in EXPOSE_FIELDS:
#             if k == "vmid":  
#                 continue
#             if k in sess:
#                 row[k] = sess[k]
#         out.append(row)
#         if len(out) >= limit:
#             break
#     return out


@router.get("/sessions/active")
def active_sessions(
    limit: int = Query(100, ge=1, le=1000),
    user_id: str | None = Query(None, description="Filter by user id"),
    store = Depends(get_session_store),
) -> List[Dict]:
    """
    Public: list active sessions (optionally filter by ?user_id=...).
    Drops auth; only returns fields in EXPOSE_FIELDS.
    """
    # sort by created_at desc if available
    def _created_at(item):
        _, sess = item
        try:
            return int(sess.get("created_at", "0"))
        except Exception:
            return 0

    items = sorted(store.items(), key=_created_at, reverse=True)

    out: List[Dict] = []
    for vmid, sess in items:
        if user_id is not None and sess.get("user_id") != user_id:
            continue
        row = {"vmid": vmid}
        for k in EXPOSE_FIELDS:
            if k == "vmid":
                continue
            if k in sess:
                row[k] = sess[k]
        out.append(row)
        if len(out) >= limit:
            break
    return out
