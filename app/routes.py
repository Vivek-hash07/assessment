"""HTTP layer: endpoints only. No SQL, no background logic."""
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request

from app import config, db
from app.schemas import WebhookPayload
from app.utils import iso

router = APIRouter()


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


@router.get("/")
async def health():
    return {"status": "HEALTHY", "current_time": iso(datetime.now(timezone.utc))}


@router.post("/v1/webhooks/transactions", status_code=202)
async def receive_webhook(payload: WebhookPayload, pool: asyncpg.Pool = Depends(get_pool)):
    await db.insert_transaction(
        pool,
        payload.transaction_id,
        payload.source_account,
        payload.destination_account,
        payload.amount,
        payload.currency.upper(),
        config.DELAY_SECONDS,
    )
    return {"status": "accepted"}


@router.get("/v1/transactions/{transaction_id}")
async def get_transaction(transaction_id: str, pool: asyncpg.Pool = Depends(get_pool)):
    r = await db.get_transaction(pool, transaction_id)
    if not r:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return [{
        "transaction_id": r["transaction_id"],
        "source_account": r["source_account"],
        "destination_account": r["destination_account"],
        "amount": float(r["amount"]),
        "currency": r["currency"],
        "status": r["status"],
        "created_at": iso(r["created_at"]),
        "processed_at": iso(r["processed_at"]),
    }]
