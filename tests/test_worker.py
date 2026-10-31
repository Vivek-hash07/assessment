import unittest
from unittest.mock import AsyncMock, patch

from app import config
from app.worker import process_transaction


class ProcessTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_configured_processing_delay(self):
        with patch("app.worker.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await process_transaction("txn_test")

        sleep.assert_awaited_once_with(config.DELAY_SECONDS)
