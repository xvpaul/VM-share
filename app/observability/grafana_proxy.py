# /app/observability/grafana_proxy.py
import os
from fastapi import APIRouter, HTTPException, Query, Response
import httpx

router = APIRouter()

# Point this to your *internal* grafana (the one from docker-compose)
GRAFANA_BASE  = os.getenv("GRAFANA_BASE", "http://localhost:3000")
# Create a Grafana Service Account (Viewer) and put its token in env:
GRAFANA_TOKEN = os.getenv("GRAFANA_TOKEN", "")

@router.get("/grafana/panel.png")
async def grafana_panel_png(
    uid: str = Query(..., description="Dashboard UID"),
    panelId: int = Query(..., description="Panel ID"),
    orgId: int = Query(1, description="Grafana org id"),
    # accept either epoch ms (int) or relative strings like now-1h
    _from: str = Query("now-1h", alias="from"),
    to: str = Query("now"),
    width: int = Query(1100),
    height: int = Query(300),
    theme: str = Query("dark"),
    tz: str = Query("browser"),
):
    if not GRAFANA_TOKEN:
        raise HTTPException(500, "GRAFANA_TOKEN not configured on server")

    # Grafana render endpoint (requires image renderer plugin/container)
    url = f"{GRAFANA_BASE.rstrip('/')}/render/d-solo/{uid}"
    params = {
        "orgId": orgId,
        "panelId": panelId,
        "from": _from,
        "to": to,
        "width": width,
        "height": height,
        "theme": theme,
        "tz": tz,
    }
    headers = {"Authorization": f"Bearer {GRAFANA_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, params=params, headers=headers)
        if r.status_code != 200 or "image" not in (r.headers.get("content-type") or ""):
            # bubble up grafana’s message for easier debugging
            detail = r.text[:200]
            raise HTTPException(r.status_code, f"Grafana render failed: {detail}")
        # pass-through PNG
        return Response(r.content, media_type="image/png")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Grafana unreachable: {e}")