# automation

Monorepo for shortcut automations, designed to run on a Raspberry Pi.

## Setup

Create a `.env` file in the repo root:

```
GOOGLE_POLLEN_API_KEY=your_key_here
CHARGEPOINT_USERNAME=your_email
CHARGEPOINT_PASSWORD=your_password
CHARGEPOINT_WAITLIST_ID=your_waitlist_id
CRUNCHYROLL_EMAIL=your_email
CRUNCHYROLL_PASSWORD=your_password
MAL_CLIENT_ID=your_client_id
MAL_CLIENT_SECRET=your_client_secret
EIA_API_KEY=your_key_here
ELECTRICITY_RATE=0.30
FREE_CHARGE_PCT=50
LG_TV_IP=192.168.1.97
LG_TV_MAC=b4:b2:91:9c:78:01
LG_TV_SSH_KEY=~/.ssh/webos_rsa
```

## Commands

### tesla-tts

TeslaMate latest drive summary for text-to-speech.

```bash
python3 main.py tesla-tts
python3 main.py tesla-tts --verbose
```

Queries the TeslaMate PostgreSQL database (via Docker) and outputs a spoken-style summary of the most recent drive, including distance, route, battery usage, and efficiency.

### tesla-weekly

Weekly driving stats recap.

```bash
python3 main.py tesla-weekly
```

### tesla-morning

Morning routine Tesla summary with efficiency prediction and charging recommendation.

```bash
python3 main.py tesla-morning --lat 37.40 --lon -121.96
python3 main.py tesla-morning --lat 37.40 --lon -121.96 --temp 65  # inject temp from Siri
```

Reports current battery, predicted efficiency based on temperature and recent driving history, estimated battery after your commute, and whether you should charge.

### charge-cost

EV savings calculator comparing Tesla charging costs vs equivalent gas cars using historical EIA gas prices and TeslaMate data.

```bash
python3 main.py charge-cost
python3 main.py charge-cost --weeks 30 --region CA
```

Compares against Prius, Civic, RAV4, F-150, and Suburban. Regions: `CA` (California), `US` (national), `WC` (West Coast). Supercharger sessions detected via `fast_charger_present` flag at $0.35/kWh; office/home charging is free.

### pollen

Current pollen levels from the Google Pollen API.

```bash
python3 main.py pollen --lat 37.40 --lon -121.96
```

Returns pollen type levels (Grass, Tree, Weed), per-plant breakdowns with botanical info and cross-reactions, and health recommendations when levels are elevated.

### chargepoint

Join the ChargePoint waitlist.

```bash
python3 main.py chargepoint
python3 main.py chargepoint -t 17  # stay on waitlist until 5pm
```

### crunchyroll-mal

Sync Crunchyroll watch history to MyAnimeList. Run once to authorize MAL via OAuth:

```bash
python3 -m crunchyroll_mal.mal_auth_setup
```

Then sync manually or via cron:

```bash
python3 main.py crunchyroll-mal
```

Cron runs daily at 4am:
```
0 4 * * * cd /home/pi/automation && python3 main.py crunchyroll-mal >> crunchyroll_mal/sync.log 2>&1
```

### lg-tv

Control the LG projector/TV via WebOS SSAP protocol (WebSocket port 3000). Automatically wakes the TV via Wake-on-LAN if it is off. Requires **Quick Start+** enabled in LG TV Settings → General.

```bash
# Launch apps
python3 main.py lg-tv launch netflix
python3 main.py lg-tv launch youtube
python3 main.py lg-tv launch crunchyroll
python3 main.py lg-tv launch prime
python3 main.py lg-tv launch disney
python3 main.py lg-tv launch appletv
python3 main.py lg-tv launch jellyfin
python3 main.py lg-tv launch twitch
python3 main.py lg-tv launch switch      # Nintendo Switch (HDMI1)
python3 main.py lg-tv launch hdmi2

# Controls
python3 main.py lg-tv volume 40          # set volume 0-100
python3 main.py lg-tv mute
python3 main.py lg-tv unmute
python3 main.py lg-tv off
python3 main.py lg-tv status
python3 main.py lg-tv apps               # list all installed apps
```

#### Apple Shortcuts integration

Use "Run Script over SSH" in the Shortcuts app to call these commands from iPhone/Siri:

- Host: `192.168.1.189`, Port: `22`, User: `pi`
- Script: `cd /home/pi/automation && python3 main.py lg-tv launch netflix`

Example Siri phrases (one shortcut per command):
- "Hey Siri, Netflix on TV"
- "Hey Siri, Nintendo Switch on TV"
- "Hey Siri, Turn Off TV"
- "Hey Siri, Mute TV"

#### LG TV SSH access

The TV runs webOS developer mode with SSH on port 9922:

```bash
ssh -p 9922 -i ~/.ssh/webos_rsa \
  -o HostKeyAlgorithms=+ssh-rsa \
  -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  prisoner@192.168.1.97
```

Key is stored at `~/.ssh/webos_rsa` (decrypted, no passphrase).
