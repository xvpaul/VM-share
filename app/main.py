# main.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import subprocess

app = FastAPI()

# 1) Serve your existing index.html on GET /
@app.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse("static/index.html")

# 2) Serve any other static assets (if you add CSS/JS/images) under /static/*
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3) The POST endpoint your front‑end fetch() calls
@app.post("/api/run-script")
async def run_vm_script(request: Request):
    try:
        data = await request.json()
        cmd = ["bash", "../core/vm_scripts/AlpineLinux/runner.sh"]
        if user_id := data.get("user_id"):
            cmd.append(str(user_id))

        subprocess.Popen(
            cmd
        )

        # Instead of redirecting directly, return URL to frontend
        return JSONResponse({
            "message": "VM launched",
            "redirect": "http://localhost:6080/vnc.html"
        })

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))