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

# The game_version field in match data is an internal build version, which
# doesn't always line up with the publicly used version. This maps the internal
# build number to the real patch version. Taken from the DevRel discord.
VERSION_MAPPING = {
    """2025"""
    "15.1": "13.3",
    "15.2": "13.4",
    "15.3": "13.5",
    "15.4": "13.6",
    "15.5": "13.7",
    "15.6": "13.8",
    "15.7": "14.1",
    "15.8": "14.2",
    "15.9": "14.3",
    "15.10": "14.4",
    "15.11": "14.5",
    "15.12": "14.6",
    "15.13": "14.7",
    "15.14": "14.8",
    "15.15": "15.1",
    "15.16": "15.2",
    "15.17": "15.3",
    "15.18": "15.4",
    "15.19": "15.5",
    "15.20": "15.6",
    "15.21": "15.7",
    "15.22": "15.8",
    "15.23": "15.9",
    "15.24": "16.1",
    """2026"""
    "16.1": "16.2",
    "16.2": "16.3",
    "16.3": "16.4",
    "16.4": "16.5",
    "16.5": "16.6",
    "16.6": "16.7",
    "16.7": "16.8",
    "16.8": "17.1",
    "16.9": "17.2",
    "16.10": "17.3",
    "16.11": "17.4",
    "16.12": "17.5",
    "16.13": "17.6",
    "16.14": "17.7",
    "16.15": "17.8",
    "16.16": "18.1",
    "16.17": "18.2",
    "16.18": "18.3",
    "16.19": "18.4",
    "16.20": "18.5",
    "16.21": "18.6",
    "16.22": "18.7",
    "16.23": "18.8",
    "16.24": "19.1",
}


@dataclass
class Config:
    # --- Defaults ---
    api_key: str = ""
    platform: str = "na1"
    leagues: List[str] = field(default_factory=lambda: ["challenger"])
    queue: str = "RANKED_TFT"
    matches_per_player: int = 50
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    db_path: str = "tft_data.db"
    request_delay: float = 1.2
    log_level: str = "INFO"

    # --- Checks ---
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
