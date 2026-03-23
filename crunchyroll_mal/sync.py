"""Sync Crunchyroll watch history to MyAnimeList."""

import json
import os
import sys
import time
from pathlib import Path

from . import crunchyroll, mal

# Cache file to store CR title -> MAL ID mappings so we don't re-search every run.
_CACHE_PATH = Path(__file__).resolve().parent / ".title_cache.json"


def _env_required(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} not set. Add it to your .env file.")
    return value


def _load_cache():
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    return {}


def _save_cache(cache):
    _CACHE_PATH.write_text(json.dumps(cache, indent=2))


def run():
    cr_email = _env_required("CRUNCHYROLL_EMAIL")
    cr_password = _env_required("CRUNCHYROLL_PASSWORD")

    # Authenticate with Crunchyroll
    print("Authenticating with Crunchyroll...")
    try:
        cr_token, account_id, _ = crunchyroll.authenticate(cr_email, cr_password)
    except Exception as exc:
        print(f"Crunchyroll auth failed: {exc}", file=sys.stderr)
        return 1

    # Fetch watch history
    print("Fetching Crunchyroll watch history...")
    episodes = crunchyroll.fetch_watch_history(cr_token, account_id)
    if not episodes:
        print("No watch history found.")
        return 0

    progress = crunchyroll.aggregate_progress(episodes)
    print(f"Found {len(progress)} series in watch history.")

    # Get MAL access token
    try:
        mal_token = mal.get_access_token()
    except Exception as exc:
        print(f"MAL auth failed: {exc}", file=sys.stderr)
        return 1

    # Load title -> MAL ID cache
    cache = _load_cache()
    updated = 0
    skipped = 0
    failed = []

    for cr_title, max_ep in progress.items():
        # Check cache first
        cached = cache.get(cr_title)
        if cached:
            mal_id = cached["mal_id"]
            total_eps = cached.get("num_episodes", 0)
        else:
            # Search MAL
            try:
                results = mal.search_anime(mal_token, cr_title)
                time.sleep(0.5)  # rate limit
            except Exception as exc:
                print(f"  [FAIL] Search failed for '{cr_title}': {exc}")
                failed.append(cr_title)
                continue

            match = mal.best_match(cr_title, results)
            if not match:
                print(f"  [SKIP] No MAL match for '{cr_title}'")
                failed.append(cr_title)
                continue

            mal_id = match["id"]
            total_eps = match.get("num_episodes", 0)
            cache[cr_title] = {
                "mal_id": mal_id,
                "mal_title": match["title"],
                "num_episodes": total_eps,
            }
            print(f"  [MAP] '{cr_title}' -> '{match['title']}' (MAL ID: {mal_id})")

        # Update MAL
        try:
            mal.update_anime_status(mal_token, mal_id, max_ep, total_eps)
            updated += 1
            status = "completed" if total_eps and max_ep >= total_eps else "watching"
            print(f"  [OK] {cr_title}: ep {max_ep} ({status})")
            time.sleep(0.5)  # rate limit
        except Exception as exc:
            print(f"  [FAIL] Update failed for '{cr_title}': {exc}")
            failed.append(cr_title)

    _save_cache(cache)

    print(f"\nSync complete: {updated} updated, {skipped} skipped, {len(failed)} failed.")
    if failed:
        print("Failed titles:")
        for title in failed:
            print(f"  - {title}")

    return 0
