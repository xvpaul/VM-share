# tests/chaos/test_fs_chaos.py
from unittest.mock import MagicMock
import utils

def test_overlay_unlink_failure_is_logged_but_cleanup_continues(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(utils, "RUN_DIR", tmp_path, raising=False)
    ovl = tmp_path / "ovl.qcow2"
    ovl.write_text("x")

    store = MagicMock()
    store.get.return_value = {"user_id":"u","os_type":"debian","overlay_path": str(ovl)}
    # Make unlink raise
    class E(Exception): pass
    def bad_unlink():
        raise E("fs error")
    monkeypatch.setattr(type(ovl), "unlink", lambda self=ovl: bad_unlink(), raising=False)

    # pkill no‑op
    monkeypatch.setattr(utils.subprocess, "run", lambda *a, **k: None, raising=False)

    utils.cleanup_vm("foo", store)
    # it should log but not crash; still remove session
    assert any("Failed to delete overlay" in r.message for r in caplog.records)
    store.delete.assert_called_once_with("foo")
