"""Background worker: claims due transactions and processes them."""
import asyncio
import logging

import asyncpg

from app import config, db

log = logging.getLogger("txn.worker")


async def process_transaction(transaction_id: str) -> None:
    """Simulate a slow external transaction operation."""
    log.info("processing %s", transaction_id)
    await asyncio.sleep(config.DELAY_SECONDS)


async def process_and_mark(pool: asyncpg.Pool, transaction_id: str) -> None:
    try:
        await process_transaction(transaction_id)
        await db.mark_processed(pool, transaction_id)
        log.info("processed %s", transaction_id)
    except Exception:
        # The lease expires and the row is retried automatically.
        log.exception("failed %s, will retry after lease", transaction_id)


async def run_worker(pool: asyncpg.Pool) -> None:
    while True:
        try:
            ids = await db.claim_due_transactions(
                pool,
                max(config.LEASE_SECONDS, config.DELAY_SECONDS + 30),
                config.CLAIM_BATCH_SIZE,
            )
            if ids:
                await asyncio.gather(
                    *(process_and_mark(pool, tid) for tid in ids)
                )
            if not ids:
                await asyncio.sleep(config.POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("worker loop error")
            await asyncio.sleep(5)
