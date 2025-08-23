# observability/db_metrics.py
import time
from typing import Optional
from prometheus_client import Histogram, Counter, Gauge
from sqlalchemy import event
from sqlalchemy.engine import Engine

DB_LAT = Histogram(
    "vmshare_db_query_seconds", "DB statement latency (s)",
    ["op"], buckets=(0.001,0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2,5,10)
)
DB_ERR = Counter("vmshare_db_errors_total", "DB errors", ["op"])
POOL_IN_USE = Gauge("vmshare_db_pool_in_use", "Checked-out connections")

def _op(sql: Optional[str]) -> str:
    if not sql: return "other"
    return (sql.lstrip().split(" ", 1)[0] or "other").lower()

def init_db_metrics(engine: Engine):
    @event.listens_for(engine, "before_cursor_execute")
    def _before(cur, conn, stmt, params, ctx, execmany):
        ctx._t0 = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(cur, conn, stmt, params, ctx, execmany):
        DB_LAT.labels(_op(stmt)).observe(time.perf_counter() - getattr(ctx, "_t0", time.perf_counter()))

    @event.listens_for(engine, "handle_error")
    def _on_err(ctx):
        try:
            DB_ERR.labels(_op(ctx.statement or "")).inc()
        except Exception:
            pass

    @event.listens_for(engine, "checkout")
    def _checkout(dbapi_conn, conn_rec, conn_proxy):
        POOL_IN_USE.inc()

    @event.listens_for(engine, "checkin")
    def _checkin(dbapi_conn, conn_rec):
        POOL_IN_USE.dec()
