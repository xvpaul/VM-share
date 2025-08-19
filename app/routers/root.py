# /app/routers/root.py
from fastapi import APIRouter, Depends
import time
from fastapi.responses import FileResponse
from methods.manager.SessionManager import get_session_store

router = APIRouter()

@router.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse("static/index.html")

@router.get("/debug/redis")
def debug_redis(store = Depends(get_session_store)):
    vmid = "test-" + str(int(time.time()))
    store.set(vmid, {"user_id":"u1","state":"running","created_at":str(int(time.time()*1000))})
    got = store.get_running_by_user("u1")
    store.update(vmid, state="stopped")
    store.delete(vmid)
    return {"ok": bool(got), "vmid": vmid}