import os
import logging

LOG_DIR = '/root/myapp/logs/'
LOG_NAME = 'logs.log'
log_file_path = os.path.join(LOG_DIR, LOG_NAME)

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True  # ensure config applies even if uvicorn/etc touched logging
)
