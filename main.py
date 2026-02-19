"""
TFT Match Crawler — entry point.

Usage
-----
  # Run with the default config file (.env):
  python main.py

"""

import logging
import sys

from dotenv import load_dotenv

from config import Config
from database import Database
from riot_client import RiotClient
from collector import Collector


def main():
    env_path = sys.argv[1] if len(sys.argv) > 1 else ".env"
    load_dotenv(env_path, override=True)

    try:
        config = Config.from_env()
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    db = Database(config.db_path)
    client = RiotClient(config)
    collector = Collector(config, db, client)

    try:
        collector.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Progress has been saved to the database.")
        sys.exit(0)


if __name__ == "__main__":
    main()
