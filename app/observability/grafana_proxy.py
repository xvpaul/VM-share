# /app/observability/grafana_proxy.py
import os
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

logger = logging.getLogger(__name__)
router = APIRouter()
logger.info("grafana_proxy: module loaded")

# NOTE:
# - We serve Grafana under /grafana via Nginx subpath.
# - So the safest base for iframes is the SAME ORIGIN relative path '/grafana'.
# - If you ever move Grafana elsewhere, set GRAFANA_IFRAME_BASE accordingly.
IFRAME_BASE = os.getenv("GRAFANA_IFRAME_BASE", "/grafana").rstrip("/")

@router.get("/grafana/panel_iframe_src")
async def grafana_panel_iframe_src(
    uid: str = Query(..., description="Dashboard UID"),
    panelId: int = Query(..., description="Panel ID"),
    _from: str = Query("now-1h", alias="from"),
    to: str = Query("now"),
    refresh: str = Query("10s"),
    theme: str = Query("dark"),
    orgId: int | None = Query(1, description="Grafana org id"),
    kiosk: bool = Query(True, description="Hide Grafana chrome"),
):
    """
    Returns a JSON object with the iframe src URL for a single-panel view.
    This does NOT render an image. Frontend should use:
      <iframe src={src} ...></iframe>
    """
    # Grafana solo panel path: /d-solo/:uid/:slug
    # slug is cosmetic; 'view' is fine.
    base = f"{IFRAME_BASE}/d-solo/{uid}/view"
    params = {
        "panelId": str(panelId),
        "from": _from,
        "to": to,
        "refresh": refresh,
        "theme": theme,
    }
    if orgId is not None:
        params["orgId"] = str(orgId)
    if kiosk:
        params["kiosk"] = ""  # presence-only flag

    # Build query string manually to keep empty kiosk param
    query = "&".join(f"{k}={v}" if v != "" else k for k, v in params.items())
    src = f"{base}?{query}"

    logger.info("grafana_iframe_src: uid=%s panelId=%s src=%s", uid, panelId, src)
    return JSONResponse({"src": src})

# --- DEPRECATED: old PNG endpoint (renderer) ---
@router.get("/grafana/panel.png")
async def grafana_panel_png_deprecated():
    """
    Deprecated. We no longer render PNGs (headless Chromium).
    """
    # 410 Gone tells clients this resource is intentionally removed.
    return PlainTextResponse(
        "PNG rendering is deprecated. Use /grafana/panel_iframe_src and an <iframe> instead.",
        status_code=410,
    )
