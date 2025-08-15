# /app/methods/manager/ProcessManager.py
from __future__ import annotations
from typing import Dict, Optional
from subprocess import Popen
from threading import RLock

class ProcRegistry:
    def __init__(self) -> None:
        self._procs: Dict[str, Popen] = {}
        self._lock = RLock()

    def set(self, key: str, proc: Popen) -> None:
        with self._lock:
            self._procs[key] = proc

    def get(self, key: str) -> Optional[Popen]:
        with self._lock:
            return self._procs.get(key)

    def stop(self, key: str) -> None:
        with self._lock:
            p = self._procs.pop(key, None)
            if p and p.poll() is None:
                p.terminate()

    def stop_all(self) -> None:
        with self._lock:
            for k, p in list(self._procs.items()):
                if p and p.poll() is None:
                    p.terminate()
                self._procs.pop(k, None)


PROC_REGISTRY = ProcRegistry()

def get_proc_registry() -> ProcRegistry:
    return PROC_REGISTRY
