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

    # morning
    morning_parser = subparsers.add_parser(
        "morning", help="Morning routine Tesla summary"
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

    if args.command == "morning":
        from tesla.morning import run

        return run(args.lat, args.lon, temp_f=args.temp)

    if args.command == "pollen":
        from pollen.scrape import run

        return run(args.lat, args.lon)

    if args.command == "chargepoint":
        from chargepoint.waitlist import run

        return run(until_time=args.until_time)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
