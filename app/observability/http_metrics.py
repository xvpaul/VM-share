# observability/http_metrics.py
import re, time
from typing import Optional
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import HTTPException as FastAPIHTTPException

REQS = Counter(
    "vmshare_requests_total", "HTTP requests",
    ["method", "path", "status"]
)
LAT = Histogram(
    "vmshare_request_duration_seconds", "HTTP request latency (s)",
    ["method", "path"],
    buckets=(0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2.5,5,10)
)

_uuid = re.compile(r"[0-9a-fA-F-]{8}-[0-9a-fA-F-]{4}-[0-9a-fA-F-]{4}-[0-9a-fA-F-]{4}-[0-9a-fA-F-]{12}")
_int  = re.compile(r"/\d+")
def _norm_path(scope) -> str:
    route = scope.get("route")
    p: Optional[str] = getattr(route, "path", None)
    if p:
        return p                     # e.g., "/vm/{id}"
    raw = scope.get("path") or "/"
    return _int.sub("/{id}", _uuid.sub("/{uuid}", raw))

class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        method = request.method
        path   = _norm_path(request.scope)
        status = 500
        try:
            resp = await call_next(request)
            status = getattr(resp, "status_code", 200)
            return resp
        except (FastAPIHTTPException, StarletteHTTPException) as ex:
            status = getattr(ex, "status_code", 500)
            raise
        except Exception:
            status = 500
            raise
        finally:
            LAT.labels(method=method, path=path).observe(time.perf_counter() - t0)
            REQS.labels(method=method, path=path, status=str(status)).inc()
