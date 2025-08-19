# /app/main.py
from contextlib import asynccontextmanager
import os, asyncio, logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers.root import router as root_router
from routers.vm   import router as vm_router
from routers.auth import router as auth_router
from routers.sessions import router as sessions_router

from methods.manager.SessionManager import get_session_store
from utils import cleanup_vm 

# --- observability imports ---
from observability.metrics import router as metrics_router, metrics_collector
from observability.utils_observability import resource_watchdog


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- STARTUP ----
    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(metrics_collector(get_session_store, stop_event, interval_sec=15)),
        asyncio.create_task(resource_watchdog(stop_event)),
    ]
    try:
        yield
    finally:
        logging.info("main.py: lifespan shutdown → stopping background tasks")
        stop_event.set()
        for t in tasks:
            try:
                await asyncio.wait_for(t, timeout=5)
            except asyncio.TimeoutError:
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        logging.info("main.py: lifespan shutdown → beginning cleanup")
        store = get_session_store()

        try:
            sessions = store.items()            # returns List[(vmid, data)]
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
app.include_router(metrics_router)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/novnc", StaticFiles(directory="static/novnc-ui", html=True), name="novnc")
