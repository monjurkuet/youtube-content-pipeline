#!/bin/bash
set -e

# Start the VPN HTTP CONNECT proxy inside the binancevpn namespace
# This script waits for DNS to be available before starting the proxy

NAMESPACE="binancevpn"
PROXY_SCRIPT="/home/administrator/githubrepo/youtube-content-pipeline/scripts/vpn_proxy.py"

# Wait for DNS to be available inside the namespace
echo "Waiting for DNS resolution inside $NAMESPACE namespace..."
for i in $(seq 1 30); do
    if sudo ip netns exec "$NAMESPACE" timeout 3 python3 -c "
import socket
try:
    socket.getaddrinfo('www.youtube.com', 443)
    print('DNS_OK')
except Exception:
    pass
" 2>/dev/null | grep -q DNS_OK; then
        echo "DNS is ready after ${i}s"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARNING: DNS still not ready after 30s, starting anyway..."
    fi
    sleep 1
done

# Start the proxy
echo "Starting VPN HTTP CONNECT proxy..."
exec sudo ip netns exec "$NAMESPACE" /usr/bin/python3 "$PROXY_SCRIPT"