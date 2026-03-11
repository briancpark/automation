import os
import shlex
import subprocess
import sys

SQL_WEEKLY_STATS = (
    "SELECT "
    "COUNT(*) AS total_drives, "
    "COALESCE(SUM(d.distance), 0) AS total_km, "
    "COALESCE(SUM(d.duration_min), 0) AS total_minutes, "
    "COALESCE(AVG(d.outside_temp_avg), 0) AS avg_temp_c, "
    "COALESCE(MAX(d.distance), 0) AS longest_drive_km, "
    "COALESCE(SUM(sp.battery_level - ep.battery_level), 0) AS total_battery_used, "
    "COALESCE(SUM(d.start_ideal_range_km - d.end_ideal_range_km), 0) AS total_range_used_km "
    "FROM drives d "
    "LEFT JOIN positions sp ON d.start_position_id = sp.id "
    "LEFT JOIN positions ep ON d.end_position_id = ep.id "
    "WHERE d.end_date >= NOW() - INTERVAL '7 days' "
    "AND d.distance IS NOT NULL AND d.distance > 0;"
)

SQL_WEEKLY_EFFICIENCY = (
    "SELECT "
    "COALESCE(SUM(d.distance), 0) AS total_km, "
    "COALESCE(SUM(d.start_ideal_range_km - d.end_ideal_range_km), 0) AS total_range_km "
    "FROM drives d "
    "WHERE d.end_date >= NOW() - INTERVAL '7 days' "
    "AND d.distance IS NOT NULL AND d.distance > 0 "
    "AND d.start_ideal_range_km - d.end_ideal_range_km > 0;"
)

SQL_TOP_DESTINATIONS = (
    "SELECT "
    "COALESCE(ea.road, ea.display_name, 'Unknown') AS destination, "
    "ea.city, "
    "COUNT(*) AS visits "
    "FROM drives d "
    "LEFT JOIN addresses ea ON d.end_address_id = ea.id "
    "WHERE d.end_date >= NOW() - INTERVAL '7 days' "
    "AND d.distance IS NOT NULL AND d.distance > 0 "
    "GROUP BY ea.road, ea.display_name, ea.city "
    "ORDER BY visits DESC LIMIT 3;"
)

SQL_LONGEST_DRIVE = (
    "SELECT "
    "d.distance, d.duration_min, "
    "sa.road AS start_road, sa.city AS start_city, "
    "ea.road AS end_road, ea.city AS end_city "
    "FROM drives d "
    "LEFT JOIN addresses sa ON d.start_address_id = sa.id "
    "LEFT JOIN addresses ea ON d.end_address_id = ea.id "
    "WHERE d.end_date >= NOW() - INTERVAL '7 days' "
    "AND d.distance IS NOT NULL AND d.distance > 0 "
    "ORDER BY d.distance DESC LIMIT 1;"
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


def km_to_miles(km):
    try:
        return float(km) * 0.621371
    except (TypeError, ValueError):
        return 0.0


def build_weekly_summary():
    # Overall stats
    stats_lines = _query_db(SQL_WEEKLY_STATS)
    if not stats_lines:
        return "No drives recorded this week."

    fields = stats_lines[0].split("|")
    total_drives = int(fields[0])
    total_km = float(fields[1])
    total_minutes = int(fields[2])
    avg_temp_c = float(fields[3])
    longest_km = float(fields[4])
    total_battery_used = int(fields[5])
    total_range_used_km = float(fields[6])

    if total_drives == 0:
        return "No drives this week. Your Tesla had a rest!"

    total_miles = km_to_miles(total_km)
    hours = total_minutes // 60
    mins = total_minutes % 60
    avg_temp_f = avg_temp_c * 9 / 5 + 32

    # Efficiency
    efficiency_lines = _query_db(SQL_WEEKLY_EFFICIENCY)
    weekly_efficiency = None
    if efficiency_lines:
        eff_fields = efficiency_lines[0].split("|")
        eff_km = float(eff_fields[0])
        eff_range = float(eff_fields[1])
        if eff_range > 0:
            weekly_efficiency = (eff_km / eff_range) * 100

    # Top destinations
    dest_lines = _query_db(SQL_TOP_DESTINATIONS)
    top_places = []
    for line in dest_lines:
        parts = line.split("|")
        road = parts[0] if parts[0] else "Unknown"
        city = parts[1] if len(parts) > 1 and parts[1] else ""
        visits = int(parts[2]) if len(parts) > 2 else 0
        label = f"{road}, {city}" if city else road
        top_places.append((label, visits))

    # Longest drive
    longest_lines = _query_db(SQL_LONGEST_DRIVE)
    longest_desc = None
    if longest_lines:
        lf = longest_lines[0].split("|")
        l_miles = km_to_miles(lf[0])
        l_mins = int(lf[1]) if lf[1] else 0
        l_start = lf[3] if len(lf) > 3 and lf[3] else lf[2] if len(lf) > 2 else ""
        l_end = lf[5] if len(lf) > 5 and lf[5] else lf[4] if len(lf) > 4 else ""
        if l_start and l_end and l_start != l_end:
            longest_desc = f"{l_miles:.1f} miles from {l_start} to {l_end}"
        else:
            longest_desc = f"{l_miles:.1f} miles"

    # Build the summary
    parts = []

    # Opening
    parts.append(
        f"Here's your weekly driving recap. "
        f"You took {total_drives} trips and drove {total_miles:.1f} miles total, "
        f"spending {hours} hours and {mins} minutes on the road."
    )

    # Battery & efficiency
    eff_parts = []
    eff_parts.append(f"You used {total_battery_used}% battery this week")
    if weekly_efficiency is not None:
        eff_parts.append(f"with an overall efficiency of {weekly_efficiency:.0f}%")
    parts.append(", ".join(eff_parts) + ".")

    # Temperature
    parts.append(f"Average outside temperature was {avg_temp_f:.0f} degrees.")

    # Longest drive
    if longest_desc:
        parts.append(f"Your longest drive was {longest_desc}.")

    # Top destinations
    if top_places:
        top = top_places[0]
        if top[1] > 1:
            parts.append(
                f"Your most visited spot was {top[0]} with {top[1]} visits."
            )

    return " ".join(parts)


def run():
    try:
        print(build_weekly_summary())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
