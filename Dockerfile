# VM_share/Dockerfile
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

WORKDIR /VM_share/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev make \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /VM_share/requirements.txt
RUN pip install --no-cache-dir -r /VM_share/requirements.txt

COPY app /VM_share/app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
