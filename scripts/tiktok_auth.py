"""One-time TikTok login: saves a refresh token to .env as TT_REFRESH_TOKEN.

Run on your own machine (it opens a browser):
    python scripts/tiktok_auth.py

Needs TT_CLIENT_KEY and TT_CLIENT_SECRET in .env, and the Desktop redirect URI below registered in the
TikTok app's Login Kit settings. Sign in as the TikTok account the clips should be posted to.
"""
from __future__ import annotations

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

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
PORT = 8723
REDIRECT_URI = f"http://localhost:{PORT}/callback/"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "user.info.basic,video.upload,video.publish"


def read_env(path: Path = ENV) -> dict:
    if not path.exists():
        return {}
    pairs = (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
             if "=" in line and not line.lstrip().startswith("#"))
    return {key.strip(): value.strip() for key, value in pairs}


def write_env_value(key: str, value: str, path: Path = ENV) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith(f"{key}=")] + [f"{key}={value}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    return verifier, hashlib.sha256(verifier.encode()).hexdigest()  # TikTok desktop expects hex, not base64


def _server(state: str) -> tuple[http.server.HTTPServer, dict]:
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                return
            result["code"] = query.get("code", [None])[0]
            result["error"] = query.get("error_description", query.get("error", [None]))[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and return to the terminal.")

        def log_message(self, *args):
            pass

    return http.server.HTTPServer(("127.0.0.1", PORT), Handler), result


def main() -> int:
    env = read_env()
    key, secret = env.get("TT_CLIENT_KEY"), env.get("TT_CLIENT_SECRET")
    if not key or not secret or "paste_" in key + secret:
        print(f"error: set TT_CLIENT_KEY and TT_CLIENT_SECRET in {ENV}")
        return 2
    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce()
    try:
        server, result = _server(state)
    except OSError as exc:
        print(f"error: cannot listen on port {PORT}: {exc}")
        return 2
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_key": key, "scope": SCOPES, "response_type": "code", "redirect_uri": REDIRECT_URI,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
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
        "client_key": key, "client_secret": secret, "code": result["code"], "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI, "code_verifier": verifier}).encode()
    request = urllib.request.Request(TOKEN_URL, data=body,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            tokens = json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        print(f"error: token exchange failed: {type(exc).__name__}: {exc}")
        return 1
    refresh = tokens.get("refresh_token")
    if not refresh:
        print(f"error: TikTok returned no refresh token: {tokens.get('error_description') or tokens.get('error')}")
        return 1
    granted = set((tokens.get("scope") or "").split(","))
    missing = set(SCOPES.split(",")) - granted
    if missing:
        print(f"warning: these scopes were not granted: {', '.join(sorted(missing))}")
    write_env_value("TT_REFRESH_TOKEN", refresh)
    print(f"Saved TT_REFRESH_TOKEN to {ENV}. Copy it into the repo's TT_REFRESH_TOKEN Actions secret "
          f"(valid for about {int(tokens.get('refresh_expires_in', 0)) // 86400} days).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
