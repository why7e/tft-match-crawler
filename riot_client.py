"""HTTP client for the Riot Games API with a fixed inter-request delay and retry logic."""

import time
import logging
from typing import Optional, Dict, Any, List

import requests

from config import Config, VALID_LEAGUES

logger = logging.getLogger(__name__)


class RiotClient:
    """HTTP client for the Riot TFT API with a static request delay and retries."""

    MAX_RETRIES = 5

    def __init__(self, config: Config):
        self.config = config
        self.request_delay = config.request_delay
        self.session = requests.Session()
        self.session.headers.update({"X-Riot-Token": config.api_key})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(self, url: str, params: Optional[Dict] = None) -> Any:
        """Make a GET request with a fixed delay and retry on 429 / server errors."""
        for attempt in range(self.MAX_RETRIES):
            time.sleep(self.request_delay)

            try:
                resp = self.session.get(url, params=params, timeout=10)
            except requests.RequestException as exc:
                logger.warning("Network error on attempt %d: %s", attempt + 1, exc)
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning(
                    "Rate limited (429). Waiting %ds before retry (attempt %d/%d).",
                    retry_after,
                    attempt + 1,
                    self.MAX_RETRIES,
                )
                time.sleep(retry_after)
                continue

            if resp.status_code == 404:
                logger.debug("404 Not Found: %s", url)
                return None

            if resp.status_code in (500, 502, 503, 504):
                wait = 2 ** attempt
                logger.warning(
                    "Server error %d. Waiting %ds (attempt %d/%d).",
                    resp.status_code,
                    wait,
                    attempt + 1,
                    self.MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()

        raise RuntimeError(
            f"Failed to fetch {url} after {self.MAX_RETRIES} attempts."
        )

    # ------------------------------------------------------------------
    # tft-league-v1  (platform routing)
    # ------------------------------------------------------------------

    def get_league(self, league: str) -> Dict:
        """GET /tft/league/v1/{league}"""
        if league not in VALID_LEAGUES:
            raise ValueError(f"Unknown league '{league}'. Valid: {sorted(VALID_LEAGUES)}")
        url = f"{self.config.platform_base_url}/tft/league/v1/{league}"
        return self._request(url, params={"queue": self.config.queue})

    # ------------------------------------------------------------------
    # tft-match-v1  (regional routing)
    # ------------------------------------------------------------------

    def get_match_ids_by_puuid(
        self,
        puuid: str,
        count: int = 50,
        start: int = 0,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[str]:
        """GET /tft/match/v1/matches/by-puuid/{puuid}/ids"""
        url = f"{self.config.region_base_url}/tft/match/v1/matches/by-puuid/{puuid}/ids"
        params: Dict[str, Any] = {"count": count, "start": start}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        result = self._request(url, params=params)
        return result if result is not None else []

    def get_match(self, match_id: str) -> Optional[Dict]:
        """GET /tft/match/v1/matches/{matchId}"""
        url = f"{self.config.region_base_url}/tft/match/v1/matches/{match_id}"
        return self._request(url)
