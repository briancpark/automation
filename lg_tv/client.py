"""LG TV control via WebOS SSAP protocol (port 3000).

First run requires pairing: TV shows a popup, user clicks Allow.
Client key is stored in .tv_client_key for subsequent calls.
"""

import asyncio
import os
import time
from pathlib import Path

from aiowebostv import WebOsClient
import wakeonlan

TV_IP = os.environ.get("LG_TV_IP", "192.168.1.97")
TV_MAC = os.environ.get("LG_TV_MAC", "b4:b2:91:9c:78:01")
KEY_PATH = Path(__file__).resolve().parent / ".tv_client_key"
WAKE_TIMEOUT = 30  # seconds to wait for TV to boot

# App IDs on webOS
APP_IDS = {
    "netflix": "netflix-pjtr",
    "youtube": "youtube.leanback.v4-pjtr",
    "prime": "amazon-pjtr",
    "amazon": "amazon-pjtr",
    "hulu": "hulu",
    "disney": "com.disney.disneyplus-prod",
    "appletv": "com.apple.appletv",
    "jellyfin": "org.jellyfin.webos",
    "twitch": "tv.twitch.tv.starshot.lg",
    "crunchyroll": "com.crunchyroll.webapp",
    "hdmi1": "com.webos.app.hdmi1",
    "switch": "com.webos.app.hdmi1",
    "nintendo": "com.webos.app.hdmi1",
    "hdmi2": "com.webos.app.hdmi2",
    "hdmi3": "com.webos.app.hdmi3",
    "live": "com.webos.app.livetv",
}


def _load_key() -> str | None:
    if KEY_PATH.exists():
        return KEY_PATH.read_text().strip() or None
    return None


def _save_key(key: str):
    KEY_PATH.write_text(key)


async def _wake_and_connect() -> WebOsClient:
    """Send WoL, wait for TV to come online, return connected client."""
    client_key = _load_key()
    tv = WebOsClient(TV_IP, client_key=client_key)

    # Try connecting first — if TV is already on, skip WoL
    try:
        await tv.connect()
        if tv.client_key and tv.client_key != client_key:
            _save_key(tv.client_key)
        return tv
    except Exception:
        pass

    # TV is off — send WoL and wait
    print("TV is off, sending Wake-on-LAN...")
    wakeonlan.send_magic_packet(TV_MAC)

    deadline = time.time() + WAKE_TIMEOUT
    while time.time() < deadline:
        await asyncio.sleep(2)
        try:
            tv = WebOsClient(TV_IP, client_key=client_key)
            await tv.connect()
            if tv.client_key and tv.client_key != client_key:
                _save_key(tv.client_key)
            print("TV is on.")
            return tv
        except Exception:
            continue

    raise TimeoutError(f"TV did not respond within {WAKE_TIMEOUT}s after WoL")


async def _run(coro):
    """Wake TV if needed, connect, run coroutine, disconnect."""
    tv = await _wake_and_connect()
    try:
        result = await coro(tv)
    finally:
        await tv.disconnect()
    return result


def launch_app(app: str) -> dict:
    app_id = APP_IDS.get(app.lower(), app)

    async def _launch(tv):
        await tv.launch_app(app_id)
        return {"ok": True, "app": app_id}

    return asyncio.run(_run(_launch))


def power_off() -> dict:
    async def _off(tv):
        await tv.power_off()
        return {"ok": True}

    return asyncio.run(_run(_off))


def set_volume(level: int) -> dict:
    async def _vol(tv):
        await tv.set_volume(max(0, min(100, level)))
        return {"ok": True, "volume": level}

    return asyncio.run(_run(_vol))


def mute(muted: bool = True) -> dict:
    async def _mute(tv):
        await tv.set_mute(muted)
        return {"ok": True, "muted": muted}

    return asyncio.run(_run(_mute))


def get_status() -> dict:
    async def _status(tv):
        info = await tv.get_software_info()
        vol = await tv.get_volume()
        app = await tv.get_current_app()
        return {
            "ok": True,
            "app": app,
            "volume": vol,
            "software": info,
        }

    return asyncio.run(_run(_status))


def list_apps() -> dict:
    async def _list(tv):
        apps = await tv.get_apps()
        return {"ok": True, "apps": [{"id": a.get("id"), "title": a.get("title")} for a in apps]}

    return asyncio.run(_run(_list))
