import os
import shlex
import subprocess
import sys


SQL_LATEST_DRIVE = (
    "SELECT d.id, d.start_date, d.end_date, d.distance, d.duration_min, "
    "d.start_ideal_range_km, d.end_ideal_range_km, "
    "sa.display_name AS start_display, sa.road AS start_road, "
    "sa.house_number AS start_house, sa.city AS start_city, "
    "ea.display_name AS end_display, ea.road AS end_road, "
    "ea.house_number AS end_house, ea.city AS end_city, "
    "sp.battery_level AS start_battery_level, "
    "ep.battery_level AS end_battery_level "
    "FROM drives d "
    "LEFT JOIN addresses sa ON d.start_address_id = sa.id "
    "LEFT JOIN addresses ea ON d.end_address_id = ea.id "
    "LEFT JOIN positions sp ON d.start_position_id = sp.id "
    "LEFT JOIN positions ep ON d.end_position_id = ep.id "
    "ORDER BY d.end_date DESC NULLS LAST "
    "LIMIT 1;"
)


def _env(name, default):
    value = os.getenv(name)
    return value if value else default


def fetch_latest_drive():
    container = _env("TESLAMATE_DB_CONTAINER", "teslamate-database-1")
    db_user = _env("TESLAMATE_DB_USER", "teslamate")
    db_name = _env("TESLAMATE_DB_NAME", "teslamate")

    cmd = (
        f"docker exec {shlex.quote(container)} "
        f"psql -U {shlex.quote(db_user)} -d {shlex.quote(db_name)} "
        f"-t -A -F '|' -c {shlex.quote(SQL_LATEST_DRIVE)}"
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        shell=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Database query failed")

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def fmt_float(value, digits=1):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return f"{number:.{digits}f}"


def km_to_miles(km):
    try:
        return float(km) * 0.621371
    except (TypeError, ValueError):
        return None


def build_place_label(display, road, house_number, city):
    street = ""
    if road:
        if house_number:
            street = f"{house_number} {road}".strip()
        else:
            street = road.strip()
    elif display:
        parts = [part.strip() for part in display.split(",") if part.strip()]
        if parts:
            if len(parts) >= 2 and parts[0].isdigit():
                street = f"{parts[0]} {parts[1]}".strip()
            else:
                street = parts[0]

    city_name = city.strip() if city else ""
    if not city_name and display:
        parts = [part.strip() for part in display.split(",") if part.strip()]
        if len(parts) >= 3:
            city_name = parts[2]
        elif len(parts) >= 2:
            city_name = parts[1]

    return street or "unknown location", city_name


def format_latest_drive(line, verbose=False):
    if not line:
        return "No completed drives found."

    fields = line.split("|")
    if len(fields) < 14:
        return "Latest drive data is incomplete."

    (
        _,
        start_date,
        end_date,
        distance,
        duration_min,
        start_range,
        end_range,
        start_display,
        start_road,
        start_house,
        start_city,
        end_display,
        end_road,
        end_house,
        end_city,
        start_battery_level,
        end_battery_level,
    ) = fields

    start_street, start_city_name = build_place_label(
        start_display, start_road, start_house, start_city
    )
    end_street, end_city_name = build_place_label(
        end_display, end_road, end_house, end_city
    )

    distance_km = fmt_float(distance)
    distance_miles = fmt_float(km_to_miles(distance), digits=1)
    duration = duration_min.strip() if duration_min else ""
    start_range_km = fmt_float(start_range)
    end_range_km = fmt_float(end_range)
    start_range_miles = fmt_float(km_to_miles(start_range), digits=1)
    end_range_miles = fmt_float(km_to_miles(end_range), digits=1)
    end_battery = end_battery_level.strip() if end_battery_level else ""
    start_battery = start_battery_level.strip() if start_battery_level else ""

    sentence_one = []
    if distance_miles:
        sentence_one.append(f"You drove {distance_miles} miles")
    else:
        sentence_one.append("You drove")

    include_city = True
    if distance_miles:
        try:
            include_city = float(distance_miles) >= 15
        except ValueError:
            include_city = True

    if start_city_name and end_city_name and start_city_name.lower() == end_city_name.lower():
        include_city = False

    if include_city and start_city_name:
        start_place = f"{start_street}, {start_city_name}"
    else:
        start_place = start_street

    if include_city and end_city_name:
        end_place = f"{end_street}, {end_city_name}"
    else:
        end_place = end_street

    sentence_one.append(f"from {start_place} to {end_place}.")

    sentence_two = []
    try:
        distance_val = float(distance_km) if distance_km else None
    except ValueError:
        distance_val = None

    # Keep the second sentence brief and only include extra stats for longer drives.
    range_consumed = None
    if start_range_km and end_range_km:
        try:
            range_consumed = float(start_range_km) - float(end_range_km)
        except ValueError:
            range_consumed = None
    range_consumed_miles = fmt_float(km_to_miles(range_consumed), digits=1)

    battery_sentence = ""
    efficiency_pct = None
    if start_battery and end_battery:
        battery_used = None
        try:
            battery_used = int(start_battery) - int(end_battery)
        except ValueError:
            battery_used = None
        if battery_used is not None:
            if range_consumed_miles:
                try:
                    range_used = float(range_consumed_miles)
                    if range_used > 0 and distance_miles:
                        efficiency_pct = (float(distance_miles) / range_used) * 100
                except ValueError:
                    efficiency_pct = None
            battery_sentence = (
                f"You started at {start_battery}% and finished at {end_battery}%, "
                f"consuming {battery_used}% battery"
            )
        else:
            battery_sentence = (
                f"You started at {start_battery}% and finished at {end_battery}%"
            )
    elif end_battery:
        battery_sentence = f"Battery ended at {end_battery}%"

    if battery_sentence:
        if range_consumed_miles and distance_miles:
            battery_sentence += f", {range_consumed_miles} miles of range"
        if efficiency_pct is not None:
            battery_sentence += f"; efficiency was {efficiency_pct:.0f}%."
        else:
            battery_sentence += "."
        sentence_two.append(battery_sentence)
    elif start_date and end_date:
        sentence_two.append(f"Started {start_date} and ended {end_date}.")

    if verbose:
        verbose_parts = [" ".join(sentence_one)]
        if start_range_miles and end_range_miles:
            verbose_parts.append(
                f"Range went from {start_range_miles} to {end_range_miles} miles."
            )
        if range_consumed_miles and distance_miles:
            verbose_parts.append(
                f"Range used was {range_consumed_miles} miles for {distance_miles} traveled."
            )
        if end_battery:
            verbose_parts.append(f"Battery ended at {end_battery} percent.")
        if start_date and end_date:
            verbose_parts.append(f"Started {start_date} and ended {end_date}.")
        return " ".join(verbose_parts)

    if sentence_two:
        return " ".join(sentence_one + sentence_two)
    return " ".join(sentence_one)


