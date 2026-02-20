"""
SQLite database layer for the TFT match crawler.

Schema
------
players             — one row per tracked player (keyed by puuid)
matches             — one row per fetched match
participants        — one row per player-in-match (8 per match)
participant_traits  — traits active for a participant
participant_units   — units fielded by a participant
"""

import json
import sqlite3
import logging
from contextlib import contextmanager
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS players (
    puuid           TEXT PRIMARY KEY,
    summoner_id     TEXT,
    summoner_name   TEXT,
    league          TEXT,
    rank            TEXT,
    lp              INTEGER,
    wins            INTEGER,
    losses          INTEGER,
    platform        TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    match_id            TEXT PRIMARY KEY,
    game_datetime       INTEGER,   -- Unix ms
    game_length         REAL,      -- seconds
    game_version        TEXT,
    queue_id            INTEGER,
    tft_set_number      INTEGER,
    tft_set_core_name   TEXT,
    platform            TEXT,
    fetched_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS participants (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id                TEXT NOT NULL REFERENCES matches(match_id),
    puuid                   TEXT NOT NULL,
    placement               INTEGER,
    level                   INTEGER,
    gold_left               INTEGER,
    last_round              INTEGER,
    players_eliminated      INTEGER,
    time_eliminated         REAL,
    total_damage_to_players INTEGER,
    augments                TEXT,   -- JSON array of augment name strings
    UNIQUE(match_id, puuid)
);

CREATE TABLE IF NOT EXISTS participant_traits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id  INTEGER NOT NULL REFERENCES participants(id),
    name            TEXT,
    num_units       INTEGER,
    style           INTEGER,   -- 0=inactive, 1=bronze, 2=silver, 3=gold, 4=chromatic
    tier_current    INTEGER,
    tier_total      INTEGER
);

CREATE TABLE IF NOT EXISTS participant_units (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id  INTEGER NOT NULL REFERENCES participants(id),
    character_id    TEXT,
    name            TEXT,
    rarity          INTEGER,
    tier            INTEGER,   -- star level
    items           TEXT       -- JSON array of item name strings
);

-- Useful indexes for analysis queries
CREATE INDEX IF NOT EXISTS idx_participants_puuid   ON participants(puuid);
CREATE INDEX IF NOT EXISTS idx_participants_match   ON participants(match_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_traits_participant_name ON participant_traits(participant_id, name);
CREATE INDEX IF NOT EXISTS idx_traits_name                    ON participant_traits(name);
CREATE INDEX IF NOT EXISTS idx_units_participant    ON participant_units(participant_id);
CREATE INDEX IF NOT EXISTS idx_units_character      ON participant_units(character_id);
CREATE INDEX IF NOT EXISTS idx_matches_datetime     ON matches(game_datetime);
CREATE INDEX IF NOT EXISTS idx_matches_version      ON matches(game_version);
"""


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)
        logger.debug("Database schema initialised: %s", self.db_path)

    # ------------------------------------------------------------------
    # Players
    # ------------------------------------------------------------------

    def upsert_player(self, player: Dict):
        sql = """
            INSERT INTO players
                (puuid, summoner_id, summoner_name, league, rank, lp, wins, losses, platform, updated_at)
            VALUES
                (:puuid, :summoner_id, :summoner_name, :league, :rank, :lp, :wins, :losses, :platform, datetime('now'))
            ON CONFLICT(puuid) DO UPDATE SET
                summoner_id   = excluded.summoner_id,
                summoner_name = excluded.summoner_name,
                league        = excluded.league,
                rank          = excluded.rank,
                lp            = excluded.lp,
                wins          = excluded.wins,
                losses        = excluded.losses,
                platform      = excluded.platform,
                updated_at    = excluded.updated_at
        """
        with self._conn() as conn:
            conn.execute(sql, player)

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------

    def get_known_match_ids(self) -> set:
        with self._conn() as conn:
            rows = conn.execute("SELECT match_id FROM matches").fetchall()
        return {r["match_id"] for r in rows}

    def match_exists(self, match_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM matches WHERE match_id = ?", (match_id,)
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Full match upsert (participants + traits + units)
    # ------------------------------------------------------------------

    def store_match(self, match_data: Dict, platform: str):
        """Parse and store a full match API response."""
        metadata = match_data.get("metadata", {})
        info = match_data.get("info", {})

        match_id = metadata.get("match_id") or match_data.get("match_id")
        if not match_id:
            logger.warning("Match data missing match_id, skipping.")
            return

        match_row = {
            "match_id": match_id,
            "game_datetime": info.get("game_datetime"),
            "game_length": info.get("game_length"),
            "game_version": info.get("game_version"),
            "queue_id": info.get("queue_id"),
            "tft_set_number": info.get("tft_set_number"),
            "tft_set_core_name": info.get("tft_set_core_name"),
            "platform": platform,
        }

        with self._conn() as conn:
            # Insert match header (ignore if already exists)
            conn.execute(
                """
                INSERT OR IGNORE INTO matches
                    (match_id, game_datetime, game_length, game_version,
                     queue_id, tft_set_number, tft_set_core_name, platform)
                VALUES
                    (:match_id, :game_datetime, :game_length, :game_version,
                     :queue_id, :tft_set_number, :tft_set_core_name, :platform)
                """,
                match_row,
            )

            for p in info.get("participants", []):
                puuid = p.get("puuid", "")
                augments = json.dumps(p.get("augments", []))

                # Upsert participant row
                conn.execute(
                    """
                    INSERT INTO participants
                        (match_id, puuid, placement, level, gold_left, last_round,
                         players_eliminated, time_eliminated, total_damage_to_players, augments)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id, puuid) DO NOTHING
                    """,
                    (
                        match_id,
                        puuid,
                        p.get("placement"),
                        p.get("level"),
                        p.get("gold_left"),
                        p.get("last_round"),
                        p.get("players_eliminated"),
                        p.get("time_eliminated"),
                        p.get("total_damage_to_players"),
                        augments,
                    ),
                )

                participant_id = conn.execute(
                    "SELECT id FROM participants WHERE match_id=? AND puuid=?",
                    (match_id, puuid),
                ).fetchone()["id"]

                # Traits
                for trait in p.get("traits", []):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO participant_traits
                            (participant_id, name, num_units, style, tier_current, tier_total)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            participant_id,
                            trait.get("name"),
                            trait.get("num_units"),
                            trait.get("style"),
                            trait.get("tier_current"),
                            trait.get("tier_total"),
                        ),
                    )

                # Units
                for unit in p.get("units", []):
                    items = json.dumps(
                        unit.get("itemNames", unit.get("items", []))
                    )
                    conn.execute(
                        """
                        INSERT INTO participant_units
                            (participant_id, character_id, name, rarity, tier, items)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            participant_id,
                            unit.get("character_id"),
                            unit.get("name", unit.get("character_id", "")),
                            unit.get("rarity"),
                            unit.get("tier"),
                            items,
                        ),
                    )

        logger.debug("Stored match %s", match_id)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_matches(self, active_traits_only: bool = True) -> List[Dict]:
        """Return all match data as a list of nested dicts for JSON export.

        Args:
            active_traits_only: If True (default), exclude inactive traits (style=0).
        """
        trait_filter = "WHERE style > 0" if active_traits_only else ""

        with self._conn() as conn:
            matches = [dict(r) for r in conn.execute(
                "SELECT * FROM matches ORDER BY game_datetime"
            ).fetchall()]
            participants = [dict(r) for r in conn.execute(
                "SELECT * FROM participants"
            ).fetchall()]
            traits = [dict(r) for r in conn.execute(
                f"SELECT * FROM participant_traits {trait_filter}"
            ).fetchall()]
            units = [dict(r) for r in conn.execute(
                "SELECT * FROM participant_units"
            ).fetchall()]

        traits_by_pid: Dict[int, list] = {}
        for t in traits:
            pid = t["participant_id"]
            traits_by_pid.setdefault(pid, []).append(
                {k: v for k, v in t.items() if k not in ("id", "participant_id")}
            )

        units_by_pid: Dict[int, list] = {}
        for u in units:
            pid = u["participant_id"]
            entry = {k: v for k, v in u.items() if k not in ("id", "participant_id")}
            entry["items"] = json.loads(entry.get("items") or "[]")
            units_by_pid.setdefault(pid, []).append(entry)

        participants_by_match: Dict[str, list] = {}
        for p in participants:
            pid = p["id"]
            entry = {k: v for k, v in p.items() if k not in ("id", "match_id")}
            entry["augments"] = json.loads(entry.get("augments") or "[]")
            entry["traits"] = traits_by_pid.get(pid, [])
            entry["units"] = units_by_pid.get(pid, [])
            participants_by_match.setdefault(p["match_id"], []).append(entry)

        for m in matches:
            m["participants"] = participants_by_match.get(m["match_id"], [])

        return matches
