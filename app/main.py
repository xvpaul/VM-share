# /app/main.py
from contextlib import asynccontextmanager
import os, asyncio, logging
from pathlib import Path
import configs.config as logs

logger = logging.getLogger(__name__)



# ---- load .env FIRST (before importing modules that read env) ----
from dotenv import load_dotenv
ENV_PATH = (Path(__file__).parent / "configs" / ".env").resolve()
load_dotenv(ENV_PATH)
logging.info("main.py: loaded .env from %s (exists=%s)", ENV_PATH, ENV_PATH.exists())

# ---- multiprocess dir guard BEFORE importing metrics module ----
mp = os.getenv("PROMETHEUS_MULTIPROC_DIR")
if mp:
    os.makedirs(mp, exist_ok=True)
    for f in os.listdir(mp):
        try:
            os.remove(os.path.join(mp, f))
        except Exception:
            pass

# ---- now import the rest ----
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers.root import router as root_router
from routers.vm   import router as vm_router
from routers.auth import router as auth_router
from routers.sessions import router as sessions_router
from routers.pages import router as pages_router
from routers.post import router as post_router

from observability.grafana_proxy import router as grafana_router

# unified metrics (HTTP middleware + registry + collector)
from observability.metrics import (
    router as metrics_router,
    metrics_collector,
    install_http_metrics,
    should_run_samplers,
)

from observability.db_metrics import init_db_metrics
from observability.utils_observability import resource_watchdog

from methods.manager.SessionManager import get_session_store
from utils import cleanup_vm

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    tasks = []

    if should_run_samplers():
        tasks.append(asyncio.create_task(metrics_collector(get_session_store, stop_event, interval_sec=15)))
        tasks.append(asyncio.create_task(resource_watchdog(stop_event)))

    try:
        yield
    finally:
        logger.info("main.py: lifespan shutdown → stopping background tasks")
        stop_event.set()
        for t in tasks:
            try:
                await asyncio.wait_for(t, timeout=5)
            except asyncio.TimeoutError:
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("main.py: lifespan shutdown → beginning cleanup")
        store = get_session_store()
        try:
            sessions = store.items()
            logger.info("main.py: found %d sessions to clean", len(sessions))
        except Exception:
            sessions = []
            logger.exception("main.py: failed to enumerate sessions")

        for vmid, _ in sessions:
            try:
                cleanup_vm(vmid, store)
            except Exception:
                logger.exception("cleanup_vm failed for %s", vmid)
            try:
                store.delete(vmid)
            except Exception:
                logger.exception("store.delete failed for %s", vmid)

app = FastAPI(lifespan=lifespan)

# ---- HTTP metrics middleware ----
install_http_metrics(app)

# ---- DB metrics ----
try:
    from methods.database.database import engine
except Exception:
    from methods.database.database import SessionLocal
    with SessionLocal() as db:
        engine = db.get_bind()
init_db_metrics(engine)

# ---- Routers ----
app.include_router(root_router)
app.include_router(vm_router, prefix="/vm", tags=["vm"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(sessions_router)
app.include_router(metrics_router)
app.include_router(pages_router)
app.include_router(post_router)
app.include_router(grafana_router)

# ---- Static ----
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/novnc", StaticFiles(directory="static/novnc-ui", html=True), name="novnc")
