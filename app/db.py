"""Database layer: connection pool, schema, and every SQL query.

Nothing outside this file should contain SQL.
"""
import asyncpg

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id       TEXT PRIMARY KEY,
    source_account       TEXT NOT NULL,
    destination_account  TEXT NOT NULL,
    amount               NUMERIC(18,2) NOT NULL,
    currency             TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'PROCESSING',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    process_after        TIMESTAMPTZ NOT NULL,
    locked_until         TIMESTAMPTZ,
    processed_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_txn_pending
    ON transactions (process_after) WHERE status = 'PROCESSING';
"""

INSERT_SQL = """
INSERT INTO transactions
    (transaction_id, source_account, destination_account, amount, currency, process_after)
VALUES ($1, $2, $3, $4, $5, now())
ON CONFLICT (transaction_id) DO NOTHING
"""

CLAIM_SQL = """
UPDATE transactions
SET locked_until = now() + make_interval(secs => $1)
WHERE transaction_id IN (
    SELECT transaction_id FROM transactions
    WHERE status = 'PROCESSING'
      AND process_after <= now()
      AND (locked_until IS NULL OR locked_until < now())
    ORDER BY process_after
    LIMIT $2
    FOR UPDATE SKIP LOCKED
)
RETURNING transaction_id
"""

COMPLETE_SQL = """
UPDATE transactions
SET status = 'PROCESSED', processed_at = now(), locked_until = NULL
WHERE transaction_id = $1 AND status = 'PROCESSING'
"""

GET_SQL = "SELECT * FROM transactions WHERE transaction_id = $1"


# ---------- pool / schema ----------

async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)


async def init_schema(pool: asyncpg.Pool) -> None:
    await pool.execute(SCHEMA)


# ---------- queries ----------

async def insert_transaction(
    pool: asyncpg.Pool,
    transaction_id: str,
    source_account: str,
    destination_account: str,
    amount,
    currency: str,
) -> None:
    """Persist a transaction for immediate background processing."""
    await pool.execute(
        INSERT_SQL,
        transaction_id, source_account, destination_account,
        amount, currency,
    )


async def get_transaction(pool: asyncpg.Pool, transaction_id: str):
    return await pool.fetchrow(GET_SQL, transaction_id)


async def claim_due_transactions(
    pool: asyncpg.Pool, lease_seconds: float, batch_size: int
) -> list[str]:
    """Lease up to `batch_size` due rows; safe with multiple workers (SKIP LOCKED)."""
    rows = await pool.fetch(CLAIM_SQL, float(lease_seconds), batch_size)
    return [r["transaction_id"] for r in rows]


async def mark_processed(pool: asyncpg.Pool, transaction_id: str) -> None:
    await pool.execute(COMPLETE_SQL, transaction_id)
