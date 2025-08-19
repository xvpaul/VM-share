# tests/resilience/test_websockify_crash_cleanup.py
import io
from unittest.mock import MagicMock
import utils

def test_start_websockify_crash_triggers_cleanup(monkeypatch):
    """
    Simulate websockify process producing lines then exiting.
    Expect: store.update called on events, cleanup_vm invoked on disconnect/exit.
    """
    # capture command & emulate stdout
    started = {}

    class FakeProc:
        def __init__(self, cmd, **kwargs):
            started["cmd"] = cmd
            # both branches: connect then disconnect
            self.stdout = io.StringIO("Accepted connection\nClient closed connection\n")
            self.returncode = 0
        def poll(self):
            return self.returncode

    store = MagicMock()

    # stub popen and cleanup
    monkeypatch.setattr(utils.subprocess, "Popen", lambda *a, **k: FakeProc(*a, **k), raising=False)
    called = {"cleanup": 0}
    monkeypatch.setattr(utils, "cleanup_vm", lambda vmid, st: called.__setitem__("cleanup", called["cleanup"] + 1), raising=False)

    proc = utils.start_websockify("v1", 7777, "/tmp/v1.sock", store)
    assert proc is not None
    cmd = started["cmd"]
    assert cmd[0] == "websockify"
    assert "--unix-target" in cmd

    # allow monitor thread to consume lines
    import time
    time.sleep(0.05)

    assert store.update.call_count >= 1
    assert called["cleanup"] >= 1
