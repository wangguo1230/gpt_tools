from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PlanType = Literal["plus", "pro5x", "pro20x", "team48"]
LinkMode = Literal["short", "hosted", "long"]


class LinkGenerateRequest(BaseModel):
    token: str = Field(min_length=1, description="Access token、Bearer 或 Session JSON")
    plan: PlanType = "pro5x"
    link_mode: LinkMode = "short"
    proxy: str | None = None
    billing_country: str | None = None
    billing_currency: str | None = None
    team_promo_code: str | None = None
    team_seat_quantity: int | None = Field(default=None, ge=1, le=999)


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
    team_promo_code: str = ""
    team_seat_quantity: int = 0
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


class SubscriptionStatusRequest(BaseModel):
    token: str = Field(min_length=1, description="Access token、Bearer 或 Session JSON")
    proxy: str | None = None


class BillingQueryRequest(BaseModel):
    token: str = Field(min_length=1, description="Access token、Bearer 或 Session JSON")
    proxy: str | None = None


class BillingInvoiceFileRequest(BaseModel):
    slug: str = Field(min_length=1, description="账单文件标识")
    file_type: Literal["invoice", "receipt"] = "invoice"
    proxy: str | None = None


class SubscriptionStatusResponse(BaseModel):
    ok: bool
    account_id: str = ""
    email: str = ""
    plan_type: str = "unknown"
    latest_subscription_plan: str = ""
    has_previously_paid_subscription: bool = False
    has_active_subscription: bool = False
    is_delinquent: bool = False
    is_paid: bool = False
    billing_period: str = ""
    subscription_start_at: str = ""
    subscription_start_source: str = ""
    expires_at: str = ""
    renews_at: str = ""
    cancels_at: str = ""
    billing_currency: str = ""
    purchase_origin_platform: str = ""
    channel_guess: str = ""
    channel_confidence: str = ""
    customer_portal_url: str = ""
    accounts_total: int = 0
    source: str = ""
    error: str = ""


class TokenProfileResponse(BaseModel):
    ok: bool
    source: str = ""
    error: str = ""
    me: dict[str, Any] = Field(default_factory=dict)
    accounts_check: dict[str, Any] = Field(default_factory=dict)
    customer_portal: dict[str, Any] = Field(default_factory=dict)


class BillingInvoiceItem(BaseModel):
    id: str = ""
    date: str = ""
    amount: str = ""
    amount_raw: int = 0
    currency: str = ""
    description: str = ""
    status: str = ""
    card: str = ""
    slug: str = ""
    hosted_invoice_url: str = ""
    invoice_pdf_url: str = ""
    receipt_pdf_url: str = ""


class BillingQueryResponse(BaseModel):
    ok: bool
    profile: dict[str, Any] = Field(default_factory=dict)
    customer: dict[str, Any] = Field(default_factory=dict)
    subscription: dict[str, Any] | None = None
    payment_method: dict[str, Any] | None = None
    invoices: list[BillingInvoiceItem] = Field(default_factory=list)
    count: int = 0
    notice: str = ""
    source: str = ""
    error: str = ""


class BillingInvoiceFileResponse(BaseModel):
    ok: bool
    slug: str = ""
    file_type: str = ""
    url: str = ""
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
