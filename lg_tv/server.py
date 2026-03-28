"""HTTP relay server for LG TV control.

Exposes simple endpoints that Apple Shortcuts can call:
  GET /tv/launch?app=netflix
  GET /tv/volume?level=30
  GET /tv/mute
  GET /tv/unmute
  GET /tv/off
  GET /tv/status
  GET /tv/apps
"""

import os
import sys
from pathlib import Path

# Load .env
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import PlainTextResponse

app = FastAPI(title="LG TV Relay")


def _tv():
    from lg_tv import client
    return client


@app.get("/tv/launch")
def launch(app_name: str = Query(..., alias="app")):
    try:
        result = _tv().launch_app(app_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tv/volume")
def volume(level: int = Query(...)):
    try:
        return _tv().set_volume(level)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tv/mute")
def mute():
    try:
        return _tv().mute(True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tv/unmute")
def unmute():
    try:
        return _tv().mute(False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tv/off")
def power_off():
    try:
        return _tv().power_off()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tv/status")
def status():
    try:
        return _tv().get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tv/apps")
def apps():
    try:
        return _tv().list_apps()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("TV_SERVER_PORT", "8080"))
    uvicorn.run("lg_tv.server:app", host="0.0.0.0", port=port, reload=False)
