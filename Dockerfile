FROM python:3.11-slim
WORKDIR /VM_share/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-libvirt libpq-dev \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
COPY requirements.txt /VM_share/requirements.txt
# Remove 'libvirt-python' from requirements.txt (apt already provides it)
RUN grep -v '^libvirt-python' /VM_share/requirements.txt > /tmp/req.txt \
 && pip install --no-cache-dir -r /tmp/req.txt \
 && pip install --no-cache-dir websockify

COPY app /VM_share/app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
