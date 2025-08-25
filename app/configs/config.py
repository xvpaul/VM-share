# config.py
from pathlib import Path
from types import SimpleNamespace
from dotenv import load_dotenv, find_dotenv
import os, logging, redis as _redis

# --- Load .env (doesn't override real env vars) ---
load_dotenv(find_dotenv(filename=".env"), override=False)

# --- tiny env helper ---
def env(name, default=None, *, required=False, cast=str):
    v = os.getenv(name, default)
    if required and (v is None or v == ""):
        raise RuntimeError(f"{name} is required but missing")
    if v is None:
        return None
    if cast is bool:
        return str(v).lower() in {"1", "true", "yes", "on"}
    if cast is int:
        return int(v)
    return v  # str

# ---------- core app config ----------
DATABASE_URL = env("DATABASE_URL", required=True)
DATABASE_STORAGE_CAPACITY = env("DATABASE_STORAGE_CAPACITY", 300, cast=int)
PORT         = env("PORT", 8000, cast=int)
DEBUG        = env("DEBUG", False, cast=bool)
SECRET_KEY   = env("SECRET_KEY", required=True)
ALGORITHM    = env("ALGORITHM")  # optional
ACCESS_TOKEN_EXPIRE_MINUTES = env("ACCESS_TOKEN_EXPIRE_MINUTES", 30, cast=int)
COOKIE_MAX_AGE = env("COOKIE_MAX_AGE", 604800, cast=int)

# uploads
MAX_ISO_BYTES = 5 * 1024 * 1024 * 1024  # 5 GiB
CHUNK_SIZE    = 1024 * 1024             # 1 MiB

# ---------- VM profiles ----------
VM_PROFILES = {
    "alpine": {
        "overlay_dir": Path("/root/myapp/overlays/Alpine"),
        "overlay_prefix": "alpine",
        "base_image": Path("/root/myapp/base_images/Alpine/alpine-base.qcow2"),
        "default_memory": 1024,
    },
    "tiny": {
        "overlay_dir": Path("/root/myapp/overlays/Tiny"),
        "overlay_prefix": "tiny",
        "base_image": Path("/root/myapp/base_images/Tiny/tinycore-base.qcow2"),
        "default_memory": 1024,
    },
    "ubuntu": {
        "overlay_dir": Path("/root/myapp/overlays/Ubuntu"),
        "overlay_prefix": "ubuntu",
        "base_image": Path("/root/myapp/base_images/Ubuntu/ubuntu20-base.qcow2"),
        "default_memory": 2048,
    },
    "custom": {
        "prefix": "{uid}.iso",
        "base_image": Path("/root/myapp/custom/"),
        "default_memory": 2048
        # e.g. Path("/root/myapp/custom/{uid}.iso")
    },
    # "lubuntu": {
    #     "overlay_dir": Path("/root/myapp/overlays/lubuntu"),
    #     "overlay_prefix": "lubuntu",
    #     "base_image": Path("/root/myapp/base_images/Lubuntu/lubuntu-base.qcow2"),
    #     "default_memory": 2048,
    # },
}
SNAPSHOTS_PATH = Path("/root/myapp/snapshots/")

# ---------- Redis ----------
REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6379/0")
def get_redis() -> _redis.Redis:
    # decode_responses=True → plain str in/out
    return _redis.from_url(REDIS_URL, decode_responses=True)

# ---------- Server / gateway ----------
SERVER_HOST     = env("SERVER_HOST", "5.101.67.252")
WS_GATEWAY_BASE = env("WS_GATEWAY_BASE", "ws://gateway:6080/ws")  # set to wss://… in prod
VNC_SOCK_DIR    = env("VNC_SOCK_DIR", "/run/vmshare/vnc")
SPICE_SOCK_DIR  = env("SPICE_SOCK_DIR", "/run/vmshare/spice")
DEFAULT_BACKEND = env("DEFAULT_BACKEND", "unix")  # unix|tcp
SESSION_TTL     = env("SESSION_TTL", 300, cast=int)
TCP_HOST        = env("TCP_HOST", "127.0.0.1")
TCP_PORT        = env("TCP_PORT", 5901, cast=int)
ONE_TIME_TOKENS = env("ONE_TIME_TOKENS", False, cast=bool)

# ---------- Logging ----------
LOG_DIR = env("LOG_DIR", "/root/myapp/logs/")
LOG_NAME = env("LOG_NAME", "logs.log")
log_file_path = os.path.join(LOG_DIR, LOG_NAME)
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)

# ---------- Pretty namespaces for simple imports ----------
config = SimpleNamespace(
    DATABASE_URL=DATABASE_URL,
    PORT=PORT,
    DEBUG=DEBUG,
    SECRET_KEY=SECRET_KEY,
    ALGORITHM=ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES=ACCESS_TOKEN_EXPIRE_MINUTES,
    COOKIE_MAX_AGE=COOKIE_MAX_AGE,
    MAX_ISO_BYTES=MAX_ISO_BYTES,
    CHUNK_SIZE=CHUNK_SIZE,
    env=env,
)

server = SimpleNamespace(
    SERVER_HOST=SERVER_HOST,
    WS_GATEWAY_BASE=WS_GATEWAY_BASE,
    VNC_SOCK_DIR=VNC_SOCK_DIR,
    SPICE_SOCK_DIR=SPICE_SOCK_DIR,
    DEFAULT_BACKEND=DEFAULT_BACKEND,
    SESSION_TTL=SESSION_TTL,
    TCP_HOST=TCP_HOST,
    TCP_PORT=TCP_PORT,
    ONE_TIME_TOKENS=ONE_TIME_TOKENS,
)

redis = SimpleNamespace(
    REDIS_URL=REDIS_URL,
    get=get_redis,
)

vm = SimpleNamespace(
    PROFILES=VM_PROFILES,
    SNAPSHOTS_PATH=SNAPSHOTS_PATH,
)

logs = SimpleNamespace(
    LOG_DIR=LOG_DIR,
    LOG_NAME=LOG_NAME,
    FILE=log_file_path,
    logging=logging,  # stdlib logging (already configured)
)

__all__ = ["server", "config", "redis", "vm", "logs"]
