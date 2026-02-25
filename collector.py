"""
TFT data collection pipeline.

1. Fetch league entries — queries the league endpoint for all player PUUIDs in the
   configured league(s).
2. Collect match IDs — fetches up to `matches_per_player` recent match IDs
   per player, optionally filtered by time window. 
   - As of 20/02, matches/by-puuid/ endpoint does not respect startTime or endTime.
     Ideally this should be the main method, and we can re-query to get all games
     played within the current period.
3. Fetch match data — retrieves and stores full match data for every unique
   match ID, skipping any already in the database.
"""

import logging
from typing import Dict, List, Set

from config import Config
from database import Database
from riot_client import RiotClient

logger = logging.getLogger(__name__)


class Collector:
    def __init__(self, config: Config, db: Database, client: RiotClient):
        self.config = config
        self.db = db
        self.client = client

    # ------------------------------------------------------------------
    # Step 1: Fetch league entries
    # ------------------------------------------------------------------

    def fetch_league_entries(self) -> List[Dict]:
        """
        Query the league endpoint for each configured league and return a
        list of player dicts, each with a `puuid` field.
        Players are upserted to the database so league data stays current.
        """
        entries: Dict[str, Dict] = {}  # puuid → entry

        for league in self.config.leagues:
            logger.info("Fetching %s league (%s)...", league.upper(), self.config.platform)
            data = self.client.get_league(league)
            if not data:
                logger.warning("No data returned for %s league.", league)
                continue

            league_entries = data.get("entries", [])
            logger.info("Found %d entries in %s.", len(league_entries), league.upper())

            for entry in league_entries:
                puuid = entry.get("puuid")
                if not puuid or puuid in entries:
                    continue
                entries[puuid] = {
                    "puuid": puuid,
                    "summoner_id": None,
                    "summoner_name": "",
                    "league": league.upper(),
                    "rank": entry.get("rank", ""),
                    "lp": entry.get("leaguePoints", 0),
                    "wins": entry.get("wins", 0),
                    "losses": entry.get("losses", 0),
                    "platform": self.config.platform,
                }

        logger.info("Total unique players: %d", len(entries))

        for player in entries.values():
            self.db.upsert_player(player)

        return list(entries.values())

    # ------------------------------------------------------------------
    # Step 2: Collect match IDs
    # ------------------------------------------------------------------

    _MATCH_ID_BATCH = 200  # Maximum IDs the API returns per request

    def collect_match_ids(self, entries: List[Dict]) -> Set[str]:
        """
        For each player, fetch recent match IDs.
        
        When start_time is configured, we query the maximum number of IDs until
        we reach a match before start_time or exhaust the player's history.
        Without start_time, a single request of `matches_per_player` is made.
        """
        all_match_ids: Set[str] = set()
        known_match_ids = self.db.get_known_match_ids()
        known_datetimes = self.db.get_match_datetimes() if self.config.start_time else {}

        logger.info(
            "Collecting match IDs for %d players...",
            len(entries),
        )

        for i, entry in enumerate(entries):
            puuid = entry["puuid"]

            if not self.config.start_time:
                # No time filter — single request, original behaviour.
                match_ids = self.client.get_match_ids_by_puuid(
                    puuid,
                    count=self.config.matches_per_player,
                    end_time=self.config.end_time,
                )
                all_match_ids.update(set(match_ids) - known_match_ids)
            else:
                # Paginate until we find a batch that reaches older than start_time
                # or exhaust the player's history.
                offset = 0
                while True:
                    batch = self.client.get_match_ids_by_puuid(
                        puuid,
                        count=self._MATCH_ID_BATCH,
                        start=offset,
                        end_time=self.config.end_time,
                    )
                    if not batch:
                        break

                    all_match_ids.update(set(batch) - known_match_ids)
                    offset += self._MATCH_ID_BATCH

                    # Check if last match in this batch is before startTime
                    # If so, we do not add any more batches
                    last_id = batch[-1]
                    logger.debug("Final match ID in this batch: %s", last_id)

                    match_data = self.client.get_match(last_id)
                    if match_data is None:
                        logger.warning("Match %s returned None (404?), skipping.", last_id)
                        continue
                    if match_data.get("info", {}).get("game_datetime", {}) < self.config.start_time:
                        logger.debug("Batch reaches startTime, final batch for PUUID %s", puuid)
                        break

                    try:
                        self.db.store_match(match_data, platform=self.config.platform)
                    except Exception as exc:
                        logger.error("Failed to store match %s: %s", last_id, exc)


            if (i + 1) % 50 == 0 or (i + 1) == len(entries):
                logger.info(
                    "  Match ID collection: %d/%d players — %d unique new IDs so far.",
                    i + 1,
                    len(entries),
                    len(all_match_ids),
                )

        logger.info(
            "Total new match IDs to fetch: %d  (skipping %d already stored)",
            len(all_match_ids),
            len(known_match_ids),
        )
        return all_match_ids

    # ------------------------------------------------------------------
    # Step 3: Fetch and store match data
    # ------------------------------------------------------------------

    def fetch_matches(self, match_ids: Set[str]):
        """Fetch full match data for each ID and store it in the database."""
        match_list = sorted(match_ids, reverse = True) # Descending order, pull newest first.
        total = len(match_list)

        if total == 0:
            logger.info("No new matches to fetch.")
            return

        logger.info("Fetching %d matches...", total)
        stored = 0
        failed = 0

        for i, match_id in enumerate(match_list):
            if self.db.match_exists(match_id):
                continue

            match_data = self.client.get_match(match_id)
            if match_data is None:
                logger.warning("Match %s returned None (404?), skipping.", match_id)
                failed += 1
                continue

            try:
                self.db.store_match(match_data, platform=self.config.platform)
                stored += 1
            except Exception as exc:
                logger.error("Failed to store match %s: %s", match_id, exc)
                failed += 1

            if (i + 1) % 100 == 0 or (i + 1) == total:
                logger.info(
                    "  Matches: %d/%d fetched — %d stored, %d failed.",
                    i + 1,
                    total,
                    stored,
                    failed,
                )

        logger.info(
            "Match fetch complete. Stored: %d, Failed/Skipped: %d", stored, failed
        )

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run(self):
        """Execute the full data collection pipeline."""
        time_window_str = (
            f"start_time={self.config.start_time} end_time={self.config.end_time}"
            if self.config.start_time or self.config.end_time
            else "no time filter"
        )
        logger.info(
            "=== TFT Match Crawler starting | platform=%s region=%s leagues=%s | %s ===",
            self.config.platform,
            self.config.region,
            self.config.leagues,
            time_window_str,
        )

        # Step 1
        entries = self.fetch_league_entries()
        if not entries:
            logger.error("No league entries found. Exiting.")
            return

        # Step 2
        match_ids = self.collect_match_ids(entries)

        # Step 3
        self.fetch_matches(match_ids)

        logger.info("=== Collection complete ===")
