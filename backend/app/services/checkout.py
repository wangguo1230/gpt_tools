from __future__ import annotations

from hashlib import sha256
from typing import Any

from ..schemas import (
    BillingCurrencyResolveRequest,
    LinkGenerateRequest,
    SubscriptionStatusRequest,
)
from .checkout_client import (
    create_checkout_from_token,
    extract_account_hint_from_input,
    query_me_and_subscription_from_token,
    query_subscription_status_from_token,
    resolve_checkout_billing_details,
)
from .orders import add_log, create_order, mark_failed, mark_success


def _fingerprint_token(raw_token: str) -> str:
    value = str(raw_token or "").strip()
    if not value:
        return ""
    return sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:32]


def generate_checkout_link(payload: LinkGenerateRequest) -> dict[str, Any]:
    token_input = str(payload.token or "").strip()
    if not token_input:
        raise ValueError("请先输入 token")

    hints = extract_account_hint_from_input(token_input)
    order_id = create_order(
        plan_type=payload.plan,
        link_mode=payload.link_mode,
        billing_country=str(payload.billing_country or ""),
        billing_currency=str(payload.billing_currency or ""),
        token_fingerprint=_fingerprint_token(token_input),
        account_email=str(hints.get("email", "") or ""),
        account_plan_type=str(hints.get("plan_type", "") or ""),
    )
    add_log(
        order_id,
        level="info",
        step="checkout_create_started",
        message="开始生成支付链接",
        metadata={
            "plan": payload.plan,
            "link_mode": payload.link_mode,
            "billing_country": str(payload.billing_country or "").upper(),
            "billing_currency": str(payload.billing_currency or "").upper(),
        },
    )

    result = create_checkout_from_token(
        token_input=token_input,
        plan=payload.plan,
        link_mode=payload.link_mode,
        proxy=str(payload.proxy or "").strip(),
        billing_country=str(payload.billing_country or ""),
        billing_currency=str(payload.billing_currency or ""),
    )
    if not result.get("ok"):
        error_message = str(result.get("error") or "生成短链失败")
        mark_failed(order_id, error_code="checkout_create_failed", error_message=error_message)
        add_log(
            order_id,
            level="error",
            step="checkout_create_failed",
            message=error_message,
            metadata={
                "source": str(result.get("source", "") or ""),
                "selected_plan": str(result.get("selected_plan", "") or ""),
            },
        )
        raise ValueError(error_message)

    saved = mark_success(order_id, result)
    add_log(
        order_id,
        level="info",
        step="checkout_created",
        message="支付链接已生成",
        metadata={
            "checkout_url": saved.checkout_url,
            "short_url": saved.short_url,
            "processor_entity": saved.processor_entity,
            "session_id": saved.checkout_session_id,
        },
    )

    response = dict(result)
    response.setdefault("ok", True)
    response.setdefault("error", "")
    response["order_id"] = int(order_id)
    response["order_no"] = str(saved.task_no or "")
    return response


def resolve_billing_currency(payload: BillingCurrencyResolveRequest) -> dict[str, Any]:
    token_input = str(payload.token or "").strip()
    if not token_input:
        raise ValueError("请先输入 token")
    country = str(payload.billing_country or "").strip().upper()
    if not country:
        raise ValueError("请先输入地区代码")

    result = resolve_checkout_billing_details(
        token_input=token_input,
        country=country,
        currency=str(payload.billing_currency or ""),
        proxy=str(payload.proxy or "").strip(),
    )
    if result.get("error"):
        raise ValueError(str(result.get("error")))
    return {
        "ok": True,
        "billing_country": str(result.get("country", "") or ""),
        "billing_currency": str(result.get("currency", "") or ""),
        "source": str(result.get("source", "") or ""),
        "error": "",
    }


def get_subscription_status(payload: SubscriptionStatusRequest) -> dict[str, Any]:
    token_input = str(payload.token or "").strip()
    if not token_input:
        raise ValueError("请先输入 token")
    result = query_subscription_status_from_token(
        token_input=token_input,
        proxy=str(payload.proxy or "").strip(),
    )
    if not result.get("ok"):
        raise ValueError(str(result.get("error") or "订阅状态查询失败"))
    return result


def get_me_and_subscription(payload: SubscriptionStatusRequest) -> dict[str, Any]:
    token_input = str(payload.token or "").strip()
    if not token_input:
        raise ValueError("请先输入 token")
    return query_me_and_subscription_from_token(
        token_input=token_input,
        proxy=str(payload.proxy or "").strip(),
    )
