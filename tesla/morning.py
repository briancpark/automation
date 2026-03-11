import json
import os
import shlex
import subprocess
import sys
import urllib.request
import urllib.error

COMMUTE_MILES = 8.4
COMMUTE_KM = COMMUTE_MILES / 0.621371

# ChargePoint workplace charger specs
CHARGER_KW = 6.6
SESSION_LIMIT_HRS = 4
CHARGING_EFFICIENCY = 0.90  # L2 charging ~90% efficient
MAX_CHARGE_KWH = CHARGER_KW * SESSION_LIMIT_HRS * CHARGING_EFFICIENCY  # ~23.8 kWh

# Car specs (Model 3 SR+)
# Derived from TeslaMate: efficiency 0.137 kWh/km, ~429 km ideal range at 100%
BATTERY_CAPACITY_KWH = 59.0
MAX_CHARGE_GAIN_PCT = (MAX_CHARGE_KWH / BATTERY_CAPACITY_KWH) * 100  # ~40%

# Join waitlist if arrival battery is at or below this threshold.
# At 60%, a 4-hour session brings you to ~100% — full utilization of the spot.
# Above 60%, you'd hit 100% early and block the charger for others.
WAITLIST_THRESHOLD_PCT = 60

# TeslaMate DB queries
SQL_CURRENT_STATE = (
    "SELECT battery_level, ideal_battery_range_km, rated_battery_range_km, "
    "outside_temp, date "
    "FROM positions ORDER BY date DESC LIMIT 1;"
)

SQL_RECENT_EFFICIENCY = (
    "SELECT d.distance, "
    "d.start_ideal_range_km - d.end_ideal_range_km AS range_used_km, "
    "d.outside_temp_avg, "
    "sp.battery_level AS start_batt, ep.battery_level AS end_batt "
    "FROM drives d "
    "LEFT JOIN positions sp ON d.start_position_id = sp.id "
    "LEFT JOIN positions ep ON d.end_position_id = ep.id "
    "WHERE d.distance IS NOT NULL AND d.distance > 0 "
    "AND d.start_ideal_range_km - d.end_ideal_range_km > 0 "
    "ORDER BY d.end_date DESC LIMIT 20;"
)


def _env(name, default):
    value = os.getenv(name)
    return value if value else default


def _query_db(sql):
    container = _env("TESLAMATE_DB_CONTAINER", "teslamate-database-1")
    db_user = _env("TESLAMATE_DB_USER", "teslamate")
    db_name = _env("TESLAMATE_DB_NAME", "teslamate")

    cmd = (
        f"docker exec {shlex.quote(container)} "
        f"psql -U {shlex.quote(db_user)} -d {shlex.quote(db_name)} "
        f"-t -A -F '|' -c {shlex.quote(sql)}"
    )
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, shell=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Database query failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def _fetch_weather(lat, lon):
    """Get current temperature from Open-Meteo (free, no key)."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m"
        f"&temperature_unit=fahrenheit"
    )
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode())
        return data.get("current", {}).get("temperature_2m")
    except Exception:
        return None


def _compute_avg_efficiency(drives):
    """Compute average efficiency ratio from recent drives."""
    ratios = []
    for line in drives:
        fields = line.split("|")
        if len(fields) < 5:
            continue
        try:
            distance_km = float(fields[0])
            range_used_km = float(fields[1])
            if range_used_km > 0:
                ratios.append(distance_km / range_used_km)
        except (ValueError, ZeroDivisionError):
            continue
    if not ratios:
        return 1.0
    return sum(ratios) / len(ratios)


def _compute_temp_efficiency(drives):
    """Group efficiency by temperature buckets to estimate temp impact."""
    buckets = {}
    for line in drives:
        fields = line.split("|")
        if len(fields) < 5:
            continue
        try:
            distance_km = float(fields[0])
            range_used_km = float(fields[1])
            temp_c = float(fields[2])
            if range_used_km > 0:
                ratio = distance_km / range_used_km
                bucket = round(temp_c / 5) * 5  # 5°C buckets
                buckets.setdefault(bucket, []).append(ratio)
        except (ValueError, ZeroDivisionError):
            continue
    return {k: sum(v) / len(v) for k, v in buckets.items()}


def _estimate_battery_drop(current_range_km, battery_pct, efficiency_ratio):
    """Estimate battery % consumed for the commute."""
    if current_range_km <= 0 or battery_pct <= 0:
        return None
    km_per_pct = current_range_km / battery_pct
    effective_range_per_pct = km_per_pct * efficiency_ratio
    if effective_range_per_pct <= 0:
        return None
    return COMMUTE_KM / effective_range_per_pct


def c_to_f(c):
    try:
        return float(c) * 9 / 5 + 32
    except (TypeError, ValueError):
        return None


def build_summary(lat, lon, temp_f=None):
    # Current car state
    state_lines = _query_db(SQL_CURRENT_STATE)
    if not state_lines:
        return "Could not retrieve current car state."
    fields = state_lines[0].split("|")
    battery_pct = int(fields[0])
    ideal_range_km = float(fields[1])
    car_temp_c = fields[3] if fields[3] else None

    # Recent efficiency
    drive_lines = _query_db(SQL_RECENT_EFFICIENCY)
    avg_efficiency = _compute_avg_efficiency(drive_lines)
    temp_buckets = _compute_temp_efficiency(drive_lines)

    # Current weather — prefer injected temp from Siri, then Open-Meteo, then car
    if temp_f is not None:
        weather_temp_f = temp_f
        current_temp_c = (temp_f - 32) * 5 / 9
        display_temp_f = f"{weather_temp_f:.0f}"
    else:
        weather_temp_f = _fetch_weather(lat, lon)
        if weather_temp_f is not None:
            current_temp_c = (weather_temp_f - 32) * 5 / 9
            display_temp_f = f"{weather_temp_f:.0f}"
        elif car_temp_c:
            current_temp_c = float(car_temp_c)
            weather_temp_f = c_to_f(current_temp_c)
            display_temp_f = f"{weather_temp_f:.0f}" if weather_temp_f else None
        else:
            current_temp_c = None
            display_temp_f = None

    # Pick efficiency estimate based on current temp
    predicted_efficiency = avg_efficiency
    if current_temp_c is not None and temp_buckets:
        bucket = round(current_temp_c / 5) * 5
        if bucket in temp_buckets:
            predicted_efficiency = temp_buckets[bucket]
        else:
            # Use closest bucket
            closest = min(temp_buckets.keys(), key=lambda b: abs(b - current_temp_c))
            predicted_efficiency = temp_buckets[closest]

    efficiency_pct = predicted_efficiency * 100

    # Estimate battery after commute
    batt_drop = _estimate_battery_drop(ideal_range_km, battery_pct, predicted_efficiency)
    arrival_battery = battery_pct - round(batt_drop) if batt_drop is not None else None

    # Build output
    parts = []

    # Current state
    ideal_range_miles = ideal_range_km * 0.621371
    temp_str = f" It's {display_temp_f} degrees outside." if display_temp_f else ""
    parts.append(
        f"Your Tesla is at {battery_pct}% with {ideal_range_miles:.0f} miles of range.{temp_str}"
    )

    # Efficiency prediction
    if efficiency_pct >= 100:
        eff_desc = "great"
    elif efficiency_pct >= 85:
        eff_desc = "good"
    elif efficiency_pct >= 70:
        eff_desc = "reduced"
    else:
        eff_desc = "poor"
    parts.append(f"Predicted efficiency today is {eff_desc} at {efficiency_pct:.0f}%.")

    # Arrival estimate
    if arrival_battery is not None:
        drop = battery_pct - arrival_battery
        parts.append(
            f"Your {COMMUTE_MILES} mile commute should use about {drop}% battery, "
            f"arriving at {arrival_battery}%."
        )

    # Charging decision
    should_join = False
    charge_time_needed_hrs = None

    if arrival_battery is not None:
        battery_after_round_trip = arrival_battery - round(batt_drop)

        if arrival_battery <= WAITLIST_THRESHOLD_PCT:
            should_join = True
            # How long to charge to ~100%?
            pct_to_fill = 100 - arrival_battery
            charge_time_needed_hrs = min(
                SESSION_LIMIT_HRS,
                (pct_to_fill / 100 * BATTERY_CAPACITY_KWH)
                / (CHARGER_KW * CHARGING_EFFICIENCY),
            )
            charge_gain = min(pct_to_fill, MAX_CHARGE_GAIN_PCT)
            leave_battery = arrival_battery + round(charge_gain)

            parts.append(
                f"Joining the ChargePoint waitlist. "
                f"A {charge_time_needed_hrs:.1f} hour session at 6.6 kW "
                f"would bring you from {arrival_battery}% to about {leave_battery}%."
            )
        elif battery_after_round_trip < 30:
            should_join = True
            pct_to_fill = 100 - arrival_battery
            charge_time_needed_hrs = min(
                SESSION_LIMIT_HRS,
                (pct_to_fill / 100 * BATTERY_CAPACITY_KWH)
                / (CHARGER_KW * CHARGING_EFFICIENCY),
            )
            charge_gain = min(pct_to_fill, MAX_CHARGE_GAIN_PCT)
            leave_battery = arrival_battery + round(charge_gain)

            parts.append(
                f"You'd be at {battery_after_round_trip}% after the round trip. "
                f"Joining the ChargePoint waitlist. "
                f"A session would bring you to about {leave_battery}%."
            )
        else:
            parts.append(
                f"No need to charge today. "
                f"You'll have about {battery_after_round_trip}% after the round trip."
            )
    elif battery_pct < 30:
        should_join = True
        parts.append("Battery is low. Joining the ChargePoint waitlist.")
    else:
        parts.append("No need to charge today.")

    return " ".join(parts), should_join


def _auto_join_waitlist():
    """Join ChargePoint waitlist if credentials are configured."""
    try:
        from chargepoint.waitlist import run as cp_run

        return cp_run()
    except Exception as exc:
        print(f"ChargePoint waitlist error: {exc}", file=sys.stderr)
        return 1


def run(lat, lon, temp_f=None):
    try:
        summary, should_join = build_summary(lat, lon, temp_f=temp_f)
        print(summary)
        if should_join:
            _auto_join_waitlist()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
