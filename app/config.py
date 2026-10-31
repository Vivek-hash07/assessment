"""Central place for all environment-based settings."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]

# Delay before a transaction becomes eligible for processing (simulates external API calls)
DELAY_SECONDS = int(os.getenv("PROCESSING_DELAY_SECONDS", "30"))

# How long a worker "owns" a claimed row. If it crashes, the row is retried after this.
LEASE_SECONDS = int(os.getenv("LEASE_SECONDS", "120"))

# Max rows a worker claims per poll
CLAIM_BATCH_SIZE = int(os.getenv("CLAIM_BATCH_SIZE", "10"))

# Idle sleep between polls when there is nothing to process
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "1"))
