# /app/main.py
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers.root import router as root_router
from routers.vm   import router as vm_router
from routers.auth import router as auth_router

from methods.manager.SessionManager import get_session_store
from methods.manager import get_websockify_service
from methods.manager.ProcessManager import get_proc_registry
from methods.manager.WebsockifyService import WebsockifyService
from utils import cleanup_vm 

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logging.info("main.py: lifespan shutdown → beginning cleanup")

    store = get_session_store()
    ws: WebsockifyService = get_websockify_service()

    try:
        all_sessions = list(store._b.items())  
        logging.info(f"main.py: found {len(all_sessions)} sessions to clean")
    except Exception:
        all_sessions = []
        logging.exception("main.py: failed to enumerate sessions")

    for vmid, sess in all_sessions:
        try:
            logging.info(f"main.py: stopping VM {vmid}")
            ws.stop(vmid)
        except Exception:
            logging.exception(f"main.py: websockify stop failed for {vmid}")

        try:
            cleanup_vm(vmid, store) 
        except Exception:
            logging.exception(f"main.py: cleanup_vm failed for {vmid}")

        try:
            store.delete(vmid)
        except Exception:
            logging.exception(f"main.py: store.delete failed for {vmid}")

    try:
        get_proc_registry().stop_all()
    except Exception:
        logging.exception("main.py: proc_registry stop_all failed")

app = FastAPI(lifespan=lifespan)

app.include_router(root_router)
app.include_router(vm_router, prefix="/api", tags=["vm"])
app.include_router(auth_router, tags=["auth"])

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/novnc", StaticFiles(directory="static/novnc-ui", html=True), name="novnc")
