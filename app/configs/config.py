# app/configs/config.py
from dotenv import load_dotenv, find_dotenv
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
