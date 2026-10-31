"""Request/response models."""
from decimal import Decimal

from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    transaction_id: str = Field(min_length=1)
    source_account: str
    destination_account: str
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
