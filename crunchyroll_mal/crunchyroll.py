"""Crunchyroll undocumented API client for fetching watch history."""

import uuid

import requests

# Hardcoded client credentials (extracted from Crunchyroll apps).
_BASIC_TOKEN = "ZWE5Y21xbHRscXl6eWFuMXZkeTQ6LV9ZQ3BBRDVnc3hDaU9IWnpSTGdJQ1I4Z09XWGlsUVI="
_TOKEN_URL = "https://www.crunchyroll.com/auth/v1/token"
_API_BASE = "https://www.crunchyroll.com"
_USER_AGENT = (
    "Crunchyroll/3.54.5 Android/13 okhttp/4.12.0"
)


def authenticate(email, password):
    """Login with email/password, return (access_token, account_id, refresh_token)."""
    device_id = str(uuid.uuid4())
    resp = requests.post(
        _TOKEN_URL,
        headers={
            "Authorization": f"Basic {_BASIC_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _USER_AGENT,
        },
        data={
            "grant_type": "password",
            "username": email,
            "password": password,
            "scope": "offline_access",
            "device_id": device_id,
            "device_name": "automation",
            "device_type": "Linux",
        },
    )
    resp.raise_for_status()
    body = resp.json()
    return body["access_token"], body["account_id"], body["refresh_token"]


def fetch_watch_history(access_token, account_id, max_pages=20):
    """Fetch full watch history. Returns list of (series_title, episode_number) tuples."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": _USER_AGENT,
    }

    episodes = []
    for page in range(1, max_pages + 1):
        resp = requests.get(
            f"{_API_BASE}/content/v2/{account_id}/watch-history",
            headers=headers,
            params={"page": page, "page_size": 100, "locale": "en-US"},
        )
        if resp.status_code != 200:
            break

        items = resp.json().get("data", [])
        if not items:
            break

        for item in items:
            panel = item.get("panel", {})
            meta = panel.get("episode_metadata", {})
            title = meta.get("series_title") or panel.get("title", "")
            ep_num = meta.get("episode_number")
            season_num = meta.get("season_number", 1)
            if title and ep_num is not None:
                episodes.append({
                    "series_title": title,
                    "episode_number": int(ep_num),
                    "season_number": int(season_num),
                })

    return episodes


def aggregate_progress(episodes):
    """Group episodes by series, return {series_title: max_episode_number}."""
    progress = {}
    for ep in episodes:
        title = ep["series_title"]
        num = ep["episode_number"]
        if title not in progress or num > progress[title]:
            progress[title] = num
    return progress
