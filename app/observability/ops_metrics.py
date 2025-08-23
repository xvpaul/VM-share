import time
from contextlib import contextmanager, asynccontextmanager
from prometheus_client import Counter, Histogram

# Count successes/failures per operation
OPS = Counter("vmshare_ops_total", "Background ops", ["op", "outcome"])  # outcome=ok|error

# Measure duration per operation
OPS_LAT = Histogram(
    "vmshare_ops_duration_seconds", "Op duration (s)", ["op"],
    buckets=(0.1,0.5,1,2,5,10,30,60,120,300)
)

def ops_ok(op: str):
    OPS.labels(op=op, outcome="ok").inc()

def ops_err(op: str):
    OPS.labels(op=op, outcome="error").inc()

@contextmanager
def time_op(op: str):
    """Sync timing + outcome."""
    t0 = time.perf_counter()
    try:
        yield
        ops_ok(op)
    except Exception:
        ops_err(op)
        raise
    finally:
        OPS_LAT.labels(op=op).observe(time.perf_counter() - t0)

@asynccontextmanager
async def time_op_async(op: str):
    """Async timing + outcome."""
    t0 = time.perf_counter()
    try:
        yield
        ops_ok(op)
    except Exception:
        ops_err(op)
        raise
    finally:
        OPS_LAT.labels(op=op).observe(time.perf_counter() - t0)
