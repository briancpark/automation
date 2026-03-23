"""MyAnimeList API v2 client with OAuth2 PKCE token management."""

import json
import os
import secrets
import string
import time
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

_AUTH_URL = "https://myanimelist.net/v1/oauth2/authorize"
_TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
_API_BASE = "https://api.myanimelist.net/v2"

TOKEN_PATH = Path(__file__).resolve().parent / ".mal_tokens.json"


def _generate_pkce_verifier(length=128):
    chars = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(chars) for _ in range(length))


def _save_tokens(data):
    data["saved_at"] = int(time.time())
    TOKEN_PATH.write_text(json.dumps(data, indent=2))
    TOKEN_PATH.chmod(0o600)


def _load_tokens():
    if not TOKEN_PATH.exists():
        return None
    return json.loads(TOKEN_PATH.read_text())


def _get_local_ip():
    """Get the Pi's local IP address."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def authorize_interactive(client_id, client_secret="", redirect_host=None):
    """Run one-time OAuth2 PKCE flow. Opens a local server to catch the redirect."""
    if redirect_host is None:
        redirect_host = _get_local_ip()
    redirect_uri = f"http://{redirect_host}:8484/callback"

    verifier = _generate_pkce_verifier()
    state = secrets.token_urlsafe(16)

    auth_params = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "code_challenge": verifier,
        "code_challenge_method": "plain",
        "state": state,
        "redirect_uri": redirect_uri,
    })
    auth_url = f"{_AUTH_URL}?{auth_params}"

    print(f"\nOpen this URL in your browser to authorize:\n\n{auth_url}\n")

    code = None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal code
            qs = parse_qs(urlparse(self.path).query)
            code = qs.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorized! You can close this tab.</h1>")

        def log_message(self, format, *args):
            pass  # silence logs

    server = HTTPServer(("0.0.0.0", 8484), Handler)
    print(f"Waiting for authorization callback on {redirect_uri} ...")
    server.handle_request()
    server.server_close()

    if not code:
        raise RuntimeError("No authorization code received.")

    token_data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    if client_secret:
        token_data["client_secret"] = client_secret

    resp = requests.post(_TOKEN_URL, data=token_data)
    resp.raise_for_status()
    tokens = resp.json()
    tokens["client_id"] = client_id
    tokens["client_secret"] = client_secret
    _save_tokens(tokens)
    print("MAL tokens saved successfully.")
    return tokens


def get_access_token():
    """Load saved tokens, refreshing if expired."""
    tokens = _load_tokens()
    if not tokens:
        raise RuntimeError(
            "No MAL tokens found. Run the auth setup first:\n"
            "  python -m crunchyroll_mal.mal_auth_setup"
        )

    elapsed = int(time.time()) - tokens.get("saved_at", 0)
    if elapsed < tokens.get("expires_in", 0) - 300:
        return tokens["access_token"]

    # Refresh
    data = {
        "client_id": tokens["client_id"],
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    }
    if tokens.get("client_secret"):
        data["client_secret"] = tokens["client_secret"]

    resp = requests.post(_TOKEN_URL, data=data)
    resp.raise_for_status()
    new_tokens = resp.json()
    new_tokens["client_id"] = tokens["client_id"]
    new_tokens["client_secret"] = tokens.get("client_secret", "")
    _save_tokens(new_tokens)
    return new_tokens["access_token"]


def search_anime(access_token, query, limit=5):
    """Search MAL for anime by title. Returns list of {id, title, alt_titles, num_episodes}."""
    resp = requests.get(
        f"{_API_BASE}/anime",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "q": query[:64],  # MAL limits query to 64 chars
            "limit": limit,
            "fields": "alternative_titles,num_episodes,media_type,status",
        },
    )
    resp.raise_for_status()
    results = []
    for item in resp.json().get("data", []):
        node = item["node"]
        results.append({
            "id": node["id"],
            "title": node["title"],
            "title_en": node.get("alternative_titles", {}).get("en", ""),
            "synonyms": node.get("alternative_titles", {}).get("synonyms", []),
            "num_episodes": node.get("num_episodes", 0),
            "media_type": node.get("media_type", ""),
            "status": node.get("status", ""),
        })
    return results


def best_match(cr_title, mal_results, threshold=0.5):
    """Find the best MAL match for a Crunchyroll title using fuzzy matching."""
    if not mal_results:
        return None

    best = None
    best_score = 0.0
    cr_lower = cr_title.lower()

    for result in mal_results:
        candidates = [result["title"], result["title_en"]] + result["synonyms"]
        for candidate in candidates:
            if not candidate:
                continue
            score = SequenceMatcher(None, cr_lower, candidate.lower()).ratio()
            if score > best_score:
                best_score = score
                best = result

    if best_score >= threshold:
        return best
    return None


def update_anime_status(access_token, anime_id, episodes_watched, total_episodes=0):
    """Update the user's list entry for an anime."""
    data = {"num_watched_episodes": episodes_watched}

    if total_episodes and episodes_watched >= total_episodes:
        data["status"] = "completed"
    else:
        data["status"] = "watching"

    resp = requests.patch(
        f"{_API_BASE}/anime/{anime_id}/my_list_status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data,
    )
    resp.raise_for_status()
    return resp.json()


def get_user_animelist(access_token, status="watching", limit=1000):
    """Fetch the user's anime list."""
    results = []
    url = f"{_API_BASE}/users/@me/animelist"
    params = {
        "status": status,
        "limit": min(limit, 100),
        "fields": "list_status,num_episodes",
        "sort": "list_updated_at",
    }

    while url and len(results) < limit:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        resp.raise_for_status()
        body = resp.json()
        for item in body.get("data", []):
            results.append(item)
        url = body.get("paging", {}).get("next")
        params = None  # next URL includes params

    return results
