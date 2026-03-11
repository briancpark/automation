# automation

Monorepo for shortcut automations, designed to run on a Raspberry Pi.

## Setup

Create a `.env` file in the repo root:

```
GOOGLE_POLLEN_API_KEY=your_key_here
```

## Commands

### tesla-tts

TeslaMate latest drive summary for text-to-speech.

```bash
python3 main.py tesla-tts
python3 main.py tesla-tts --verbose
```

Queries the TeslaMate PostgreSQL database (via Docker) and outputs a spoken-style summary of the most recent drive, including distance, route, battery usage, and efficiency.

### pollen

Current pollen levels from the Google Pollen API.

```bash
python3 main.py pollen --lat 37.40 --lon -121.96
```

Returns pollen type levels (Grass, Tree, Weed), per-plant breakdowns with botanical info and cross-reactions, and health recommendations when levels are elevated.
