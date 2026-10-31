"""App entrypoint: wires together the DB pool, worker and routes."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.routes import router
from app.worker import run_worker

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await db.create_pool()
    await db.init_schema(app.state.pool)
    worker_task = asyncio.create_task(run_worker(app.state.pool))
    yield
    worker_task.cancel()
    await app.state.pool.close()


app = FastAPI(title="Transaction Webhook Service", lifespan=lifespan)
app.include_router(router)
