"""Quick script to load DB tables into pandas for interactive exploration."""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "career_scout_dev.db"

conn = sqlite3.connect(DB_PATH)

listings = pd.read_sql("SELECT * FROM job_listings", conn)
runs = pd.read_sql("SELECT * FROM scraping_runs", conn)

conn.close()

# Set a breakpoint here and explore `listings` and `runs` in the debugger
print(f"Listings: {len(listings)} rows, Runs: {len(runs)} rows")
