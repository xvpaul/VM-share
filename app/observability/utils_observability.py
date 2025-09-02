# /app/observability/utils_observability.py
import asyncio
import logging
from datetime import datetime

import psutil
from sentry_sdk import capture_message

logger = logging.getLogger(__name__)

# Telegram reporting (from /app/observability/report.py)
try:
    from .report import telegram_reporting
except Exception as _e:
    logger.error("Failed to import telegram_reporting: %s", _e)
    def telegram_reporting(message: str) -> None:  # no-op fallback
        logger.error("telegram_reporting not available; message was: %s", message)

# ---- Thresholds ----
CPU_THRESH = 1        # %
RAM_THRESH = 3        # %
SUSTAINED  = 10        # seconds the condition must hold
INTERVAL   = 5         # seconds between checks

# Alert when these devices have ≤ given GiB free (device -> GiB)
DISK_FREE_THRESHOLDS_GIB = {
    "/dev/vda2": 30,   # root disk on your host
}

# ---- Helpers ----
def _sustained(now: datetime, start: datetime | None, condition_true: bool) -> tuple[datetime | None, bool]:
    """
    Track how long a condition has been true.
    Returns the (possibly updated) start timestamp, and whether we crossed the SUSTAINED window.
    """
    if not condition_true:
        return None, False
    start = start or now
    return start, (now - start).total_seconds() >= SUSTAINED


_PSEUDO_FS = {
    "proc", "sysfs", "tmpfs", "devtmpfs", "devpts", "cgroup", "cgroup2", "pstore",
    "autofs", "mqueue", "debugfs", "tracefs", "overlay", "squashfs", "fusectl",
    "configfs", "securityfs", "hugetlbfs", "ramfs",
}

def _device_partition_map() -> dict[str, object]:  # device -> representative partition
    """
    Map real block devices (e.g., /dev/vda2) to a representative partition.
    Filters out pseudo filesystems and non-/dev/* entries.
    Prefers the shortest mountpoint for a device (usually '/').
    """
    devmap: dict[str, object] = {}
    try:
        parts = psutil.disk_partitions(all=True)
    except Exception:
        return devmap

    for p in parts:
        try:
            if not p.device or not p.device.startswith("/dev/"):
                continue
            if p.fstype in _PSEUDO_FS:
                continue
            cur = devmap.get(p.device)
            if cur is None or len(p.mountpoint) < len(getattr(cur, "mountpoint", "")):
                devmap[p.device] = p
        except Exception:
            continue
    return devmap


# ---- Watchdog ----
async def resource_watchdog(stop_event: asyncio.Event):
    # High-usage windows
    over_cpu: datetime | None = None
    over_ram: datetime | None = None
    over_disk_free: dict[str, datetime | None] = {}  # device -> timestamp when condition started

    # Recovery windows (below threshold)
    cpu_alert_open = False
    ram_alert_open = False
    cpu_recover: datetime | None = None
    ram_recover: datetime | None = None

    # Prime CPU sampling window
    psutil.cpu_percent(None)

    while not stop_event.is_set():
        try:
            now = datetime.utcnow()

            # --- CPU ---
            cpu = psutil.cpu_percent(None)

            # High CPU sustained
            over_cpu, fire_cpu = _sustained(now, over_cpu, cpu >= CPU_THRESH)
            if fire_cpu and not cpu_alert_open:
                msg = f"[Host] CPU ≥{CPU_THRESH}% for {SUSTAINED}s (now {cpu:.0f}%)"
                logger.warning(msg)
                capture_message(msg, level="warning")
                try:
                    telegram_reporting(msg)
                except Exception as e:
                    logger.error("telegram_reporting CPU error: %s", e)
                cpu_alert_open = True
                over_cpu = now  # require another sustained window for subsequent alerts
                cpu_recover = None  # reset recovery timer

            # CPU recovery sustained
            cpu_recover, fire_cpu_recover = _sustained(now, cpu_recover, cpu < CPU_THRESH)
            if cpu_alert_open and fire_cpu_recover:
                msg = f"[Host] CPU recovered <{CPU_THRESH}% for {SUSTAINED}s (now {cpu:.0f}%)"
                logger.info(msg)
                capture_message(msg, level="info")
                try:
                    telegram_reporting(msg)
                except Exception as e:
                    logger.error("telegram_reporting CPU recovery error: %s", e)
                cpu_alert_open = False
                cpu_recover = None

            # --- RAM ---
            vm = psutil.virtual_memory()
            ram_pct = vm.percent

            # High RAM sustained
            over_ram, fire_ram = _sustained(now, over_ram, ram_pct >= RAM_THRESH)
            if fire_ram and not ram_alert_open:
                # Sum RSS of qemu-system* processes for context
                qemu_rss = 0
                for p in psutil.process_iter(["name", "memory_info"]):
                    try:
                        if (p.info.get("name") or "").startswith("qemu-system") and p.info.get("memory_info"):
                            qemu_rss += p.info["memory_info"].rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                msg = (
                    f"[Host] RAM ≥{RAM_THRESH}% for {SUSTAINED}s "
                    f"(qemu RSS≈{qemu_rss/(1024**3):.2f} GiB, used {ram_pct:.0f}%)"
                )
                logger.warning(msg)
                capture_message(msg, level="warning")
                try:
                    telegram_reporting(msg)
                except Exception as e:
                    logger.error("telegram_reporting RAM error: %s", e)
                ram_alert_open = True
                over_ram = now
                ram_recover = None

            # RAM recovery sustained
            ram_recover, fire_ram_recover = _sustained(now, ram_recover, ram_pct < RAM_THRESH)
            if ram_alert_open and fire_ram_recover:
                msg = f"[Host] RAM recovered <{RAM_THRESH}% for {SUSTAINED}s (now {ram_pct:.0f}%)"
                logger.info(msg)
                capture_message(msg, level="info")
                try:
                    telegram_reporting(msg)
                except Exception as e:
                    logger.error("telegram_reporting RAM recovery error: %s", e)
                ram_alert_open = False
                ram_recover = None

            # --- DISK FREE (absolute GiB by device) ---
            devmap = _device_partition_map()
            for dev, thresh_gib in DISK_FREE_THRESHOLDS_GIB.items():
                part = devmap.get(dev)
                if not part:
                    over_disk_free.pop(dev, None)
                    continue

                try:
                    du = psutil.disk_usage(part.mountpoint)
                except (PermissionError, FileNotFoundError):
                    over_disk_free.pop(dev, None)
                    continue

                free_gib = du.free / (1024 ** 3)
                over_disk_free[dev], fire_free = _sustained(
                    now, over_disk_free.get(dev), free_gib <= float(thresh_gib)
                )
                if fire_free:
                    msg = (
                        f"[Host] Disk {dev} free ≤{thresh_gib} GiB for {SUSTAINED}s "
                        f"(free {free_gib:.1f} GiB; used {du.percent:.0f}% "
                        f"of {du.total/(1024**3):.1f} GiB; mp={part.mountpoint}; fs={part.fstype})"
                    )
                    logger.warning(msg)
                    capture_message(msg, level="warning")
                    try:
                        telegram_reporting(msg)
                    except Exception as e:
                        logger.error("telegram_reporting DISK error: %s", e)
                    over_disk_free[dev] = now

        except Exception as e:
            logger.exception("resource_watchdog error: %s", e)

        # sleep or stop
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL)
        except asyncio.TimeoutError:
            pass
