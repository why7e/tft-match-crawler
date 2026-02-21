# TFT Match Crawler

Collects ranked TFT match data from the Riot Games API and stores it in a local SQLite database, with the ability to export to JSON.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set RIOT_API_KEY
```

## Usage

### Crawl

```bash
python main.py           # uses .env in the current directory
python main.py path/.env # uses a custom env file
```

### Export to JSON

```bash
python main.py export                        # → matches_export.json (active traits only)
python main.py export out.json               # → out.json
python main.py export out.json --all-traits  # include inactive traits (style=0)
```

Output is a JSON array of match objects, each with nested participants, traits, and units.

## Configuration

All settings are read from environment variables (`.env`):

| Variable | Default | Description |
|---|---|---|
| `RIOT_API_KEY` | — | Required. Riot API key (`RGAPI-...`) |
| `PLATFORM` | `na1` | Platform routing value (e.g. `na1`, `euw1`, `kr`) |
| `LEAGUES` | `challenger` | Comma-separated leagues: `challenger`, `grandmaster`, `master` |
| `QUEUE` | `RANKED_TFT` | Riot queue identifier |
| `MATCHES_PER_PLAYER` | `50` | Recent matches to fetch per player (1–200) |
| `START_TIME` | — | Optional Unix timestamp (seconds) — filter match start |
| `END_TIME` | — | Optional Unix timestamp (seconds) — filter match end |
| `DB_PATH` | `tft_data.db` | SQLite database file path |
| `REQUEST_DELAY` | `1.2` | Seconds between API requests |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

Use `START_TIME` / `END_TIME` to restrict collection to a specific patch window. See the [TFT patch schedule](https://support-teamfighttactics.riotgames.com/hc/en-us/articles/37127675562387-Patch-Schedule-Teamfight-Tactics) for date ranges.

## Database Schema

```
players             — tracked players (puuid, league, LP, wins/losses)
matches             — match metadata (version, set, queue, datetime)
participants        — one row per player-in-match (placement, level, augments, ...)
participant_traits  — traits active for each participant
participant_units   — units fielded by each participant (character, star level, items)
```

`participants.puuid` links back to `players.puuid` for player-level analysis.
