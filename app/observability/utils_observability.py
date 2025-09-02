# /app/observability/utils_observability.py
import asyncio
import logging
from datetime import datetime

import psutil
from sentry_sdk import capture_message

logger = logging.getLogger(__name__)

# ---- Thresholds ----
CPU_THRESH = 90        # %
RAM_THRESH = 85        # %
SUSTAINED  = 60        # seconds the condition must hold
INTERVAL   = 5         # seconds between checks

# Alert when these devices have ≤ given GiB free (device -> GiB)
DISK_FREE_THRESHOLDS_GIB = {
    "/dev/vda2": 30,   # root disk on your host
}

# ---- Helpers ----
def _sustained(now: datetime, start: datetime | None, above: bool) -> tuple[datetime | None, bool]:
    """
    Track how long a condition has been true.
    Returns the (possibly updated) start timestamp, and whether we crossed the SUSTAINED window.
    """
    if not above:
        return None, False
    start = start or now
    return start, (now - start).total_seconds() >= SUSTAINED


_PSEUDO_FS = {
    "proc", "sysfs", "tmpfs", "devtmpfs", "devpts", "cgroup", "cgroup2", "pstore",
    "autofs", "mqueue", "debugfs", "tracefs", "overlay", "squashfs", "fusectl",
    "configfs", "securityfs", "hugetlbfs", "ramfs",
}

def _device_partition_map() -> dict[str, psutil._common.sdiskpart]:  # device -> representative partition
    """
    Build a mapping of real block devices (e.g., /dev/vda2) to a representative partition entry.
    Filters out pseudo filesystems and non-/dev/* entries.
    Prefers the shortest mountpoint for a device (usually '/').
    """
    devmap: dict[str, psutil._common.sdiskpart] = {}
    try:
        parts = psutil.disk_partitions(all=True)
    except Exception:
        return devmap

    for p in parts:
        if not p.device or not p.device.startswith("/dev/"):
            continue
        if p.fstype in _PSEUDO_FS:
            continue
        # prefer the shortest mountpoint (e.g., '/' over '/some/sub/mount')
        cur = devmap.get(p.device)
        if cur is None or len(p.mountpoint) < len(cur.mountpoint):
            devmap[p.device] = p
    return devmap


# ---- Watchdog ----
async def resource_watchdog(stop_event: asyncio.Event):
    over_cpu: datetime | None = None
    over_ram: datetime | None = None
    over_disk_free: dict[str, datetime | None] = {}  # device -> timestamp when condition started

    # Prime CPU sampling window
    psutil.cpu_percent(None)

    while not stop_event.is_set():
        try:
            now = datetime.utcnow()

            # --- CPU ---
            cpu = psutil.cpu_percent(None)
            over_cpu, fire_cpu = _sustained(now, over_cpu, cpu >= CPU_THRESH)
            if fire_cpu:
                msg = f"[Host] CPU ≥{CPU_THRESH}% for {SUSTAINED}s (now {cpu:.0f}%)"
                logger.warning(msg)
                capture_message(msg, level="warning")
                over_cpu = now  # reset window so repeated alerts require another sustained period

            # --- RAM ---
            vm = psutil.virtual_memory()
            ram_pct = vm.percent
            over_ram, fire_ram = _sustained(now, over_ram, ram_pct >= RAM_THRESH)
            if fire_ram:
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
                over_ram = now

            # --- DISK FREE (absolute GiB by device) ---
            devmap = _device_partition_map()
            for dev, thresh_gib in DISK_FREE_THRESHOLDS_GIB.items():
                part = devmap.get(dev)
                if not part:
                    # Device not mounted/visible; clear any ongoing window
                    over_disk_free.pop(dev, None)
                    continue

                try:
                    du = psutil.disk_usage(part.mountpoint)
                except (PermissionError, FileNotFoundError):
                    over_disk_free.pop(dev, None)
                    continue

                free_gib = du.free / (1024 ** 3)
                over_disk_free[dev], fire_free = _sustained(now, over_disk_free.get(dev), free_gib <= float(thresh_gib))
                if fire_free:
                    msg = (
                        f"[Host] Disk {dev} free ≤{thresh_gib} GiB for {SUSTAINED}s "
                        f"(free {free_gib:.1f} GiB; used {du.percent:.0f}% "
                        f"of {du.total/(1024**3):.1f} GiB; mp={part.mountpoint}; fs={part.fstype})"
                    )
                    logger.warning(msg)
                    capture_message(msg, level="warning")
                    over_disk_free[dev] = now

        except Exception as e:
            logger.exception("resource_watchdog error: %s", e)

        # sleep or stop
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL)
        except asyncio.TimeoutError:
            pass
