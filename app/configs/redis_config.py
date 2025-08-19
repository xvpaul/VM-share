# /configs/redis_config.py
import os, redis
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
def get_redis() -> redis.Redis:
    # decode_responses=True → plain str in/out
    return redis.from_url(REDIS_URL, decode_responses=True)
