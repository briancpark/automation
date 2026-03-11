import os
import sys
from datetime import datetime

import requests


HEADERS_BASE = {
    "origin": "https://na.chargepoint.com",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "x-requested-with": "XMLHttpRequest",
    "pragma": "no-cache",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/73.0.3683.103 Safari/537.36"
    ),
    "cache-control": "no-cache",
    "authority": "na.chargepoint.com",
    "dnt": "1",
}


def _env_required(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} not set. Add it to your .env file.")
    return value


def login(session, username, password):
    headers = {
        **HEADERS_BASE,
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "accept": "*/*",
        "referer": "https://na.chargepoint.com/home",
    }
    data = {
        "user_name": username,
        "user_password": password,
        "auth_code": "",
        "recaptcha_response_field": "",
        "timezone_offset": "420",
        "timezone": "PDT",
        "timezone_name": "",
    }
    resp = session.post(
        "https://na.chargepoint.com/users/validate", headers=headers, data=data
    )
    resp.raise_for_status()
    return resp


def join_waitlist(session, waitlist_id, until_time=23):
    headers = {
        **HEADERS_BASE,
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "accept": "application/json, text/javascript, */*; q=0.01",
        "referer": "https://na.chargepoint.com/dashboard_driver",
    }
    data = {"regionIds": waitlist_id, "untilTime": str(until_time)}
    resp = session.post(
        "https://na.chargepoint.com/community/activateRegion",
        headers=headers,
        data=data,
    )
    resp.raise_for_status()
    return resp


def run(until_time=23):
    username = _env_required("CHARGEPOINT_USERNAME")
    password = _env_required("CHARGEPOINT_PASSWORD")
    waitlist_id = _env_required("CHARGEPOINT_WAITLIST_ID")

    try:
        session = requests.Session()
        login(session, username, password)
        join_waitlist(session, waitlist_id, until_time)
        print(f"Joined ChargePoint waitlist {waitlist_id} until {until_time}:00.")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
