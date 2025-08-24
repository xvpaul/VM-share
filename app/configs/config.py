# app/configs/config.py
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
import os

# Load .env if present (won't override real env vars)
load_dotenv(find_dotenv(filename=".env"), override=False)

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

# Your config values
DATABASE_URL = env("DATABASE_URL", required=True)
PORT         = env("PORT", 8000, cast=int)
DEBUG        = env("DEBUG", False, cast=bool)
SECRET_KEY   = env("SECRET_KEY", required=True)
ALGORITHM    = env("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = env("ACCESS_TOKEN_EXPIRE_MINUTES", 30, cast=int)
COOKIE_MAX_AGE = env("COOKIE_MAX_AGE", 604800, cast=int)


# 5 GiB cap by default (tune as you like)
MAX_ISO_BYTES = 5 * 1024 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024  # 1 MiB


# app/configs/vm_profiles.py

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
    "lubuntu": {
        "overlay_dir": Path("/root/myapp/overlays/lubuntu"),
        "overlay_prefix": "lubuntu",
        "base_image": Path("/root/myapp/base_images/Lubuntu/lubuntu-base.qcow2"),
        "default_memory": 2048,
    },
    "ubuntu": {
        "overlay_dir": Path("/root/myapp/overlays/Ubuntu"),
        "overlay_prefix": "ubuntu",
        "base_image": Path("/root/myapp/base_images/Ubuntu/ubuntu20-base.qcow2"),
        "default_memory": 2048,
    },
    "custom": {
        "prefix": '{uid}.iso',
        "base_image": Path("/root/myapp/custom/")
        # "base_image": Path("/root/myapp/custom/{uid}.iso"), <---- prev
    }
}

SNAPSHOTS_PATH = Path("/root/myapp/snapshots")