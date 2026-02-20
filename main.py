"""
TFT Match Crawler — entry point.

Usage
-----
  # Crawl (uses .env by default):
  python main.py
  python main.py path/to/.env

  # Export all stored matches to JSON:
  python main.py export                          # → matches_export.json (active traits only)
  python main.py export out.json                 # → out.json
  python main.py export out.json --all-traits    # include inactive traits (style=0)
"""

import json
import logging
import sys

from dotenv import load_dotenv

from config import Config
from database import Database
from riot_client import RiotClient
from collector import Collector


def export(db: Database, output_path: str, active_traits_only: bool):
    print(f"Exporting match data to {output_path} (active traits only: {active_traits_only})...")
    matches = db.export_matches(active_traits_only=active_traits_only)
    with open(output_path, "w") as f:
        json.dump(matches, f)
    total_participants = sum(len(m["participants"]) for m in matches)
    print(f"Exported {len(matches)} matches, {total_participants} participants → {output_path}")


def main():
    args = sys.argv[1:]

    if args and args[0] == "export":
        output_path = next((a for a in args[1:] if not a.startswith("--")), "matches_export.json")
        active_traits_only = "--all-traits" not in args
        load_dotenv(".env", override=True)
        try:
            config = Config.from_env()
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        db = Database(config.db_path)
        export(db, output_path, active_traits_only)
        return

    env_path = args[0] if args else ".env"
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
