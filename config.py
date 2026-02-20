"""
Configuration for the TFT match crawler.

Settings are read from environment variables, which are loaded from a .env
file by main.py before this module is used. See .env.example for all
available variables and their defaults.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

# Maps platform routing values to their regional routing cluster.
# Platform values are used by tft-league-v1 and tft-summoner-v1.
# Regional values are used by tft-match-v1.
PLATFORM_TO_REGION = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
    "oc1": "sea",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}

VALID_LEAGUES = {"challenger", "grandmaster", "master"}


@dataclass
class Config:
    # --- API auth ---
    api_key: str = ""

    # --- Routing ---
    platform: str = "na1"

    # --- Collection settings ---
    leagues: List[str] = field(default_factory=lambda: ["challenger"])
    queue: str = "RANKED_TFT"
    matches_per_player: int = 50

    # --- Time window (optional) ---
    # Unix timestamps in seconds. When set, only matches within this window
    # are returned by the match-IDs endpoint. Useful for patch-specific pulls.
    start_time: Optional[int] = None
    end_time: Optional[int] = None

    # --- Storage ---
    db_path: str = "tft_data.db"

    # --- Rate limiting ---
    request_delay: float = 1.2  # seconds between requests

    # --- Logging ---
    log_level: str = "INFO"

    def __post_init__(self):
        if not self.api_key:
            raise ValueError(
                "RIOT_API_KEY is not set. Add it to your .env file:\n"
                "  RIOT_API_KEY=RGAPI-xxxx-xxxx-xxxx"
            )
        self.platform = self.platform.lower()
        if self.platform not in PLATFORM_TO_REGION:
            raise ValueError(
                f"Unknown PLATFORM '{self.platform}'. "
                f"Valid options: {sorted(PLATFORM_TO_REGION)}"
            )
        self.leagues = [l.lower() for l in self.leagues]
        for league in self.leagues:
            if league not in VALID_LEAGUES:
                raise ValueError(
                    f"Unknown league '{league}' in LEAGUES. "
                    f"Valid options: {sorted(VALID_LEAGUES)}"
                )
        if self.matches_per_player < 1 or self.matches_per_player > 200:
            raise ValueError("MATCHES_PER_PLAYER must be between 1 and 200.")
        if self.start_time is not None and self.end_time is not None:
            if self.start_time >= self.end_time:
                raise ValueError("START_TIME must be earlier than END_TIME.")

    @property
    def region(self) -> str:
        """Regional routing cluster derived from the platform."""
        return PLATFORM_TO_REGION[self.platform]

    @property
    def platform_base_url(self) -> str:
        return f"https://{self.platform}.api.riotgames.com"

    @property
    def region_base_url(self) -> str:
        return f"https://{self.region}.api.riotgames.com"

    @classmethod
    def from_env(cls) -> "Config":
        """Build Config from environment variables.

        Call dotenv.load_dotenv() before this to populate the environment
        from a .env file.
        """
        leagues_raw = os.environ.get("LEAGUES", "challenger")
        leagues = [l.strip() for l in leagues_raw.split(",") if l.strip()]

        start_raw = os.environ.get("START_TIME", "").strip()
        end_raw = os.environ.get("END_TIME", "").strip()

        return cls(
            api_key=os.environ.get("RIOT_API_KEY", ""),
            platform=os.environ.get("PLATFORM", "na1"),
            leagues=leagues,
            queue=os.environ.get("QUEUE", "RANKED_TFT"),
            matches_per_player=int(os.environ.get("MATCHES_PER_PLAYER", "50")),
            start_time=int(start_raw) if start_raw else None,
            end_time=int(end_raw) if end_raw else None,
            db_path=os.environ.get("DB_PATH", "tft_data.db"),
            request_delay=float(os.environ.get("REQUEST_DELAY", "1.2")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
