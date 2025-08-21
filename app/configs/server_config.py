# app/configs/server_config.py
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class WSSettings:
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    WS_GATEWAY_BASE: str = os.getenv("WS_GATEWAY_BASE", "ws://gateway:6080/ws")  # set to wss://… in prod
    VNC_SOCK_DIR: str = os.getenv("VNC_SOCK_DIR", "/run/vmshare/vnc")
    SPICE_SOCK_DIR: str = os.getenv("SPICE_SOCK_DIR", "/run/vmshare/spice")
    DEFAULT_BACKEND: str = os.getenv("DEFAULT_BACKEND", "unix")  # unix|tcp
    SESSION_TTL: int = int(os.getenv("SESSION_TTL", "300"))
    TCP_HOST: str = os.getenv("TCP_HOST", "127.0.0.1")
    TCP_PORT: int = int(os.getenv("TCP_PORT", "5901"))
    ONE_TIME_TOKENS: bool = os.getenv("ONE_TIME_TOKENS", "0") == "1"

ws_settings = WSSettings()


SERVER_HOST = '5.101.67.252/' #"83.69.248.229"
