#!/usr/bin/env python3
"""Extract YouTube cookies from Chrome and save for yt-dlp."""

import sys
import browser_cookie3
from pathlib import Path
from http.cookiejar import MozillaCookieJar


def extract_youtube_cookies():
    """Extract YouTube cookies from Chrome."""

    # Output path
    cookie_dir = Path.home() / ".config/yt-dlp"
    cookie_dir.mkdir(parents=True, exist_ok=True)
    cookie_file = cookie_dir / "cookies.txt"

    print("Extracting cookies from Chrome...")
    print(f"Chrome profile: /home/muham/.config/google-chrome/Default")

    try:
        # Get cookies from Chrome
        # browser_cookie3 will try to decrypt using the secret service
        cj = browser_cookie3.chrome(domain_name=".youtube.com")

        # Also get google.com cookies (for authentication)
        cj_google = browser_cookie3.chrome(domain_name=".google.com")

        # Merge cookies
        for cookie in cj_google:
            cj.set_cookie(cookie)

        # Save in Mozilla format (compatible with yt-dlp)
        mozilla_jar = MozillaCookieJar(str(cookie_file))

        for cookie in cj:
            mozilla_jar.set_cookie(cookie)

        mozilla_jar.save(ignore_discard=True, ignore_expires=True)

        # Count YouTube cookies
        youtube_cookies = [c for c in cj if "youtube" in c.domain]
        google_cookies = [c for c in cj if "google" in c.domain]

        print(f"✓ Extracted {len(youtube_cookies)} YouTube cookies")
        print(f"✓ Extracted {len(google_cookies)} Google cookies")
        print(f"✓ Saved to: {cookie_file}")

        # Check if we have the important cookies
        important_cookies = ["LOGIN_INFO", "SSID", "APISID", "SAPISID", "HSID"]
        found = []
        for cookie in cj:
            if cookie.name in important_cookies:
                found.append(cookie.name)

        print(f"\nImportant auth cookies found: {', '.join(found) if found else 'None'}")

        if not found:
            print("\n⚠️  Warning: No authentication cookies found!")
            print("   Make sure you're logged into YouTube in Chrome.")
            return False

        return True

    except Exception as e:
        print(f"✗ Error extracting cookies: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = extract_youtube_cookies()
    sys.exit(0 if success else 1)
