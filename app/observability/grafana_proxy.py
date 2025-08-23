# app/observability/grafana_proxy.py
import os, httpx
from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter()

GRAFANA_BASE  = os.getenv("GRAFANA_BASE", "http://localhost:3000").rstrip("/")
GRAFANA_TOKEN = os.getenv("GRAFANA_TOKEN", "")

@router.get("/grafana/panel.png")
async def grafana_panel_png(
    uid: str = Query(..., description="Dashboard UID"),
    panelId: int = Query(..., description="Panel ID"),
    # accept relative time or epoch ms
    from_: str = Query("now-1h", alias="from"),
    to: str = Query("now"),
    width: int = Query(1100),
    height: int = Query(300),
    theme: str = Query("dark"),
    orgId: int | None = Query(None, description="Optional Grafana org id"),
    tz: str | None = Query(None),
):
    if not GRAFANA_TOKEN:
        raise HTTPException(500, "GRAFANA_TOKEN not configured on server")

    # NOTE: include a slug segment; '_' is fine
    url = f"{GRAFANA_BASE}/render/d-solo/{uid}/_"

    params = {
        "panelId": panelId,
        "from": from_,
        "to": to,
        "width": width,
        "height": height,
        "theme": theme,
    }
    if orgId is not None:
        params["orgId"] = orgId
    if tz:
        params["tz"] = tz

    headers = {
        "Authorization": f"Bearer {GRAFANA_TOKEN}",
        "Accept": "image/png,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as e:
        raise HTTPException(502, f"Grafana unreachable: {e}")

    ct = (r.headers.get("content-type") or "").lower()
    if r.status_code != 200 or "image" not in ct:
        # Show first bytes of Grafana’s error (401/403/404 or renderer issues)
        snippet = (r.text or "")[:200]
        raise HTTPException(502, f"Grafana render failed {r.status_code}: {snippet}")

    # no-store so your cache-buster works predictably
    return Response(
        r.content,
        media_type="image/png",
        headers={"Cache-Control": "no-store"}
    )
