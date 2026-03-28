"""LG TV control via WebOS SSAP protocol (port 3000).

First run requires pairing: TV shows a popup, user clicks Allow.
Client key is stored in .tv_client_key for subsequent calls.
"""

import asyncio
import os
from pathlib import Path

from aiowebostv import WebOsClient

TV_IP = os.environ.get("LG_TV_IP", "192.168.1.97")
KEY_PATH = Path(__file__).resolve().parent / ".tv_client_key"

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


async def _run(coro):
    """Connect, run a coroutine, disconnect."""
    client_key = _load_key()
    tv = WebOsClient(TV_IP, client_key=client_key)
    await tv.connect()
    # Save updated client key after (re)pairing
    if tv.client_key and tv.client_key != client_key:
        _save_key(tv.client_key)
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
