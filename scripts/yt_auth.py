"""One-time YouTube OAuth consent: prints a refresh token for the YT_REFRESH_TOKEN secret.

Run on your own machine (it opens a browser):
    python3 scripts/yt_auth.py [--client ~/secrets/yt_client.json]

Sign in as the Google account that owns the channel, and pick that channel if asked.
Stdlib only. The token is printed to the terminal and never written to disk.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _wait_for_code(state: str) -> tuple[http.server.HTTPServer, dict]:
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                return
            result["code"] = query.get("code", [None])[0]
            result["error"] = query.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and return to the terminal.")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    return server, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Get a YouTube refresh token")
    parser.add_argument("--client", default="~/secrets/yt_client.json", help="OAuth Desktop client JSON")
    args = parser.parse_args(argv)
    client_path = Path(args.client).expanduser()
    try:
        client = json.loads(client_path.read_text(encoding="utf-8"))["installed"]
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: cannot read a Desktop client from {client_path}: {exc}")
        return 2

    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce()
    server, result = _wait_for_code(state)
    redirect_uri = f"http://127.0.0.1:{server.server_port}"
    url = client["auth_uri"] + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    print("Opening your browser. If it does not open, visit:\n" + url + "\n")
    webbrowser.open(url)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    thread.join(timeout=300)
    server.server_close()
    if result.get("error") or not result.get("code"):
        print(f"error: no authorization code received ({result.get('error') or 'timed out'})")
        return 1

    body = urllib.parse.urlencode({
        "client_id": client["client_id"], "client_secret": client["client_secret"], "code": result["code"],
        "code_verifier": verifier, "grant_type": "authorization_code", "redirect_uri": redirect_uri,
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(client["token_uri"], data=body), timeout=30) as resp:
            tokens = json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        print(f"error: token exchange failed: {type(exc).__name__}: {exc}")
        return 1
    refresh = tokens.get("refresh_token")
    if not refresh:
        print("error: Google returned no refresh token. Revoke the app at "
              "https://myaccount.google.com/permissions and run this again.")
        return 1
    print("YT_REFRESH_TOKEN (keep this secret; do not paste it into chat):\n")
    print(refresh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
