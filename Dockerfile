# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/root

# 1) Install QEMU (TCG), git (for noVNC), plus basics
RUN apt-get update && apt-get install -y --no-install-recommends \
      qemu-system-x86 qemu-utils git ca-certificates net-tools procps \
 && rm -rf /var/lib/apt/lists/*

# 2) Create the exact dirs your code expects for profiles + sockets
RUN mkdir -p \
      /tmp/qemu \
      /root/myapp/overlays/Alpine_Linux \
      /root/myapp/overlays/Tiny \
      /root/myapp/base_images/Alpine_Linux \
      /root/myapp/base_images/Tiny

# 3) Clone noVNC to ~/noVNC (so ~/noVNC/utils/novnc_proxy exists)
RUN git clone --depth=1 https://github.com/novnc/noVNC.git /root/noVNC

WORKDIR /app

# 4) Install Python dependencies + websockify
COPY requirements.txt .
RUN pip install -r requirements.txt && pip install websockify

# 5) Copy your app exactly as-is
COPY app ./app

# 6) Copy noVNC's core/ + vendor/ into your app's static folder
RUN mkdir -p /app/app/static/novnc-ui \
 && cp -r /root/noVNC/core /root/noVNC/vendor /app/app/static/novnc-ui/

# 7) Expose ports your code uses
EXPOSE 8000 6080 6900-6999

# 8) Run FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
