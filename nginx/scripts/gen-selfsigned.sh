#!/usr/bin/env bash
set -euo pipefail
IP="${1:-$(curl -s ifconfig.me || echo 127.0.0.1)}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/certs"
mkdir -p "$DIR"
echo "Generating self-signed cert for IP: $IP -> $DIR"

openssl req -x509 -nodes -newkey rsa:4096 -days 365 \
  -keyout "$DIR/vmshare.key" \
  -out   "$DIR/vmshare.crt" \
  -subj "/CN=${IP}" \
  -addext "subjectAltName = IP:${IP},DNS:vmshare.local"

[ -f "$DIR/dhparam.pem" ] || openssl dhparam -out "$DIR/dhparam.pem" 2048
echo "Done."
