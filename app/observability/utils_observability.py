# /app/observability/utils_observability.py
import asyncio, psutil, logging
from datetime import datetime
from sentry_sdk import capture_message

CPU_THRESH = 90   # %
RAM_THRESH = 85   # %
SUSTAINED  = 60   # seconds
INTERVAL   = 5    # seconds

def _sustained(now, start, above):
    if not above:
        return None, False
    start = start or now
    return start, (now - start).total_seconds() >= SUSTAINED

async def resource_watchdog(stop_event: asyncio.Event):
    over_cpu = over_ram = None
    psutil.cpu_percent(None)  # prime
    while not stop_event.is_set():
        try:
            now = datetime.utcnow()
            cpu = psutil.cpu_percent(None)
            ram = psutil.virtual_memory().percent

            over_cpu, fire_cpu = _sustained(now, over_cpu, cpu >= CPU_THRESH)
            over_ram, fire_ram = _sustained(now, over_ram, ram >= RAM_THRESH)

            if fire_cpu:
                msg = f"[Host] CPU ≥{CPU_THRESH}% for {SUSTAINED}s (now {cpu:.0f}%)"
                logging.warning(msg)
                capture_message(msg, level="warning")
                over_cpu = now

            if fire_ram:
                qemu_rss = 0
                for p in psutil.process_iter(['name','memory_info']):
                    if (p.info['name'] or '').startswith('qemu-system') and p.info['memory_info']:
                        qemu_rss += p.info['memory_info'].rss
                msg = f"[Host] RAM ≥{RAM_THRESH}% for {SUSTAINED}s (qemu RSS≈{qemu_rss/(1024**3):.2f} GiB)"
                logging.warning(msg)
                capture_message(msg, level="warning")
                over_ram = now
        except Exception as e:
            logging.exception("resource_watchdog error: %s", e)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL)
        except asyncio.TimeoutError:
            pass
