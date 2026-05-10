from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

from curl_cffi import requests as curl_requests

from .checkout_client import BACKEND_API_BASE, CHATGPT_API_BASE, extract_access_token_from_input

PAY_OPENAI_BASE = "https://pay.openai.com/v1/billing_portal/sessions"
INVOICE_DATA_BASE = "https://invoicedata.stripe.com"
MAX_BILLING_TOKEN_INPUT_LENGTH = 256_000
BILLING_QUERY_TIMEOUT_SECONDS = 60
BILLING_FILE_TIMEOUT_SECONDS = 20
_SLUG_RE = re.compile(r"[A-Za-z0-9/_-]+")


class BillingToolError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class BillingPortalSession:
    session_api_key: str
    portal_session_id: str
    stripe_account: str


def query_billing_from_token(*, token_input: str, proxy: str = "") -> dict[str, Any]:
    access_token = _extract_billing_access_token(token_input)

    portal_url = ""
    portal_error = ""
    try:
        portal_url = _get_customer_portal(access_token=access_token, proxy=proxy)
    except BillingToolError as exc:
        if exc.status_code == 401:
            raise
        portal_error = str(exc)

    if not portal_url:
        return {
            "ok": True,
            "profile": {},
            "customer": {},
            "subscription": None,
            "payment_method": None,
            "invoices": [],
            "count": 0,
            "notice": portal_error or "该账户暂无可查询的订阅账单",
            "source": "billing_portal",
            "error": "",
        }

    session = _get_portal_session(portal_url=portal_url, proxy=proxy)
    raw_invoices = _get_invoices(session=session, proxy=proxy)
    invoices = [_format_invoice(item) for item in raw_invoices]

    return {
        "ok": True,
        "profile": {},
        "customer": {},
        "subscription": None,
        "payment_method": None,
        "invoices": invoices,
        "count": len(invoices),
        "notice": "",
        "source": "billing_portal",
        "error": "",
    }


def resolve_billing_invoice_file_url(*, slug: str, file_type: str, proxy: str = "") -> str:
    clean_slug = str(slug or "").strip()
    clean_type = str(file_type or "").strip().lower()
    if clean_type not in {"invoice", "receipt"}:
        raise BillingToolError("账单文件类型无效")
    if (
        not clean_slug
        or len(clean_slug) > 512
        or not _SLUG_RE.fullmatch(clean_slug)
    ):
        raise BillingToolError("账单文件标识无效")

    url = _resolve_invoice_file_url(clean_slug, clean_type, proxy=proxy)
    if not url:
        raise BillingToolError("未获取到账单文件链接", 404)
    return url


def _extract_billing_access_token(token_input: str) -> str:
    value = str(token_input or "").strip()
    if not value:
        raise BillingToolError("请填写 Session JSON 或 access token")
    if len(value) > MAX_BILLING_TOKEN_INPUT_LENGTH:
        raise BillingToolError("输入内容超过允许长度")
    try:
        access_token = extract_access_token_from_input(value)
    except ValueError as exc:
        raise BillingToolError(str(exc)) from exc
    if not access_token:
        raise BillingToolError("未解析到 access token")
    return access_token


def _chatgpt_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": CHATGPT_API_BASE,
        "Referer": f"{CHATGPT_API_BASE}/",
        "oai-language": "zh-CN",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    }


def _build_proxies(proxy: str) -> dict[str, str] | None:
    value = str(proxy or "").strip()
    if not value:
        return None
    return {"http": value, "https": value}


def _request_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = BILLING_QUERY_TIMEOUT_SECONDS,
    allow_redirects: bool = True,
    proxy: str = "",
):
    try:
        return curl_requests.get(
            url,
            headers=headers,
            proxies=_build_proxies(proxy),
            impersonate="chrome",
            timeout=timeout,
            allow_redirects=allow_redirects,
        )
    except Exception as exc:
        raise BillingToolError(f"连接账单服务失败: {str(exc)[:160]}", 502) from exc


def _response_json(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _get_me_info(*, access_token: str, proxy: str = "") -> dict[str, Any]:
    response = _request_get(
        f"{BACKEND_API_BASE}/me",
        headers=_chatgpt_headers(access_token),
        timeout=BILLING_QUERY_TIMEOUT_SECONDS,
        proxy=proxy,
    )
    if response.status_code == 401:
        raise BillingToolError("Token 已过期或无效，请重新获取", 401)
    if response.status_code >= 400:
        raise BillingToolError(f"查询账号信息失败 ({response.status_code})", 502)
    data = _response_json(response)

    plan_type = "free"
    has_active_subscription = False
    expires_at: str | None = None
    accounts = data.get("accounts", {})
    if isinstance(accounts, dict):
        for account in accounts.values():
            if not isinstance(account, dict):
                continue
            entitlement = account.get("entitlement") or {}
            raw_plan = str(entitlement.get("subscription_plan", "") or "")
            inferred = _infer_plan_type(raw_plan)
            if inferred:
                plan_type = inferred
            has_active_subscription = bool(
                entitlement.get("has_active_subscription", False) or has_active_subscription
            )
            expires_at = str(entitlement.get("expires_at", "") or "").strip() or expires_at
            break

    return {
        "email": str(data.get("email", "") or "").strip(),
        "name": str(data.get("name", "") or "").strip(),
        "phone": str(data.get("phone_number", "") or "").strip(),
        "plan_type": plan_type,
        "has_active_subscription": has_active_subscription,
        "expires_at": expires_at or "",
    }


def _get_customer_portal(*, access_token: str, proxy: str = "") -> str:
    response = _request_get(
        f"{BACKEND_API_BASE}/payments/customer_portal",
        headers=_chatgpt_headers(access_token),
        timeout=BILLING_QUERY_TIMEOUT_SECONDS,
        proxy=proxy,
    )
    if response.status_code == 401:
        raise BillingToolError("Token 已过期或无效，请重新获取", 401)
    if response.status_code == 404:
        raise BillingToolError("该账户无订阅记录")
    if response.status_code >= 400:
        raise BillingToolError(f"获取账单门户失败 ({response.status_code})", 502)
    data = _response_json(response)
    portal_url = str(data.get("url", "") or "").strip()
    if not portal_url:
        raise BillingToolError("账单门户未返回可用链接", 502)
    return portal_url


def _get_portal_session(*, portal_url: str, proxy: str = "") -> BillingPortalSession:
    response = _request_get(
        portal_url,
        timeout=BILLING_QUERY_TIMEOUT_SECONDS,
        allow_redirects=True,
        proxy=proxy,
    )
    if response.status_code >= 400:
        raise BillingToolError(f"打开账单门户失败 ({response.status_code})", 502)
    html = str(response.text or "")

    key_match = re.search(r'session_api_key["\s:&;quot]+?(ek_live_[A-Za-z0-9_-]+)', html)
    if not key_match:
        raise BillingToolError("无法提取账单门户 session key", 502)
    session_match = re.search(r"(bps_[A-Za-z0-9]+)", html)
    if not session_match:
        raise BillingToolError("无法提取账单门户 session id", 502)
    account_match = re.search(r"(acct_[A-Za-z0-9]+)", html)

    return BillingPortalSession(
        session_api_key=key_match.group(1),
        portal_session_id=session_match.group(1),
        stripe_account=account_match.group(1) if account_match else "",
    )


def _stripe_headers(session: BillingPortalSession) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {session.session_api_key}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "stripe-version": "2025-06-30.basil",
        "stripe-livemode": "true",
        "x-stripe-csrf-token": "fake-deprecated-token",
    }
    if session.stripe_account:
        headers["stripe-account"] = session.stripe_account
    return headers


def _get_customer(*, session: BillingPortalSession, proxy: str = "") -> dict[str, Any]:
    response = _request_get(
        f"{PAY_OPENAI_BASE}/{session.portal_session_id}/customer",
        headers=_stripe_headers(session),
        timeout=BILLING_QUERY_TIMEOUT_SECONDS,
        proxy=proxy,
    )
    if response.status_code >= 400:
        raise BillingToolError(f"查询 customer 失败 ({response.status_code})", 502)
    return _response_json(response)


def _get_subscriptions(*, session: BillingPortalSession, proxy: str = "") -> dict[str, Any]:
    url = (
        f"{PAY_OPENAI_BASE}/{session.portal_session_id}/subscriptions"
        "?expand[]=data.default_payment_method"
        "&expand[]=data.items.price_details.product"
        "&expand[]=data.items.price_details.recurring"
    )
    response = _request_get(
        url,
        headers=_stripe_headers(session),
        timeout=BILLING_QUERY_TIMEOUT_SECONDS,
        proxy=proxy,
    )
    if response.status_code >= 400:
        raise BillingToolError(f"查询 subscription 失败 ({response.status_code})", 502)
    return _response_json(response)


def _get_payment_methods(*, session: BillingPortalSession, proxy: str = "") -> dict[str, Any]:
    response = _request_get(
        f"{PAY_OPENAI_BASE}/{session.portal_session_id}/payment_methods",
        headers=_stripe_headers(session),
        timeout=BILLING_QUERY_TIMEOUT_SECONDS,
        proxy=proxy,
    )
    if response.status_code >= 400:
        raise BillingToolError(f"查询 payment methods 失败 ({response.status_code})", 502)
    return _response_json(response)


def _get_invoices(*, session: BillingPortalSession, proxy: str = "") -> list[dict[str, Any]]:
    include_fields = (
        "data.id,has_more,"
        "data.amount_due,data.currency,"
        "data.effective_at,data.finalized_at,"
        "data.hosted_invoice_url,"
        "data.lines.data.description,"
        "data.lines.data.short_description,"
        "data.payment_intent.payment_method.card.brand,"
        "data.payment_intent.payment_method.card.last4,"
        "data.status"
    )

    invoices: list[dict[str, Any]] = []
    starting_after = ""
    while True:
        url = (
            f"{PAY_OPENAI_BASE}/{session.portal_session_id}/invoices"
            "?expand[]=data.payment_intent.payment_method"
            f"&include_only[]={include_fields}"
            "&limit=10"
        )
        if starting_after:
            url += f"&starting_after={quote(starting_after)}"
        response = _request_get(
            url,
            headers=_stripe_headers(session),
            timeout=BILLING_QUERY_TIMEOUT_SECONDS,
            proxy=proxy,
        )
        if response.status_code >= 400:
            raise BillingToolError(f"查询发票失败 ({response.status_code})", 502)
        data = _response_json(response)
        page_items = data.get("data", [])
        if not isinstance(page_items, list):
            break
        invoices.extend([item for item in page_items if isinstance(item, dict)])
        if not data.get("has_more") or not page_items:
            break
        starting_after = str(page_items[-1].get("id", "") or "")
        if not starting_after:
            break
    return invoices


def _profile_from_token(access_token: str) -> dict[str, Any]:
    try:
        payload_part = access_token.split(".")[1]
        payload_part += "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_part))
    except Exception:
        return {
            "email": "",
            "name": "",
            "phone": "",
            "plan_type": "",
            "has_active_subscription": False,
            "expires_at": "",
            "email_verified": False,
        }

    profile = payload.get("https://api.openai.com/profile", {}) or {}
    auth_info = payload.get("https://api.openai.com/auth", {}) or {}
    return {
        "email": str(profile.get("email", "") or "").strip(),
        "name": "",
        "phone": "",
        "plan_type": str(auth_info.get("chatgpt_plan_type", "") or "").strip(),
        "has_active_subscription": False,
        "expires_at": "",
        "email_verified": bool(profile.get("email_verified", False)),
    }


def _format_customer(customer: dict[str, Any]) -> dict[str, Any]:
    address = customer.get("address") or {}
    parts = [
        address.get("line1"),
        address.get("line2"),
        address.get("city"),
        address.get("state"),
        address.get("postal_code"),
        address.get("country"),
    ]
    return {
        "name": str(customer.get("name", "") or ""),
        "email": str(customer.get("email", "") or ""),
        "phone": str(customer.get("phone", "") or ""),
        "address": ", ".join([str(part) for part in parts if part]),
    }


def _format_subscription(subscription_data: dict[str, Any]) -> dict[str, Any] | None:
    subscriptions = subscription_data.get("data", []) if isinstance(subscription_data, dict) else []
    if not subscriptions or not isinstance(subscriptions, list):
        return None
    subscription = subscriptions[0] if isinstance(subscriptions[0], dict) else {}
    if not subscription:
        return None

    items = subscription.get("items") or []
    plan_name = ""
    interval = ""
    interval_count = 1
    amount = 0
    currency = ""
    if items and isinstance(items, list) and isinstance(items[0], dict):
        price_details = items[0].get("price_details") or items[0].get("price") or {}
        if not isinstance(price_details, dict):
            price_details = {}
        product = price_details.get("product") or {}
        plan_name = str(product.get("name", "") or "") if isinstance(product, dict) else ""
        recurring = price_details.get("recurring") or {}
        if not isinstance(recurring, dict):
            recurring = {}
        interval = str(recurring.get("interval", "") or "")
        try:
            interval_count = int(recurring.get("interval_count", 1) or 1)
        except Exception:
            interval_count = 1
        try:
            amount = int(price_details.get("unit_amount", 0) or 0)
        except Exception:
            amount = 0
        currency = str(price_details.get("currency", "") or "").upper()

    current_period_end = subscription.get("current_period_end") or subscription.get("min_period_end") or 0
    return {
        "plan_name": plan_name,
        "price": _format_amount(amount, currency),
        "currency": currency,
        "interval": _interval_label(interval),
        "period_text": _period_text(interval, interval_count),
        "status": _subscription_status_label(str(subscription.get("status", "") or "")),
        "next_billing": _format_ts(current_period_end),
        "cancel_at_period_end": bool(subscription.get("cancel_at_period_end", False)),
        "auto_renew": not bool(subscription.get("cancel_at_period_end", False)),
        "payment_channel": _detect_payment_channel(subscription.get("default_payment_method") or {}),
    }


def _format_payment_method(payment_method_data: dict[str, Any]) -> dict[str, Any] | None:
    methods = payment_method_data.get("data", []) if isinstance(payment_method_data, dict) else []
    if not methods or not isinstance(methods, list):
        return None
    method = methods[0] if isinstance(methods[0], dict) else {}
    if not method:
        return None
    card = method.get("card") or {}
    exp_month = card.get("exp_month", "")
    exp_year = card.get("exp_year", "")
    expires = ""
    if exp_month and exp_year:
        try:
            expires = f"{int(exp_month):02d}/{exp_year}"
        except Exception:
            expires = ""
    return {
        "brand": str(card.get("brand", "") or "").upper(),
        "last4": str(card.get("last4", "") or ""),
        "expires": expires,
        "channel": _detect_payment_channel(method),
    }


def _format_invoice(invoice: dict[str, Any]) -> dict[str, Any]:
    effective_at = invoice.get("effective_at") or invoice.get("finalized_at") or 0
    try:
        amount = int(invoice.get("amount_due", 0) or 0)
    except Exception:
        amount = 0
    currency = str(invoice.get("currency", "") or "").upper()
    lines = (invoice.get("lines") or {}).get("data", [])
    description = "N/A"
    if lines and isinstance(lines, list):
        first_line = lines[0] if isinstance(lines[0], dict) else {}
        description = str(first_line.get("short_description") or first_line.get("description") or "N/A")

    card_info = ""
    payment_intent = invoice.get("payment_intent")
    if isinstance(payment_intent, dict):
        payment_method = payment_intent.get("payment_method")
        if isinstance(payment_method, dict):
            card = payment_method.get("card") or {}
            brand = str(card.get("brand", "") or "").upper()
            last4 = str(card.get("last4", "") or "")
            if brand or last4:
                card_info = f"{brand} *{last4}".strip()

    hosted_url = str(invoice.get("hosted_invoice_url", "") or "")
    public_hosted_url = hosted_url
    if hosted_url.startswith("/"):
        public_hosted_url = f"https://pay.openai.com{hosted_url}"

    slug = ""
    if hosted_url:
        match = re.match(r"/i/(.+)", urlparse(hosted_url).path)
        if match:
            slug = match.group(1).split("?", 1)[0]

    return {
        "id": str(invoice.get("id", "") or ""),
        "date": _format_ts(effective_at) or "未知",
        "amount": _format_amount(amount, currency),
        "amount_raw": amount,
        "currency": currency,
        "description": description,
        "status": _invoice_status_label(str(invoice.get("status", "") or "")),
        "card": card_info,
        "slug": slug,
        "hosted_invoice_url": public_hosted_url,
        "invoice_pdf_url": "",
        "receipt_pdf_url": "",
    }


def _resolve_invoice_file_url(slug: str, file_type: str, *, proxy: str = "") -> str:
    quoted_slug = quote(slug, safe="/_-")
    if file_type == "receipt":
        meta_url = f"{INVOICE_DATA_BASE}/invoice_receipt_file_url/{quoted_slug}?locale=zh-Hans"
    else:
        meta_url = f"{INVOICE_DATA_BASE}/invoice_pdf_file_url/{quoted_slug}?locale=zh-Hans"

    response = _request_get(
        meta_url,
        timeout=BILLING_FILE_TIMEOUT_SECONDS,
        proxy=proxy,
        allow_redirects=True,
    )
    if response.status_code >= 400:
        return ""
    data = _response_json(response)
    return str(data.get("file_url", "") or "").strip()


def _detect_payment_channel(payment_method: dict[str, Any]) -> dict[str, str]:
    if not payment_method or not isinstance(payment_method, dict):
        return {"type": "unknown", "label": "未知"}
    method_type = str(payment_method.get("type", "") or "")
    card = payment_method.get("card") or {}
    wallet = card.get("wallet") or {}
    wallet_type = str(wallet.get("type", "") or "") if isinstance(wallet, dict) else ""
    wallet_labels = {
        "google_pay": "Google Pay",
        "apple_pay": "Apple Pay",
        "samsung_pay": "Samsung Pay",
        "link": "Stripe Link",
    }
    if wallet_type in wallet_labels:
        return {"type": wallet_type, "label": wallet_labels[wallet_type]}
    if method_type == "card":
        brand = str(card.get("brand", "") or "").upper()
        last4 = str(card.get("last4", "") or "")
        return {"type": "card", "label": f"{brand} •{last4}".strip() if brand or last4 else "银行卡"}
    fallback = {
        "paypal": "PayPal",
        "alipay": "支付宝",
        "wechat_pay": "微信支付",
    }
    return {"type": method_type or "unknown", "label": fallback.get(method_type, method_type or "未知")}


def _infer_plan_type(value: str) -> str:
    lower_value = str(value or "").lower()
    if "enterprise" in lower_value:
        return "enterprise"
    if "team" in lower_value:
        return "team"
    if "pro" in lower_value:
        return "pro"
    if "plus" in lower_value:
        return "plus"
    if "free" in lower_value:
        return "free"
    return ""


def _format_amount(amount: int, currency: str) -> str:
    symbols = {
        "USD": "$",
        "CNY": "CNY ",
        "EUR": "EUR ",
        "GBP": "GBP ",
        "JPY": "JPY ",
        "PHP": "PHP ",
        "KRW": "KRW ",
        "TWD": "TWD ",
    }
    symbol = symbols.get(currency, f"{currency} " if currency else "")
    if amount:
        return f"{symbol}{amount / 100:.2f}"
    return f"{symbol}0.00".strip()


def _format_ts(value: Any) -> str:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        timestamp = 0
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def _interval_label(interval: str) -> str:
    return {"month": "月", "year": "年", "week": "周", "day": "日"}.get(interval, interval)


def _period_text(interval: str, count: int) -> str:
    label = _interval_label(interval)
    if not label:
        return ""
    if count > 1:
        return f"每 {count} {label}"
    return f"每 {label}"


def _subscription_status_label(status: str) -> str:
    labels = {
        "active": "使用中",
        "canceled": "已取消",
        "past_due": "逾期",
        "trialing": "试用中",
        "unpaid": "未支付",
        "incomplete": "未完成",
    }
    return labels.get(status, status)


def _invoice_status_label(status: str) -> str:
    labels = {
        "paid": "已支付",
        "open": "待支付",
        "void": "已作废",
        "draft": "草稿",
        "uncollectible": "无法收回",
    }
    return labels.get(status, status or "未知")
