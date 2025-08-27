# /app/methods/manager/OverlayManager.py
import platform, shutil, subprocess, os, tempfile, time, json, re, socket
from configs.config import SNAPSHOTS_PATH, VM_PROFILES
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

RUN_DIR = Path("/tmp/qemu")
RUN_DIR.mkdir(parents=True, exist_ok=True)

class OnlineSnapshotError(RuntimeError): ...


class QemuOverlayManager:
    """
    Manages a user's qcow2 overlay and a headless QEMU instance with VNC+QMP on UNIX sockets,
    supporting multiple OS profiles (e.g., alpine, ubuntu).
    """
    def __init__(self, user_id: str, vmid: str, os_type: str = "alpine"):
        if os_type not in VM_PROFILES:
            raise ValueError(f"Unsupported OS type: {os_type}")
        
        self.profile = VM_PROFILES[os_type]
        self.user_id = user_id
        self.vmid = vmid
        self.os_type = os_type

    def overlay_path(self) -> Path:
        overlay_dir = self.profile.get("overlay_dir")
        prefix = self.profile.get("overlay_prefix")
        if not overlay_dir or not prefix:
            raise ValueError(f"profile '{self.os_type}' is ISO-only; overlays are not supported")
        return overlay_dir / f"{prefix}_{self.vmid}.qcow2"

    def create_overlay(self) -> Path:
        if not self.profile.get("overlay_dir") or not self.profile.get("overlay_prefix"):
            raise ValueError(f"profile '{self.os_type}' is ISO-only; use /run-iso")
        try:
            overlay = self.overlay_path()
            if overlay.exists():
                logger.info(f"Overlay already exists for user {self.user_id}: {overlay}")
                return overlay
            subprocess.check_call([
                "qemu-img", "create", "-f", "qcow2",
                "-F", "qcow2", "-b", str(self.profile["base_image"]),
                str(overlay)
            ])
            logger.info(f"Created overlay for user {self.user_id}: {overlay}")
            return overlay
        except Exception as e:
            logger.exception(f"Unexpected error during overlay creation for user {self.user_id}: {e}")
            raise

    def _socket_paths(self, vmid: str):
        vnc = RUN_DIR / f"vnc-{vmid}.sock"
        qmp = RUN_DIR / f"qmp-{vmid}.sock"
        return vnc, qmp

    def boot_vm(self, vmid: str, memory_mb: int = None, wait_timeout_s: float = 10.0, drive_path: str | None = None) -> dict:
        image = Path(drive_path) if drive_path else self.overlay_path()
        if not image.exists():
            error_msg = f"Drive image missing for user {self.user_id}: {image}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        vnc_sock, qmp_sock = self._socket_paths(vmid)
        for s in (vnc_sock, qmp_sock):
            if s.exists():
                s.unlink()
                logger.warning(f"Removed existing socket: {s}")

        mem = str(memory_mb or self.profile["default_memory"])

        pidfile = RUN_DIR / f"qemu-{vmid}.pid"
        try:
            if pidfile.exists():
                pidfile.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove existing pidfile {pidfile}: {e}")

        cmd = [
            "qemu-system-amd",
            # "-enable-kvm",
            " -machine pc,accel=kvm,kernel-irqchip=off",
            "-cpu EPYC,pmu=off,-tsc-deadline,-hle,-rtm ",
            "-m", mem,
            "-drive", f"file={image},format=qcow2,if=virtio,cache=writeback,discard=unmap",
            "-nic", "user,model=virtio-net-pci",
            "-vnc", f"unix:{vnc_sock}",
            "-qmp", f"unix:{qmp_sock},server,nowait",
            "-display", "none",
            "-daemonize",
            "-pidfile", str(pidfile),
        ]
        qemu-system-x86_64 \
  -enable-kvm \
  -machine pc,accel=kvm,kernel-irqchip=off \
  -cpu EPYC,pmu=off,-tsc-deadline,-hle,-rtm \
  -m 2048 -smp 2 \
  -display none -serial mon:stdio \
  -drive file=… ,if=virtio,format=qcow2,cache=writeback,discard=unmap \
  -nic user,model=virtio-net-pci

        logger.info(f"Launching QEMU for user {self.user_id} with vmid={vmid}, os_type={self.os_type}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = (
                f"QEMU failed for user {self.user_id} (vmid={vmid})\n"
                f"Return code: {result.returncode}\n"
                f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        deadline = time.time() + wait_timeout_s
        qemu_pid = None
        last_exc = None
        while time.time() < deadline:
            if pidfile.exists():
                try:
                    qemu_pid = int(pidfile.read_text().strip())
                    break
                except Exception as e:
                    last_exc = e
            time.sleep(0.05)

        if qemu_pid is None:
            msg = (
                f"QEMU started but no pidfile within {wait_timeout_s}s "
                f"(expected at {pidfile}). Last read error: {last_exc}. STDERR: {result.stderr}"
            )
            logger.error(msg)
            raise FileNotFoundError(msg)

        logger.info(f"QEMU successfully started for user {self.user_id} (vmid={vmid}) with PID {qemu_pid}")

        return {
            "user_id": self.user_id,
            "vmid": vmid,
            "os_type": self.os_type,
            "overlay": str(image),            # <- reflect the actual image used
            "vnc_socket": str(vnc_sock),
            "qmp_socket": str(qmp_sock),
            "started_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "pid": qemu_pid,
        }

    
    # Replace your current peek_iso with this:
    @staticmethod
    def peek_iso(iso_path: str, max_files: int = 200) -> dict:
        """
        Portable ISO introspection that never raises due to missing/failing tools.
        Tries (macOS) hdiutil -> iso-info -> bsdtar. Returns minimal info on failure.
        """
        iso = Path(iso_path)
        if not iso.exists():
            raise FileNotFoundError(f"ISO not found: {iso}")

        info = {
            "iso": str(iso),
            "size_mb": round(iso.stat().st_size / (1024 * 1024), 2),
            "has_uefi": False,
            "has_bios": False,
            "kernel": None,
            "initrd": None,
            "files": [],
            "method": None,
            "warnings": [],
        }

        def _postprocess(paths: list[str]):
            info["files"] = paths[:max_files]
            for f in paths:
                lf = f.lower()
                if "efi/boot/bootx64.efi" in lf:
                    info["has_uefi"] = True
                if "isolinux/" in lf or "syslinux/" in lf or "boot/grub" in lf:
                    info["has_bios"] = True
                if lf.endswith("vmlinuz") and not info["kernel"]:
                    info["kernel"] = f
                if "initrd" in lf and not info["initrd"]:
                    info["initrd"] = f

        # --- 1) macOS: hdiutil (built-in) ---
        if platform.system().lower() == "darwin":
            mnt = Path(tempfile.mkdtemp(prefix="isopeek_"))
            try:
                p = subprocess.run(
                    ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mnt), str(iso)],
                    capture_output=True, text=True
                )
                if p.returncode == 0:
                    paths = []
                    for root, dirs, files in os.walk(mnt):
                        rel_root = "/" + str(Path(root).relative_to(mnt))
                        rel_root = rel_root.replace("//", "/")
                        for d in dirs:
                            paths.append(f"{rel_root}/{d}/".replace("//", "/"))
                        for f in files:
                            paths.append(f"{rel_root}/{f}".replace("//", "/"))
                    info["method"] = "hdiutil"
                    _postprocess(paths)
                    return info
                else:
                    info["warnings"].append(f"hdiutil failed: {p.stderr.strip()}")
            except Exception as e:
                info["warnings"].append(f"hdiutil error: {e}")
            finally:
                subprocess.run(["hdiutil", "detach", str(mnt)], capture_output=True)

        # --- 2) iso-info (libcdio) ---
        if shutil.which("iso-info"):
            try:
                out = subprocess.run(
                    ["iso-info", "-i", str(iso), "-f"],  # file list
                    capture_output=True, text=True
                )
                if out.returncode == 0:
                    info["method"] = "iso-info"
                    _postprocess(out.stdout.splitlines())
                    return info
                info["warnings"].append(f"iso-info failed: {out.stderr.strip()}")
            except Exception as e:
                info["warnings"].append(f"iso-info error: {e}")

        # --- 3) bsdtar (libarchive) ---
        if shutil.which("bsdtar"):
            try:
                out = subprocess.run(
                    ["bsdtar", "-tf", str(iso)],
                    capture_output=True, text=True
                )
                if out.returncode == 0:
                    info["method"] = "bsdtar"
                    _postprocess(out.stdout.splitlines())
                    return info
                info["warnings"].append(f"bsdtar failed: {out.stderr.strip()}")
            except Exception as e:
                info["warnings"].append(f"bsdtar error: {e}")

        # --- 4) final fallback: minimal info, no raise ---
        info["warnings"].append("All peek methods unavailable/failed; returning minimal info.")
        return info

    def boot_from_iso(
        self,
        vmid: str,
        iso_path: str,
        *,
        memory_mb: int | None = None,
        cpus: int | None = None,
        data_disk_gb: int | None = None,
        install_disk_path: str | None = None,
        wait_timeout_s: float = 10.0,
        force_uefi: bool | None = None,           # ignored (BIOS-only)
        ovmf_code_path: str | None = None,        # ignored (BIOS-only)
        extra_qemu_args: list[str] | None = None,
    ) -> dict:
        # 0) Absolute ISO + quick validity checks
        iso = Path(iso_path).expanduser().resolve(strict=True)
        size = iso.stat().st_size
        if size < 10 * 1024 * 1024:
            raise RuntimeError(f"ISO too small ({size} bytes): {iso}")
        try:
            with iso.open("rb") as f:
                f.seek(0x8000)
                hdr = f.read(8192)
                if b"CD001" not in hdr and b"NSR02" not in hdr and b"NSR03" not in hdr:
                    raise RuntimeError(f"File is not ISO9660/UDF (no CD001/NSR0x at 0x8000): {iso}")
        except Exception as e:
            raise RuntimeError(f"Failed to inspect ISO {iso}: {e}")

        # 1) Resources (defaults from profile)
        mem = str(memory_mb or self.profile.get("default_memory", 2048))
        smp = str(cpus or self.profile.get("default_cpus", 2))

        # 2) Sockets/pidfile
        vnc_sock, qmp_sock = self._socket_paths(vmid)
        pidfile = RUN_DIR / f"qemu-{vmid}.pid"
        for p in (vnc_sock, qmp_sock, pidfile):
            try:
                if p.exists():
                    p.unlink()
                    logger.warning(f"[boot_from_iso] removed leftover: {p}")
            except Exception as e:
                logger.warning(f"[boot_from_iso] cleanup failed for {p}: {e}")

        # 3) Optional scratch disk
        scratch_path = None
        if data_disk_gb:
            if data_disk_gb <= 0:
                raise ValueError("data_disk_gb must be a positive integer (GB).")
            base_dir = self.profile.get("overlay_dir", RUN_DIR)
            scratch_path = Path(base_dir) / f"iso-scratch-{vmid}.qcow2"
            if not scratch_path.exists():
                subprocess.check_call([
                    "qemu-img", "create", "-f", "qcow2", str(scratch_path), f"{int(data_disk_gb)}G"
                ])
                logger.info(f"[boot_from_iso] created scratch disk: {scratch_path}")

        # 4) Build minimal, VNC‑only, BIOS (SeaBIOS) command
        cmd = [
            "qemu-system-x86_64",
            "-machine", "pc,accel=tcg",                # BIOS-friendly, works with -cdrom
            "-smp", smp,
            "-m", mem,
            "-display", "none",
            "-vnc", f"unix:{vnc_sock}",
            "-qmp", f"unix:{qmp_sock},server,nowait",
            "-daemonize",
            "-pidfile", str(pidfile),
            "-cdrom", str(iso),                        # ABSOLUTE path
            "-boot", "d",
            "-nic", "user,model=virtio-net-pci",
            "-vga", "std",
        ]
        if scratch_path:
            cmd += ["-drive", f"file={scratch_path},format=qcow2,if=virtio,cache=writeback,discard=unmap"]
        if install_disk_path:
            target = Path(install_disk_path).expanduser().resolve(strict=True)
            cmd += ["-drive", f"file={target},format=qcow2,if=virtio,cache=writeback,discard=unmap"]
        if extra_qemu_args:
            cmd += list(extra_qemu_args)

        logger.info(
            "Launching ISO (VNC, BIOS) user=%s vmid=%s os=%s iso_abs=%s size=%s mem=%s smp=%s",
            self.user_id, vmid, self.os_type, str(iso), size, mem, smp
        )

        # 5) Launch
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            msg = (
                f"QEMU ISO boot failed (user={self.user_id} vmid={vmid})\n"
                f"rc={result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
            logger.error(msg)
            raise RuntimeError(msg)

        # 6) Wait for pidfile
        deadline = time.time() + wait_timeout_s
        qemu_pid = None
        last_exc = None
        while time.time() < deadline:
            if pidfile.exists():
                try:
                    qemu_pid = int(pidfile.read_text().strip())
                    break
                except Exception as e:
                    last_exc = e
            time.sleep(0.05)
        if qemu_pid is None:
            msg = (
                f"QEMU (ISO VNC) started but no pidfile within {wait_timeout_s}s "
                f"(expected at {pidfile}). Last error: {last_exc}. STDERR: {result.stderr}"
            )
            logger.error(msg)
            raise FileNotFoundError(msg)

        return {
            "mode": "iso-live-vnc",
            "user_id": self.user_id,
            "vmid": vmid,
            "os_type": self.os_type,
            "iso": str(iso),
            "vnc_socket": str(vnc_sock),
            "qmp_socket": str(qmp_sock),
            "pid": qemu_pid,
            "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
   
    def create_disk_snapshot(self, name: str) -> Path:
        """
        Live disk-only snapshot while VM is running (via QMP drive-backup).
        Output: {SNAPSHOTS_PATH}/{user_id}__{os_type}__{self.vmid}.qcow2
        """
        out = Path(SNAPSHOTS_PATH) / f"{self.user_id}__{self.os_type}__{self.vmid}.qcow2"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            try:
                out.unlink()
            except Exception as e:
                raise OnlineSnapshotError(f"Failed to remove existing snapshot file: {out} ({e})")

        # Use QMP of the *running* VM (do not require overlay file)
        _, qmp_sock = self._socket_paths(self.vmid)
        if not qmp_sock.exists():
            # overlays may be purged when VM stops; don't attempt offline copy
            raise OnlineSnapshotError("VM is not running (no QMP socket) — cannot create live snapshot")

        def _qmp_send(payload: dict, timeout: float = 10.0) -> dict:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(str(qmp_sock))
                # greeting
                try:
                    json.loads(s.recv(4096).decode(errors="ignore") or "{}")
                except Exception:
                    pass
                # enable caps
                s.sendall((json.dumps({"execute": "qmp_capabilities"}) + "\n").encode())
                try:
                    json.loads(s.recv(4096).decode(errors="ignore") or "{}")
                except Exception:
                    pass
                # command
                s.sendall((json.dumps(payload) + "\n").encode())
                resp = s.recv(65536).decode(errors="ignore") or "{}"
                try:
                    return json.loads(resp)
                except Exception:
                    return {}

        # Pick the main writable disk device from query-block
        qb = _qmp_send({"execute": "query-block"})
        devices = qb.get("return", []) if isinstance(qb, dict) else []
        dev_name = None

        def _drv(ins: dict) -> str:
            if isinstance(ins.get("image"), dict):
                return ins["image"].get("format") or ""
            return ins.get("drv") or ""

        for d in devices:
            ins = d.get("inserted") or {}
            if not ins:
                continue
            # skip cdrom/ro devices
            if ins.get("ro") or ins.get("removable"):
                continue
            fmt = _drv(ins).lower()
            if fmt in ("qcow2", "raw"):            # typical root disk formats
                dev_name = d.get("device")
                if dev_name:
                    break

        if not dev_name and devices:
            # last resort: first device with a name
            dev_name = next((d.get("device") for d in devices if d.get("device")), None)

        if not dev_name:
            raise OnlineSnapshotError("Unable to determine block device for drive-backup")

        job_id = f"backup-{self.vmid}-{int(time.time())}"
        start = _qmp_send({
            "execute": "drive-backup",
            "arguments": {
                "device": dev_name,
                "job-id": job_id,
                "target": str(out),
                "format": "qcow2",
                "sync": "full",
                "auto-finalize": True,
                "auto-dismiss": True,
            }
        })
        if isinstance(start, dict) and "error" in start:
            raise OnlineSnapshotError(f"drive-backup start failed: {start['error']}")

        # Wait for job completion (auto-dismiss removes it from the list)
        deadline = time.time() + 300
        while time.time() < deadline:
            q = _qmp_send({"execute": "query-block-jobs"})
            jobs = q.get("return", []) if isinstance(q, dict) else []
            if not any(j.get("id") == job_id for j in jobs):
                break
            time.sleep(0.5)
        else:
            raise OnlineSnapshotError("drive-backup timed out")

        if not out.exists() or out.stat().st_size == 0:
            raise OnlineSnapshotError("Snapshot file missing/empty after drive-backup")

        logger.info(f"[snap] Live disk snapshot created via QMP: {out}")
        return out

    def list_disk_snapshots(self) -> list[dict]:
        """List internal qcow2 snapshots (disk-only)."""
        overlay = self.overlay_path()
        cmd = ["qemu-img", "snapshot", "-l", str(overlay)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise OnlineSnapshotError(f"Failed to list snapshots:\n{result.stderr}")

        snapshots = []
        for line in result.stdout.splitlines():
            # Skip header lines, parse: ID TAG VM SIZE DATE VM CLOCK
            if line.strip().startswith("ID") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                snapshots.append({"id": parts[0], "tag": parts[1]})
        return snapshots

    def delete_disk_snapshot(self, name: str) -> None:
        """Delete a qcow2 internal snapshot."""
        overlay = self.overlay_path()
        cmd = ["qemu-img", "snapshot", "-d", name, str(overlay)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise OnlineSnapshotError(
                f"Failed to delete snapshot {name}:\n{result.stderr}"
            )
        logger.info(f"[snap] Deleted disk snapshot '{name}' for {overlay}")