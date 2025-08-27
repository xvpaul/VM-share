# VM_share/Dockerfile
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

WORKDIR /VM_share/app

# --- system deps for building native wheels ---
# - pkg-config + python3-dev + gcc: compile C extensions
# - libvirt-dev + libxml2-dev: headers/libs for libvirt-python
# - libpq-dev: headers for psycopg2 (Postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config python3-dev gcc \
    libvirt-dev libxml2-dev \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# (optional) keep pip recent; helpful for many wheels
RUN pip install --upgrade pip

# If your app launches `websockify` as a subprocess, ensure the binary exists.
# Choose ONE of the following:
# A) via pip (lightweight):
RUN pip install --no-cache-dir websockify
# B) or via apt (includes novnc static files under /usr/share/novnc):
# RUN apt-get update && apt-get install -y --no-install-recommends websockify novnc && rm -rf /var/lib/apt/lists/*

# Install Python deps (now that build deps are present)
COPY requirements.txt /VM_share/requirements.txt
RUN pip install --no-cache-dir -r /VM_share/requirements.txt

# App code last (better layer caching)
COPY app /VM_share/app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
