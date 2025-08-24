# /app/methods/manager/OverlayManager.py
import platform, shutil, subprocess, os, tempfile, time, json, re, socket
import configs.vm_profiles as vm_profiles
import configs.log_config as logs
from configs.config import SNAPSHOTS_PATH
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
        if os_type not in vm_profiles.VM_PROFILES:
            raise ValueError(f"Unsupported OS type: {os_type}")
        
        self.profile = vm_profiles.VM_PROFILES[os_type]
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

    def boot_vm(self, vmid: str, memory_mb: int = None, wait_timeout_s: float = 10.0) -> dict:
        overlay = self.overlay_path()
        if not overlay.exists():
            error_msg = f"Overlay missing for user {self.user_id}: {overlay}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        vnc_sock, qmp_sock = self._socket_paths(vmid)
        for s in (vnc_sock, qmp_sock):
            if s.exists():
                s.unlink()
                logger.warning(f"Removed existing socket: {s}")

        mem = str(memory_mb or self.profile["default_memory"])

        # NEW: keep artifacts together and poll for this pidfile
        pidfile = RUN_DIR / f"qemu-{vmid}.pid"
        try:
            if pidfile.exists():
                pidfile.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove existing pidfile {pidfile}: {e}")

        cmd = [
            "qemu-system-x86_64",
            # "-enable-kvm", # <----- added to test <------- not working
            "-m", mem,
            "-drive", f"file={overlay},format=qcow2,if=virtio,cache=writeback,discard=unmap",
            "-nic", "user,model=virtio-net-pci",
            "-vnc", f"unix:{vnc_sock}",
            "-qmp", f"unix:{qmp_sock},server,nowait",
            "-display", "none",
            "-daemonize",
            "-pidfile", str(pidfile),  # NEW: ask QEMU to write its PID
        ]
        

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

        # NEW: race-proof wait for pidfile to appear (qemu writes it after daemonize)
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
            "overlay": str(overlay),
            "vnc_socket": str(vnc_sock),
            "qmp_socket": str(qmp_sock),
            "started_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "pid": qemu_pid,  # NEW: included in return
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
        Make an *internal* qcow2 snapshot on the active overlay, then export it
        to a standalone qcow2 file: {user_id}__{os_type}__{vmid}.qcow2
        """
        overlay = self.overlay_path()
        if not overlay.exists():
            raise FileNotFoundError(f"Overlay not found: {overlay}")

        # 1) internal snapshot
        r = subprocess.run(
            ["qemu-img", "snapshot", "-c", name, str(overlay)],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            raise OnlineSnapshotError(f"Failed to create snapshot {name}:\n{r.stderr}")

        # 2) export that snapshot to a file you can boot from later
        out = SNAPSHOTS_PATH / f"{self.user_id}__{self.os_type}__{self.vmid}.qcow2"
        # overwrite is fine; keep one snapshot per VM if you want
        r2 = subprocess.run(
            ["qemu-img", "convert", "-O", "qcow2", "-s", name, str(overlay), str(out)],
            capture_output=True, text=True
        )
        if r2.returncode != 0:
            raise OnlineSnapshotError(f"Failed to export snapshot {name}:\n{r2.stderr}")

        logging.info(f"[snap] Created+exported snapshot '{name}' -> {out}")
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