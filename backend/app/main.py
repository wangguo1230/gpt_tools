from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from .database import init_database
from .schemas import (
    BillingCurrencyResolveRequest,
    BillingCurrencyResolveResponse,
    LinkGenerateRequest,
    LinkGenerateResponse,
    OrderDetailResponse,
    OrderListResponse,
    SubscriptionStatusRequest,
    SubscriptionStatusResponse,
    TokenProfileResponse,
)
from .services.checkout import (
    generate_checkout_link,
    get_me_and_subscription,
    get_subscription_status,
    resolve_billing_currency,
)
from .services.orders import get_order_detail, list_orders


def _cors_origins() -> list[str]:
    raw = str(
        os.getenv("GPT_TOOLS_CORS_ORIGINS")
        or "http://127.0.0.1:5173,http://localhost:5173"
    )
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or ["*"]


app = FastAPI(title="GPT Tools API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_database()


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "gpt_tools_backend", "version": "2.0.0"}


@app.post("/api/links/generate", response_model=LinkGenerateResponse)
async def api_generate_link(payload: LinkGenerateRequest) -> LinkGenerateResponse:
    try:
        result = await run_in_threadpool(generate_checkout_link, payload)
        return LinkGenerateResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/regions/resolve-currency", response_model=BillingCurrencyResolveResponse)
async def api_resolve_currency(payload: BillingCurrencyResolveRequest) -> BillingCurrencyResolveResponse:
    try:
        result = await run_in_threadpool(resolve_billing_currency, payload)
        return BillingCurrencyResolveResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/subscription/status", response_model=SubscriptionStatusResponse)
async def api_subscription_status(payload: SubscriptionStatusRequest) -> SubscriptionStatusResponse:
    try:
        result = await run_in_threadpool(get_subscription_status, payload)
        return SubscriptionStatusResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/token/profile", response_model=TokenProfileResponse)
async def api_token_profile(payload: SubscriptionStatusRequest) -> TokenProfileResponse:
    try:
        result = await run_in_threadpool(get_me_and_subscription, payload)
        return TokenProfileResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/orders", response_model=OrderListResponse)
async def api_list_orders(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    plan_type: str = Query(default=""),
) -> OrderListResponse:
    try:
        payload = await run_in_threadpool(
            list_orders,
            limit=limit,
            offset=offset,
            keyword=keyword,
            status=status,
            plan_type=plan_type,
        )
        return OrderListResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"订单查询失败: {exc}") from exc


@app.get("/api/orders/{order_id}", response_model=OrderDetailResponse)
async def api_order_detail(
    order_id: int,
    log_limit: int = Query(default=30, ge=1, le=100),
) -> OrderDetailResponse:
    try:
        payload = await run_in_threadpool(get_order_detail, order_id=order_id, log_limit=log_limit)
        return OrderDetailResponse(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"订单详情查询失败: {exc}") from exc
