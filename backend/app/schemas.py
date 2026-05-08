from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PlanType = Literal["pro", "plus", "pro5x", "pro20x"]
LinkMode = Literal["short", "hosted", "long"]


class LinkGenerateRequest(BaseModel):
    token: str = Field(min_length=1, description="Access token、Bearer 或 Session JSON")
    plan: PlanType = "pro"
    link_mode: LinkMode = "short"
    proxy: str | None = None
    billing_country: str | None = None
    billing_currency: str | None = None


class LinkGenerateResponse(BaseModel):
    ok: bool
    order_id: int = 0
    order_no: str = ""
    selected_plan: str = ""
    link_mode: str = ""
    checkout_url: str = ""
    checkout_short_url: str = ""
    stripe_checkout_url: str = ""
    checkout_session_id: str = ""
    processor_entity: str = ""
    source: str = ""
    billing_country: str = ""
    billing_currency: str = ""
    billing_source: str = ""
    payment_methods: dict[str, str] = Field(default_factory=dict)
    error: str = ""


class BillingCurrencyResolveRequest(BaseModel):
    token: str = Field(min_length=1, description="Access token、Bearer 或 Session JSON")
    billing_country: str = Field(min_length=1, description="账单国家/地区代码，如 US")
    billing_currency: str | None = None
    proxy: str | None = None


class BillingCurrencyResolveResponse(BaseModel):
    ok: bool
    billing_country: str = ""
    billing_currency: str = ""
    source: str = ""
    error: str = ""


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_no: str
    plan_type: str
    link_mode: str
    status: str
    checkout_url: str
    short_url: str
    stripe_checkout_url: str
    checkout_session_id: str
    processor_entity: str
    source: str
    billing_country: str
    billing_currency: str
    account_email: str
    account_plan_type: str
    last_error_code: str
    last_error_message: str
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    ok: bool
    items: list[OrderSummary]
    total: int
    limit: int
    offset: int


class OrderLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    step: str
    message: str
    metadata_json: dict
    created_at: datetime


class OrderDetailResponse(BaseModel):
    ok: bool
    item: OrderSummary
    logs: list[OrderLogItem]
