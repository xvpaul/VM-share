from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers.root import router as root_router
from routers.vm   import router as vm_router
from routers.auth import router as auth_router

app = FastAPI()

app.include_router(root_router)
app.include_router(vm_router, prefix="/api", tags=["vm"])
app.include_router(auth_router, tags=["auth"])

app.mount("/static", StaticFiles(directory="static"), name="static")
