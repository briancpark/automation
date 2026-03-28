"""
Charge cost vs gas savings calculator.

Pulls weekly miles + kWh from TeslaMate, fetches historical gas prices from EIA,
and compares actual electricity cost against equivalent gas car costs.
"""

import os
import shlex
import subprocess
import sys
import urllib.request
import json
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Comparison cars  (name, MPG combined, gas grade: regular/midgrade/premium)
# ---------------------------------------------------------------------------
COMPARISON_CARS = [
    ("Toyota Prius (Hybrid)",   52, "regular"),
    ("Honda Civic",             36, "regular"),
    ("Toyota RAV4",             30, "regular"),
    ("Ford F-150",              22, "regular"),
    ("Chevy Suburban",          16, "regular"),
]

# EIA duoarea codes
EIA_DUOAREA = {
    "CA": "SCA",   # California
    "US": "NUS",   # National average
    "WC": "R50",   # West Coast (PADD 5)
}

EIA_PRODUCT = {
    "regular":  "EPMR",
    "midgrade": "EPMM",
    "premium":  "EPMP",
}


def _env(name, default=None):
    return os.getenv(name) or default


def _query_db(sql):
    container = _env("TESLAMATE_DB_CONTAINER", "teslamate-database-1")
    db_user   = _env("TESLAMATE_DB_USER", "teslamate")
    db_name   = _env("TESLAMATE_DB_NAME", "teslamate")

    cmd = (
        f"docker exec {shlex.quote(container)} "
        f"psql -U {shlex.quote(db_user)} -d {shlex.quote(db_name)} "
        f"-t -A -F '|' -c {shlex.quote(sql)}"
    )
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, shell=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "DB query failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def _fetch_eia_prices(api_key, duoarea, weeks_back=52):
    """Fetch weekly retail gas prices from EIA API v2. Returns {date_str: price}."""
    start = (datetime.now() - timedelta(weeks=weeks_back)).strftime("%Y-%m-%d")
    prices = {}

    for grade, product in EIA_PRODUCT.items():
        url = (
            "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
            f"?api_key={api_key}"
            f"&frequency=weekly"
            f"&data[]=value"
            f"&facets[product][]={product}"
            f"&facets[duoarea][]={duoarea}"
            f"&start={start}"
            f"&sort[0][column]=period"
            f"&sort[0][direction]=desc"
            f"&length=200"
        )
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            for row in data.get("response", {}).get("data", []):
                period = row.get("period")   # "YYYY-MM-DD"
                value = row.get("value")
                if period and value:
                    prices.setdefault(period, {})[grade] = float(value)
        except Exception as exc:
            print(f"  [WARN] EIA fetch failed for {grade}: {exc}", file=sys.stderr)

    return prices


def _price_for_week(gas_prices, week_dt, grade="regular"):
    """Find the closest EIA price for a given week."""
    if not gas_prices:
        return None
    week_str = week_dt.strftime("%Y-%m-%d")
    # Exact match first
    if week_str in gas_prices and grade in gas_prices[week_str]:
        return gas_prices[week_str][grade]
    # Find closest week within 2 weeks
    best_key = None
    best_delta = timedelta(days=999)
    for date_str, grades in gas_prices.items():
        if grade not in grades:
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            delta = abs(d - week_dt)
            if delta < best_delta:
                best_delta = delta
                best_key = date_str
        except ValueError:
            continue
    if best_key and best_delta <= timedelta(days=14):
        return gas_prices[best_key][grade]
    return None


def _weekly_stats(weeks_back):
    """Fetch weekly (miles driven, kWh charged) from TeslaMate."""
    start = (datetime.now() - timedelta(weeks=weeks_back)).strftime("%Y-%m-%d")

    sql_drives = f"""
        SELECT DATE_TRUNC('week', end_date)::date AS week,
               SUM(distance) AS total_km
        FROM drives
        WHERE end_date >= '{start}' AND distance > 0
        GROUP BY 1 ORDER BY 1;
    """

    # Split kWh into supercharger vs free (office/home) using fast_charger_present flag
    sql_charging = f"""
        WITH session_type AS (
            SELECT cp.id,
                   cp.start_date,
                   cp.charge_energy_added,
                   bool_or(c.fast_charger_present) AS is_supercharger
            FROM charging_processes cp
            LEFT JOIN charges c ON c.charging_process_id = cp.id
            WHERE cp.start_date >= '{start}' AND cp.charge_energy_added > 0
            GROUP BY cp.id, cp.start_date, cp.charge_energy_added
        )
        SELECT DATE_TRUNC('week', start_date)::date AS week,
               SUM(CASE WHEN is_supercharger THEN charge_energy_added ELSE 0 END) AS supercharger_kwh,
               SUM(CASE WHEN is_supercharger THEN 0 ELSE charge_energy_added END) AS free_kwh
        FROM session_type
        GROUP BY 1 ORDER BY 1;
    """

    miles_by_week = {}
    for line in _query_db(sql_drives):
        parts = line.split("|")
        week_str = parts[0].strip()
        km = float(parts[1])
        miles_by_week[week_str] = km * 0.621371

    kwh_by_week = {}
    for line in _query_db(sql_charging):
        parts = line.split("|")
        week_str = parts[0].strip()
        kwh_by_week[week_str] = {
            "supercharger": float(parts[1]),
            "free": float(parts[2]),
        }

    # Merge by week
    all_weeks = sorted(set(list(miles_by_week.keys()) + list(kwh_by_week.keys())))
    return [
        {
            "week": w,
            "miles": miles_by_week.get(w, 0.0),
            "supercharger_kwh": kwh_by_week.get(w, {}).get("supercharger", 0.0),
            "free_kwh": kwh_by_week.get(w, {}).get("free", 0.0),
        }
        for w in all_weeks
    ]


def _format_savings(weeks, gas_prices, supercharger_rate, region):
    """Build the savings report text."""
    lines = []
    totals = {car[0]: {"gas_cost": 0.0, "ev_cost": 0.0} for car in COMPARISON_CARS}
    total_miles = 0.0
    total_sc_kwh = 0.0
    total_free_kwh = 0.0
    total_ev_cost = 0.0

    lines.append(f"=== EV Savings Report ({len(weeks)} weeks, {region}) ===\n")

    for w in weeks:
        week_dt = datetime.strptime(w["week"], "%Y-%m-%d")
        miles = w["miles"]
        sc_kwh = w["supercharger_kwh"]
        free_kwh = w["free_kwh"]
        total_kwh = sc_kwh + free_kwh

        # Supercharger sessions cost money; office/home assumed free
        ev_cost = sc_kwh * supercharger_rate

        total_miles += miles
        total_sc_kwh += sc_kwh
        total_free_kwh += free_kwh
        total_ev_cost += ev_cost

        week_label = week_dt.strftime("%b %d")
        lines.append(
            f"Week of {week_label}: {miles:.0f} mi driven, "
            f"{sc_kwh:.1f} kWh Supercharger (${ev_cost:.2f}) + {free_kwh:.1f} kWh free"
        )

        for car_name, mpg, grade in COMPARISON_CARS:
            gas_price = _price_for_week(gas_prices, week_dt, grade)
            if gas_price and miles > 0:
                gas_cost = (miles / mpg) * gas_price
                totals[car_name]["gas_cost"] += gas_cost
                totals[car_name]["ev_cost"] += ev_cost
                saved = gas_cost - ev_cost
                lines.append(f"  vs {car_name} ({mpg} MPG @ ${gas_price:.2f}/gal): ${gas_cost:.2f} → saved ${saved:.2f}")
            elif miles > 0:
                lines.append(f"  vs {car_name} ({mpg} MPG): no gas price data for this week")

        lines.append("")

    # Summary
    lines.append(
        f"=== TOTALS: {total_miles:.0f} miles | "
        f"{total_sc_kwh:.1f} kWh Supercharger (${total_ev_cost:.2f}) + "
        f"{total_free_kwh:.1f} kWh free ==="
    )
    for car_name, mpg, grade in COMPARISON_CARS:
        t = totals[car_name]
        if t["gas_cost"] > 0:
            saved = t["gas_cost"] - t["ev_cost"]
            lines.append(f"  vs {car_name}: ${t['gas_cost']:.2f} gas → saved ${saved:.2f}")

    return "\n".join(lines)


def run(weeks_back=30, region_code="CA"):
    api_key = _env("EIA_API_KEY")
    supercharger_rate = float(_env("SUPERCHARGER_RATE", "0.35"))

    duoarea = EIA_DUOAREA.get(region_code.upper(), "SCA")

    # Fetch weekly stats from TeslaMate
    try:
        weeks = _weekly_stats(weeks_back)
    except Exception as exc:
        print(f"Error fetching TeslaMate data: {exc}", file=sys.stderr)
        return 1

    if not weeks:
        print("No drive data found.")
        return 0

    # Fetch gas prices from EIA
    gas_prices = {}
    if api_key:
        gas_prices = _fetch_eia_prices(api_key, duoarea, weeks_back + 4)
    else:
        print(
            "[WARN] EIA_API_KEY not set — gas prices unavailable. "
            "Get a free key at https://www.eia.gov/opendata/\n",
            file=sys.stderr,
        )

    region_label = {
        "CA": "California", "US": "National Avg", "WC": "West Coast"
    }.get(region_code.upper(), region_code)

    print(_format_savings(weeks, gas_prices, supercharger_rate, region_label))
    return 0
