"""Background worker: claims due transactions and processes them."""
import asyncio
import logging

import asyncpg

from app import config, db

log = logging.getLogger("txn.worker")


async def process_transaction(transaction_id: str) -> None:
    """Placeholder for real work (external API calls, ledger updates, ...).

    The 30s delay is already enforced by `process_after` in the database.
    """
    await asyncio.sleep(0)


async def run_worker(pool: asyncpg.Pool) -> None:
    while True:
        try:
            ids = await db.claim_due_transactions(
                pool, config.LEASE_SECONDS, config.CLAIM_BATCH_SIZE
            )
            for tid in ids:
                try:
                    await process_transaction(tid)
                    await db.mark_processed(pool, tid)
                    log.info("processed %s", tid)
                except Exception:
                    # Lease expires -> row is retried automatically
                    log.exception("failed %s, will retry after lease", tid)
            if not ids:
                await asyncio.sleep(config.POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("worker loop error")
            await asyncio.sleep(5)
