#!/usr/bin/env python3
"""Extract YouTube/Google cookies from running Chrome instances via CDP.

Bypasses "Sign in to confirm" IP blocks by pulling cookies from actively
logged-in Chrome sessions via Chrome DevTools Protocol.

CDP Storage.getCookies returns ALL cookies including HttpOnly, Secure,
and SameSite ones that JavaScript cannot access.

Output formats:
  --format netscape  -> Mozilla cookies.txt (for yt-dlp --cookies)
  --format json      -> JSON array of cookie objects
  --format string    -> Cookie header string (for requests.Session / API)

Usage:
  python scripts/cdp_cookie_extractor.py --output ~/.config/yt-dlp/cookies.txt
  python scripts/cdp_cookie_extractor.py --port 9222 --output /tmp/cookies.txt
  python scripts/cdp_cookie_extractor.py --format string
  python scripts/cdp_cookie_extractor.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import websockets
except ImportError:
    print("ERROR: websockets package required. Install with: uv pip install websockets")
    sys.exit(1)

logger = logging.getLogger(__name__)

YOUTUBE_AUTH_COOKIES = {
    "LOGIN_INFO", "SSID", "APISID", "SAPISID", "HSID", "SID", "SIDCC",
    "__Secure-1PSID", "__Secure-3PSID",
    "__Secure-1PSIDTS", "__Secure-3PSIDTS",
    "__Secure-1PSIDCC", "__Secure-3PSIDCC",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
    "__Secure-OSID", "OSID",
    "VISITOR_INFO1_LIVE", "YSC", "GPS",
}

YOUTUBE_RELEVANT_DOMAINS = {
    ".youtube.com", "www.youtube.com", "youtube.com",
    ".google.com", "www.google.com", "google.com",
    "accounts.google.com", ".accounts.google.com",
    "ogs.google.com", ".ogs.google.com",
    "play.google.com", ".play.google.com",
    ".googleapis.com", ".googlevideo.com",
    ".gstatic.com", ".ytimg.com",
}


def _is_youtube_relevant(domain: str) -> bool:
    domain_lower = domain.lower().lstrip(".")
    for relevant in YOUTUBE_RELEVANT_DOMAINS:
        rel_lower = relevant.lower().lstrip(".")
        if domain_lower == rel_lower or domain_lower.endswith(rel_lower):
            return True
    return False


async def get_browser_ws_url(port: int) -> str | None:
    import urllib.request
    try:
        url = f"http://localhost:{port}/json/version"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("webSocketDebuggerUrl")
    except Exception as e:
        logger.debug(f"Failed to get WS URL from port {port}: {e}")
        return None


async def extract_cookies_from_cdp(port: int) -> list[dict[str, Any]]:
    ws_url = await get_browser_ws_url(port)
    if not ws_url:
        logger.warning(f"No WebSocket URL found for port {port}")
        return []
    try:
        async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
            resp = json.loads(await ws.recv())
            cookies = resp.get("result", {}).get("cookies", [])
            logger.info(f"Extracted {len(cookies)} cookies from port {port}")
            return cookies
    except Exception as e:
        logger.warning(f"Failed to extract cookies from port {port}: {e}")
        return []


async def extract_cookies_from_all_ports(ports: list[int] = None) -> list[dict[str, Any]]:
    if ports is None:
        ports = [9222, 9224, 9225]
    all_cookies: dict[str, dict[str, Any]] = {}
    for port in ports:
        cookies = await extract_cookies_from_cdp(port)
        for cookie in cookies:
            key = f"{cookie.get('domain', '')}:{cookie.get('name', '')}:{cookie.get('path', '/')}"
            existing = all_cookies.get(key)
            if existing is None:
                all_cookies[key] = cookie
            else:
                if cookie.get("expires", -1) > existing.get("expires", -1):
                    all_cookies[key] = cookie
    return list(all_cookies.values())


def filter_youtube_cookies(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in cookies if _is_youtube_relevant(c.get("domain", ""))]


def get_auth_cookie_names(cookies: list[dict[str, Any]]) -> list[str]:
    return [c["name"] for c in cookies if c["name"] in YOUTUBE_AUTH_COOKIES]


def to_netscape_format(cookies: list[dict[str, Any]]) -> str:
    lines = [
        "# Netscape HTTP Cookie File",
        "# https://curl.se/docs/http-cookies.html",
        "# This is a generated file! Do not edit.",
        "",
    ]
    sorted_cookies = sorted(cookies, key=lambda c: (c.get("domain", ""), c.get("name", "")))
    for c in sorted_cookies:
        domain = c.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        expires = c.get("expires", -1)
        if expires == -1:
            expires = int(datetime.now(timezone.utc).timestamp()) + 86400 * 365
        else:
            expires = int(expires)
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
    return "\n".join(lines) + "\n"


def to_cookie_string(cookies: list[dict[str, Any]]) -> str:
    return "; ".join(f'{c["name"]}={c["value"]}' for c in cookies)


def create_requests_session(cookies: list[dict[str, Any]]):
    import requests as req_lib
    session = req_lib.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    for c in cookies:
        domain = c.get("domain", "").lstrip(".")
        secure = c.get("secure", False)
        path = c.get("path", "/")
        session.cookies.set(c["name"], c["value"], domain=domain, path=path, secure=secure)
    return session


def write_netscape_cookies(cookies: list[dict[str, Any]], output_path: Path) -> int:
    content = to_netscape_format(cookies)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    return len(cookies)


def write_metadata(cookies, auth_cookies, metadata_path, ports):
    yt_count = len([c for c in cookies if "youtube" in c.get("domain", "")])
    google_count = len([c for c in cookies if "google" in c.get("domain", "")])
    metadata = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "source": "cdp",
        "ports": ports,
        "youtube_count": yt_count,
        "google_count": google_count,
        "auth_cookies": auth_cookies,
        "has_auth": bool(auth_cookies),
        "total_cookies": len(cookies),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2))


async def main():
    parser = argparse.ArgumentParser(description="Extract YouTube cookies from Chrome via CDP")
    parser.add_argument("--ports", nargs="+", type=int, default=[9222, 9224, 9225])
    parser.add_argument("--output", "-o", type=Path, default=None)
    parser.add_argument("--format", "-f", choices=["netscape", "json", "string"], default="netscape")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all-domains", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    print(f"Extracting cookies from CDP ports: {args.ports}")
    all_cookies = await extract_cookies_from_all_ports(args.ports)
    print(f"Total cookies extracted: {len(all_cookies)}")

    if not all_cookies:
        print("ERROR: No cookies found. Are Chrome instances running on those ports?")
        sys.exit(1)

    if not args.all_domains:
        yt_cookies = filter_youtube_cookies(all_cookies)
        print(f"YouTube/Google cookies: {len(yt_cookies)}")
    else:
        yt_cookies = all_cookies

    auth_names = get_auth_cookie_names(yt_cookies)
    unique_auth = sorted(set(auth_names))
    print(f"Auth cookies: {unique_auth}")

    if "LOGIN_INFO" not in auth_names:
        print("WARNING: LOGIN_INFO cookie not found - user may not be logged into YouTube")
    else:
        print(f"YouTube auth session detected ({len(unique_auth)} unique auth cookie types)")

    if args.dry_run:
        print("[DRY RUN] No files written.")
        return

    output_path = args.output or Path.home() / ".config" / "yt-dlp" / "cookies.txt"
    metadata_path = output_path.parent / ".cookie_metadata.json"

    if args.format == "netscape":
        count = write_netscape_cookies(yt_cookies, output_path)
        write_metadata(yt_cookies, unique_auth, metadata_path, args.ports)
        print(f"Wrote {count} cookies to {output_path}")
        print(f"   Metadata: {metadata_path}")
    elif args.format == "json":
        json.dump(yt_cookies, sys.stdout, indent=2, default=str)
        print()
    elif args.format == "string":
        print(to_cookie_string(yt_cookies))


if __name__ == "__main__":
    asyncio.run(main())
