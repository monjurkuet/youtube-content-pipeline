#!/usr/bin/env python3
"""Minimal HTTP CONNECT proxy for routing YouTube API traffic via ProtonVPN namespace.

Runs inside the binancevpn network namespace using /usr/bin/python3 (system Python).
Listens on 10.200.200.2:8888 (inside the namespace) for HTTP CONNECT requests
and relays them out through the ProtonVPN WireGuard tunnel.

Usage (run inside binancevpn ns):
  sudo ip netns exec binancevpn /usr/bin/python3 scripts/vpn_proxy.py
"""

import logging
import os
import socket
import select
import sys
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [VPN-PROXY] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vpn_proxy")

BIND_HOST = "10.200.200.2"
BIND_PORT = 8888
BUFFER_SIZE = 65536


def _relay(src, dst, direction, stream_id):
    """Relay data from src to dst until EOF."""
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    except Exception as e:
        logger.debug("[%s/%s] relay error: %s", stream_id, direction, e)
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle_connection(client_sock, addr):
    """Handle an HTTP CONNECT request."""
    stream_id = f"{addr[0]}:{addr[1]}"
    try:
        # Read the CONNECT request
        data = client_sock.recv(BUFFER_SIZE)
        if not data:
            return

        request_line = data.split(b"\r\n")[0].decode("utf-8", errors="replace")
        logger.info("[%s] <- %s", stream_id, request_line)

        parts = request_line.split()
        if len(parts) < 2:
            return

        method = parts[0].upper()

        if method == "CONNECT":
            # HTTPS tunnel: CONNECT host:port HTTP/1.1
            host_port = parts[1]
            host, _, port_str = host_port.partition(":")
            port = int(port_str) if port_str else 443

            logger.info("[%s] CONNECT tunnel: %s:%d", stream_id, host, port)

            # Connect to target via the VPN tunnel (namespace default route)
            # Resolve hostname from the HOST namespace since VPN ns has DNS issues
            try:
                import subprocess
                result = subprocess.run(
                    ["getent", "ahostsv4", host],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    resolved_ip = result.stdout.strip().split()[0]
                    logger.info("[%s] Resolved %s -> %s (host DNS)", stream_id, host, resolved_ip)
                    host = resolved_ip
            except Exception as e:
                logger.warning("[%s] DNS resolution from host failed: %s", stream_id, e)

            target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target.settimeout(30)
            target.connect((host, port))
            target.settimeout(None)

            # Send 200 response
            client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

            # Bidirectional relay
            threads = [
                threading.Thread(target=_relay, args=(client_sock, target, "C->T", stream_id), daemon=True),
                threading.Thread(target=_relay, args=(target, client_sock, "T->C", stream_id), daemon=True),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            logger.info("[%s] tunnel closed", stream_id)

        elif method in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
            # HTTP forward proxy (no caching, just relay)
            # Parse the absolute URL
            url = parts[1]
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if not parsed.hostname:
                logger.warning("[%s] Bad URL: %s", stream_id, url)
                return

            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query

            logger.info("[%s] HTTP proxy: %s://%s:%d%s", stream_id, parsed.scheme, host, port, path)

            # Rewrite request: replace absolute URL with path
            new_request = request_line.replace(url, path, 1)
            rewritten = new_request.encode() + b"\r\n" + data.split(b"\r\n", 1)[1]
            # Strip Proxy-* headers
            lines = rewritten.split(b"\r\n")
            clean_lines = []
            for line in lines:
                if line.lower().startswith(b"proxy-"):
                    continue
                clean_lines.append(line)
            rewritten = b"\r\n".join(clean_lines)

            # Connect and relay
            target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target.settimeout(30)
            target.connect((host, port))
            target.settimeout(None)

            # Send the rewritten request
            target.sendall(rewritten)

            # Relay response back
            client_sock.settimeout(30)
            try:
                while True:
                    data = target.recv(BUFFER_SIZE)
                    if not data:
                        break
                    client_sock.sendall(data)
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass
            except Exception as e:
                logger.debug("[%s] HTTP relay error: %s", stream_id, e)

            target.close()
            logger.info("[%s] HTTP proxy done", stream_id)

        else:
            logger.warning("[%s] Unknown method: %s", stream_id, method)

    except Exception as e:
        logger.error("[%s] Error: %s", stream_id, e)
    finally:
        try:
            client_sock.close()
        except OSError:
            pass


def main():
    logger.info("Starting VPN HTTP CONNECT proxy on %s:%d", BIND_HOST, BIND_PORT)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(None)
    server.bind((BIND_HOST, BIND_PORT))
    server.listen(64)
    logger.info("Proxy ready. Waiting for connections...")

    while True:
        try:
            client, addr = server.accept()
            thread = threading.Thread(
                target=handle_connection, args=(client, addr), daemon=True
            )
            thread.start()
        except Exception as e:
            logger.error("Accept error: %s", e)


if __name__ == "__main__":
    main()