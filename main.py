#!/usr/bin/env python3
"""Entry point for all shortcut automations."""

import argparse
import os
import sys
from pathlib import Path


def _load_env():
    """Load .env file from the repo root."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main():
    _load_env()

    parser = argparse.ArgumentParser(description="Shortcut automations")
    subparsers = parser.add_subparsers(dest="command")

    # tesla-tts
    tts_parser = subparsers.add_parser(
        "tesla-tts", help="TeslaMate latest drive TTS summary"
    )
    tts_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include full detailed output for the latest drive",
    )

    # tesla-weekly
    subparsers.add_parser(
        "tesla-weekly", help="Weekly driving stats recap"
    )

    # tesla-morning
    morning_parser = subparsers.add_parser(
        "tesla-morning", help="Morning routine Tesla summary"
    )
    morning_parser.add_argument("--lat", type=float, required=True, help="Latitude")
    morning_parser.add_argument("--lon", type=float, required=True, help="Longitude")
    morning_parser.add_argument("--temp", type=float, default=None, help="Current temp in °F (from Siri, skips weather API)")

    # pollen
    pollen_parser = subparsers.add_parser(
        "pollen", help="Current pollen levels from Google Pollen API"
    )
    pollen_parser.add_argument("--lat", type=float, required=True, help="Latitude")
    pollen_parser.add_argument("--lon", type=float, required=True, help="Longitude")

    # chargepoint
    cp_parser = subparsers.add_parser(
        "chargepoint", help="Join ChargePoint waitlist"
    )
    cp_parser.add_argument(
        "-t", "--until-time", type=int, default=23,
        help="Stay on waitlist until this hour [0-23]. Default 23."
    )

    # charge-cost
    cc_parser = subparsers.add_parser(
        "charge-cost", help="EV savings report vs equivalent gas cars"
    )
    cc_parser.add_argument(
        "--weeks", type=int, default=30,
        help="Number of weeks to look back (default: 8)"
    )
    cc_parser.add_argument(
        "--region", type=str, default="CA",
        help="Gas price region: CA (California), US (national), WC (West Coast). Default: CA"
    )

    # crunchyroll-mal
    subparsers.add_parser(
        "crunchyroll-mal", help="Sync Crunchyroll watch history to MyAnimeList"
    )

    # lg-tv
    tv_parser = subparsers.add_parser("lg-tv", help="Control LG TV")
    tv_sub = tv_parser.add_subparsers(dest="tv_command")
    tv_launch = tv_sub.add_parser("launch", help="Launch an app")
    tv_launch.add_argument("app", help="App name: netflix, youtube, prime, disney, jellyfin, appletv, twitch, switch (HDMI1), hdmi2, live")
    tv_vol = tv_sub.add_parser("volume", help="Set volume (0-100)")
    tv_vol.add_argument("level", type=int)
    tv_sub.add_parser("mute", help="Mute TV")
    tv_sub.add_parser("unmute", help="Unmute TV")
    tv_sub.add_parser("off", help="Power off TV")
    tv_sub.add_parser("status", help="Get current TV status")
    tv_sub.add_parser("apps", help="List installed apps")

    # tv-server
    server_parser = subparsers.add_parser("tv-server", help="Start LG TV HTTP relay server")
    server_parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "tesla-tts":
        from tesla.tts import fetch_latest_drive, format_latest_drive

        try:
            line = fetch_latest_drive()
            print(format_latest_drive(line, verbose=args.verbose))
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.command == "tesla-weekly":
        from tesla.weekly import run

        return run()

    if args.command == "tesla-morning":
        from tesla.morning import run

        return run(args.lat, args.lon, temp_f=args.temp)

    if args.command == "pollen":
        from pollen.scrape import run

        return run(args.lat, args.lon)

    if args.command == "chargepoint":
        from chargepoint.waitlist import run

        return run(until_time=args.until_time)

    if args.command == "charge-cost":
        from tesla.charge_cost import run

        return run(weeks_back=args.weeks, region_code=args.region)

    if args.command == "crunchyroll-mal":
        from crunchyroll_mal.sync import run

        return run()

    if args.command == "lg-tv":
        import json
        from lg_tv import client as tv

        if args.tv_command == "launch":
            print(json.dumps(tv.launch_app(args.app), indent=2))
        elif args.tv_command == "volume":
            print(json.dumps(tv.set_volume(args.level), indent=2))
        elif args.tv_command == "mute":
            print(json.dumps(tv.mute(True), indent=2))
        elif args.tv_command == "unmute":
            print(json.dumps(tv.mute(False), indent=2))
        elif args.tv_command == "off":
            print(json.dumps(tv.power_off(), indent=2))
        elif args.tv_command == "status":
            print(json.dumps(tv.get_status(), indent=2))
        elif args.tv_command == "apps":
            result = tv.list_apps()
            for a in result.get("apps", []):
                print(f"{a['id']:50s} {a['title']}")
        else:
            tv_parser.print_help()
        return 0

    if args.command == "tv-server":
        import os
        os.environ["TV_SERVER_PORT"] = str(args.port)
        import uvicorn
        uvicorn.run("lg_tv.server:app", host="0.0.0.0", port=args.port, reload=False)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
