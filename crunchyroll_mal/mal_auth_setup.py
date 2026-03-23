"""One-time interactive setup for MyAnimeList OAuth2 tokens.

Usage:
    python -m crunchyroll_mal.mal_auth_setup
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crunchyroll_mal.mal import authorize_interactive


def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def main():
    _load_env()

    client_id = os.getenv("MAL_CLIENT_ID")
    client_secret = os.getenv("MAL_CLIENT_SECRET", "")

    if not client_id:
        print("MAL_CLIENT_ID not set. Add it to your .env file.")
        return 1

    authorize_interactive(client_id, client_secret)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
