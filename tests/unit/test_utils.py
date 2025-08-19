import io
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient  # not strictly needed here, but OK
import utils  # thanks to your conftest path shim / cwd change

# ---------------------------
# find_free_port / _to_int
# ---------------------------

def test_find_free_port_returns_int():
    port = utils.find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535

def test__to_int_variants():
    assert utils._to_int("123") == 123
    assert utils._to_int(456) == 456
    assert utils._to_int("") is None
    assert utils._to_int(None) is None
    assert utils._to_int("x") is None

# ---------------------------
# cleanup_vm
# ---------------------------

def test_cleanup_vm_no_session_logs_and_returns(caplog):
    store = MagicMock()
    store.get.return_value = None
    utils.cleanup_vm("vm-missing", store)
    assert any("No active session" in r.message for r in caplog.records)
    store.delete.assert_not_called()

def test_cleanup_vm_unknown_os_type_deletes_session(monkeypatch, caplog):
    # No overlay_path; os_type not in profiles -> delete session and return
    store = MagicMock()
    store.get.return_value = {"user_id": "u", "os_type": "weirdos"}
    # Empty profiles to force unknown
    monkeypatch.setattr(utils.vm_profiles, "VM_PROFILES", {}, raising=False)
    utils.cleanup_vm("vm-1", store)
    store.delete.assert_called_once_with("vm-1")
    assert any("Unknown/missing os_type" in r.message for r in caplog.records)

def test_cleanup_vm_happy_with_pids(monkeypatch, tmp_path):
    # Prepare temp RUN_DIR and overlay file
    monkeypatch.setattr(utils, "RUN_DIR", tmp_path, raising=False)
    overlay = tmp_path / "ovl.qcow2"
    overlay.write_text("dummy")

    # Also create expected sockets to be removed
    (tmp_path / "vnc-vm-2.sock").write_text("")
    (tmp_path / "qmp-vm-2.sock").write_text("")

    # Session has overlay_path and PIDs (as strings)
    store = MagicMock()
    store.get.return_value = {
        "user_id": "u2",
        "os_type": "debian",
        "overlay_path": str(overlay),
        "qemu_pid": "1111",
        "websockify_pid": "2222",
    }

    killed = []
    def fake_kill(pid, sig):
        killed.append((int(pid), sig))
    monkeypatch.setattr(utils.os, "kill", fake_kill, raising=False)

    # Ensure pkill path NOT used when qemu_pid present
    ran = []
    def fake_run(cmd, check=False):
        ran.append(cmd)
    monkeypatch.setattr(utils.subprocess, "run", fake_run, raising=False)

    utils.cleanup_vm("vm-2", store)

    # Both processes should be signaled
    assert (1111, 15) in killed and (2222, 15) in killed
    # Overlay removed; sockets removed
    assert not overlay.exists()
    assert not (tmp_path / "vnc-vm-2.sock").exists()
    assert not (tmp_path / "qmp-vm-2.sock").exists()
    # pkill not used
    assert ran == []
    # session deleted at the end
    store.delete.assert_called_once_with("vm-2")

def test_cleanup_vm_no_qemu_pid_uses_pkill(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "RUN_DIR", tmp_path, raising=False)
    overlay = tmp_path / "ovl2.qcow2"
    overlay.write_text("x")

    store = MagicMock()
    store.get.return_value = {
        "user_id": "u3",
        "os_type": "debian",
        "overlay_path": str(overlay),
        "websockify_pid": "3000",  # qemu_pid missing -> pkill fallback
    }

    # Stub os.kill and capture calls
    killed = []
    monkeypatch.setattr(utils.os, "kill", lambda pid, sig: killed.append((int(pid), sig)), raising=False)

    ran = []
    monkeypatch.setattr(utils.subprocess, "run", lambda cmd, check=False: ran.append(cmd), raising=False)

    utils.cleanup_vm("vm-3", store)

    # websockify was killed, qemu not (unknown); pkill used twice
    assert (3000, 15) in killed
    assert any(cmd[:2] == ["pkill", "-f"] for cmd in ran) and len(ran) >= 2
    assert not overlay.exists()
    store.delete.assert_called_once_with("vm-3")

# ---------------------------
# start_websockify
# ---------------------------

def test_start_websockify_spawns_and_monitors(monkeypatch):
    # Fake store that records updates
    store = MagicMock()

    # Capture Popen invocation and feed lines to the monitor
    started = {}
    class FakeProc:
        def __init__(self, cmd, **kwargs):
            started["cmd"] = cmd
            # Simulate stdout emitting lines that trigger both branches
            self.stdout = io.StringIO(
                "Accepted connection\n"
                "Client closed connection\n"
            )
            self.returncode = 0
        def poll(self):
            return self.returncode

    monkeypatch.setattr(utils.subprocess, "Popen", lambda *a, **k: FakeProc(*a, **k), raising=False)

    # Prevent real cleanup side-effects; just record calls
    called_cleanup = {"count": 0}
    monkeypatch.setattr(utils, "cleanup_vm", lambda vmid, st: called_cleanup.__setitem__("count", called_cleanup["count"] + 1), raising=False)

    proc = utils.start_websockify("vmA", 7001, "/tmp/vmA.sock", store)
    assert proc is not None
    # Assert the command basics
    cmd = started["cmd"]
    assert cmd[0] == "websockify"
    assert "--web" in cmd and "--unix-target" in cmd
    assert f"0.0.0.0:7001" in cmd

    # Give the monitor thread a tiny moment to process lines
    import time; time.sleep(0.05)

    # store.update should have been called at least once on connect/disconnect
    assert store.update.call_count >= 1
    # cleanup_vm should have been triggered (on disconnect and/or finalizer)
    assert called_cleanup["count"] >= 1
