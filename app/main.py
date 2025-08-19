# /app/main.py
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers.root import router as root_router
from routers.vm   import router as vm_router
from routers.auth import router as auth_router
from routers.sessions import router as sessions_router

from methods.manager.SessionManager import get_session_store
from utils import cleanup_vm 

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logging.info("main.py: lifespan shutdown → beginning cleanup")
    store = get_session_store()

    try:
        sessions = store.items()            # ← returns List[(vmid, data)]
        logging.info(f"main.py: found {len(sessions)} sessions to clean")
    except Exception:
        sessions = []
        logging.exception("main.py: failed to enumerate sessions")

    for vmid, _ in sessions:
        try:
            cleanup_vm(vmid, store)       
        except Exception:
            logging.exception(f"cleanup_vm failed for {vmid}")
        try:
            store.delete(vmid)              
        except Exception:
            logging.exception(f"store.delete failed for {vmid}")

app = FastAPI(lifespan=lifespan)

app.include_router(root_router)
app.include_router(vm_router, prefix="/api", tags=["vm"])
app.include_router(auth_router, tags=["auth"])
app.include_router(sessions_router)


app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/novnc", StaticFiles(directory="static/novnc-ui", html=True), name="novnc")
