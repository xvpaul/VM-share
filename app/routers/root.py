from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

@router.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse("static/index.html")
