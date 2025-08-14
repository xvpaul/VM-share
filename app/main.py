# /main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers.root import router as root_router
from routers.vm   import router as vm_router  
from routers.auth import router as auth_router
from methods.manager.UserManager import SESSIONS 
from utils import cleanup_vm
import logging

app = FastAPI()

app.include_router(root_router)
app.include_router(vm_router, prefix="/api", tags=["vm"])
app.include_router(auth_router, tags=["auth"])

for route in app.routes:
    print(f"{route.name:30} → {route.path}  {getattr(route, 'methods', None)}")

@app.on_event("shutdown")
def shutdown_event():
    logging.info("VM_share/main.py: cleanup at shutdown")
    for vmid, session in SESSIONS.copy().items():
        cleanup_vm(vmid, SESSIONS)

app.mount("/static", StaticFiles(directory="static"), name="static")
