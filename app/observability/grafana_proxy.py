# /app/observability/grafana_proxy.py
import os
import time
import logging
from fastapi import APIRouter, HTTPException, Query, Response
import httpx

router = APIRouter()
logging.info("grafana_proxy: module loaded")

@router.get("/grafana/panel.png")
async def grafana_panel_png(
    uid: str = Query(..., description="Dashboard UID"),
    panelId: int = Query(..., description="Panel ID"),
    _from: str = Query("now-1h", alias="from"),
    to: str = Query("now"),
    width: int = Query(1100),
    height: int = Query(300),
    theme: str = Query("dark"),
    orgId: int | None = Query(None, description="Optional Grafana org id"),
    tz: str | None = Query(None),
):
    base  = os.getenv("GRAFANA_BASE", "http://localhost:3000").rstrip("/")
    token = os.getenv("GRAFANA_TOKEN", "")

    if not token:
        logging.error("grafana_proxy: GRAFANA_TOKEN is not set")
        raise HTTPException(500, "GRAFANA_TOKEN not configured on server")

    url = f"{base}/render/d-solo/{uid}/_"  # slug can be anything
    params = {
        "panelId": panelId,
        "from": _from,
        "to": to,
        "width": width,
        "height": height,
        "theme": theme,
    }
    if orgId is not None:
        params["orgId"] = orgId
    if tz:
        params["tz"] = tz

    logging.info(
        "grafana_proxy: render request base=%s uid=%s panelId=%s from=%s to=%s w=%s h=%s theme=%s orgId=%s tz=%s",
        base, uid, panelId, _from, to, width, height, theme, orgId, tz
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "image/png,*/*;q=0.8",
    }

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as e:
        dt = (time.perf_counter() - t0) * 1000
        logging.exception("grafana_proxy: unreachable base=%s dur_ms=%.1f err=%s", base, dt, e)
        raise HTTPException(502, f"Grafana unreachable: {e}") from e

    dt = (time.perf_counter() - t0) * 1000
    ct = (r.headers.get("content-type") or "").lower()
    size = len(r.content or b"")

    if r.status_code != 200 or "image" not in ct:
        snippet = (r.text or "")[:200]
        logging.warning(
            "grafana_proxy: render failed status=%s ct=%s bytes=%s dur_ms=%.1f url=%s params=%s snippet=%r",
            r.status_code, ct, size, dt, url, params, snippet
        )
        raise HTTPException(502, f"Grafana render failed {r.status_code}: {snippet}")

    logging.info(
        "grafana_proxy: render ok status=%s bytes=%s dur_ms=%.1f uid=%s panelId=%s",
        r.status_code, size, dt, uid, panelId
    )

    return Response(
        r.content,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Grafana-Status": str(r.status_code),
            "X-Render-Duration-ms": f"{dt:.1f}",
        },
    )
