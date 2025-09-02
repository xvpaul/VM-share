server { listen 80; server_name vmshare.ru www.vmshare.ru; # --- General --- client_max_body_size 2G; # allow big file uploads # --- API (FastAPI backend) --- location /api/ { proxy_pass http://127.0.0.1:8000; proxy_http_version 1.1; # Stream uploads directly (no buffering in Nginx) proxy_request_buffering off; # Forward headers proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection $connection_upgrade; proxy_read_timeout 3600s; proxy_send_timeout 3600s; # Don’t buffer big downloads in memory proxy_buffering off; # --- CORS --- add_header 'Access-Control-Allow-Origin' 'https://vmshare.ru' always; add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always; add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always; # Preflight (OPTIONS) handler if ($request_method = OPTIONS) { add_header 'Access-Control-Allow-Origin' 'https://vmshare.ru'; add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS'; add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type'; add_header 'Access-Control-Max-Age' 86400; return 204; } } # --- Frontend (your web app / UI) --- location / { proxy_pass http://127.0.0.1:8000; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection $connection_upgrade; proxy_read_timeout 60s; proxy_send_timeout 60s; proxy_buffering on; proxy_buffers 8 16k; proxy_busy_buffers_size 32k; } }





root@xvhgxvhg6:~/myapp/monitoring# cat docker-compose.yml 
services:
  prometheus:
    image: prom/prometheus:latest
    network_mode: host
    volumes:
      - ./prom-config:/etc/prometheus:ro
      - ./prom-data:/var/lib/prometheus    # bind mount (chown 65534:65534)
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/var/lib/prometheus
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:latest
    network_mode: host
    pid: host
    volumes:
      - /:/host:ro,rslave
    command:
      - --path.rootfs=/host
    restart: unless-stopped

  grafana:
    image: grafana/grafana-oss:latest
    ports: ["3000:3000"]
    environment:
     # - GF_RENDERING_SERVER_URL=http://renderer:8081/render
     # - GF_RENDERING_CALLBACK_URL=http://grafana:3000/
     # - GF_LOG_FILTERS=rendering:debug
     # emb below set true from false server root and next are extras
      - GF_SERVER_ROOT_URL=http://localhost:3000
      - GF_SERVER_SERVE_FROM_SUB_PATH=false
      - GF_SERVER_DOMAIN=vmshare.ru
      - GF_SECURITY_ALLOW_EMBEDDING=true
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
    depends_on:
      - renderer
    volumes:
      - grafana-data:/var/lib/grafana
    # let containers resolve the host as "host.docker.internal"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped

  renderer:
    image: grafana/grafana-image-renderer:latest
    # port publish is optional; Grafana talks over the default bridge network
    ports: ["8081:8081"]
    environment:
      - ENABLE_METRICS=true
    restart: unless-stopped

volumes:
  grafana-data:





  