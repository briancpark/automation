import json
import os
import sys
import urllib.request
import urllib.error

API_URL = "https://pollen.googleapis.com/v1/forecast:lookup"

LEVEL_LABELS = {
    0: "None",
    1: "Very Low",
    2: "Low",
    3: "Moderate",
    4: "High",
    5: "Very High",
}


def _get_api_key():
    key = os.getenv("GOOGLE_POLLEN_API_KEY")
    if not key:
        raise RuntimeError(
            "GOOGLE_POLLEN_API_KEY not set. Add it to your .env file."
        )
    return key


def fetch_pollen(lat, lon, days=1):
    key = _get_api_key()
    url = (
        f"{API_URL}"
        f"?key={key}"
        f"&location.latitude={lat}"
        f"&location.longitude={lon}"
        f"&days={days}"
    )

    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode() if exc.fp else ""
        raise RuntimeError(f"Google Pollen API error {exc.code}: {body}") from exc

    return data


def format_pollen(data):
    forecasts = data.get("dailyInfo", [])
    if not forecasts:
        return "No pollen data available for this location."

    today = forecasts[0]
    date_info = today.get("date", {})
    date_str = (
        f"{date_info.get('year')}-{date_info.get('month', 0):02d}-"
        f"{date_info.get('day', 0):02d}"
    )

    lines = [f"Pollen report for {date_str}:"]

    # --- Pollen type summaries (Grass, Tree, Weed) ---
    type_infos = today.get("pollenTypeInfo", [])
    if type_infos:
        lines.append("")
        for entry in type_infos:
            name = entry.get("displayName", entry.get("code", "Unknown"))
            in_season = entry.get("inSeason", False)
            index_info = entry.get("indexInfo", {})
            value = index_info.get("value")
            category = index_info.get("category", "")

            if value is not None:
                label = LEVEL_LABELS.get(value, category or str(value))
                status = f"{label} ({value}/5)"
            elif not in_season:
                status = "Out of season"
            else:
                status = "No data"

            lines.append(f"  {name}: {status}")

            # Health recommendations per type
            recommendations = entry.get("healthRecommendations", [])
            for rec in recommendations:
                lines.append(f"    - {rec}")

    # --- Individual plant breakdown ---
    plant_infos = today.get("plantInfo", [])
    in_season_plants = [p for p in plant_infos if p.get("inSeason", False)]
    if in_season_plants:
        lines.append("")
        lines.append("Plants currently in season:")
        for plant in in_season_plants:
            name = plant.get("displayName", plant.get("code", "Unknown"))
            idx = plant.get("indexInfo", {})
            value = idx.get("value")
            category = idx.get("category", "")
            desc = plant.get("plantDescription", {})
            family = desc.get("family", "")
            season = desc.get("season", "")
            cross = desc.get("crossReaction", "")

            if value is not None:
                label = LEVEL_LABELS.get(value, category or str(value))
                plant_line = f"  {name}: {label} ({value}/5)"
            else:
                plant_line = f"  {name}: In season (no index)"

            details = []
            if family:
                details.append(f"family: {family}")
            if season:
                details.append(f"season: {season}")
            if cross:
                details.append(f"cross-reaction: {cross}")

            if details:
                plant_line += f"  [{', '.join(details)}]"

            lines.append(plant_line)

    # --- Out of season plants (brief) ---
    out_of_season = [p for p in plant_infos if not p.get("inSeason", False)]
    if out_of_season:
        names = [p.get("displayName", p.get("code", "?")) for p in out_of_season]
        lines.append("")
        lines.append(f"Out of season: {', '.join(names)}")

    return "\n".join(lines)


def run(lat, lon):
    try:
        data = fetch_pollen(lat, lon)
        print(format_pollen(data))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
