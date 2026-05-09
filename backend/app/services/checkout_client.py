from __future__ import annotations

import calendar
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

from curl_cffi import requests as curl_requests


CHATGPT_API_BASE = "https://chatgpt.com"
BACKEND_API_BASE = f"{CHATGPT_API_BASE}/backend-api"

ALLOWED_PLANS = {"pro", "plus", "pro5x", "pro20x"}
ALLOWED_LINK_MODES = {"short", "hosted", "long"}

STRIPE_KEYS: dict[str, str] = {
    "openai_llc": "pk_live_51HOrSwC6h1nxGoI3lTAgRjYVrz4dU3fVOabyCcKR3pbEJguCVAlqCxdxCUvoRh1XWwRacViovU3kLKvpkjh7IqkW00iXQsjo3n",
    "openai_ie": "pk_live_51Pj377KslHRdbaPgTJYjThzH3f5dt1N1vK7LUp0qh0yNSarhfZ6nfbG7FFlh8KLxVkvdMWN5o6Mc4Vda6NHaSnaV00C2Sbl8Zs",
}

PURCHASE_ORIGIN_CHANNEL_MAP: dict[str, str] = {
    "chatgpt_mobile_android": "google_play_like",
    "chatgpt_mobile_ios": "apple_iap_like",
    "chatgpt_web": "web_stripe_like",
    "chatgpt_not_purchased": "not_purchased",
}


def extract_access_token_from_input(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""

    def _find_token(payload: Any, depth: int = 0, allow_bare_string: bool = False) -> str:
        if depth > 6 or payload is None:
            return ""
        if isinstance(payload, str):
            return payload.strip() if allow_bare_string else ""
        if isinstance(payload, list):
            for item in payload:
                candidate = _find_token(item, depth + 1, allow_bare_string=True)
                if candidate:
                    return candidate
            return ""
        if not isinstance(payload, dict):
            return ""
        for key in ("access_token", "accessToken", "token"):
            candidate = str(payload.get(key, "") or "").strip()
            if candidate:
                return candidate
        for item in payload.values():
            candidate = _find_token(item, depth + 1, allow_bare_string=False)
            if candidate:
                return candidate
        return ""

    if value.startswith(("{", "[")):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"token JSON 解析失败: {exc}") from exc
        value = _find_token(payload, allow_bare_string=True)
        if not value:
            raise ValueError("token JSON 中未找到 access_token/accessToken/token 字段")

    lower_value = value.lower()
    if lower_value.startswith("authorization:"):
        value = value.split(":", 1)[1].strip()
        lower_value = value.lower()
    if lower_value.startswith("bearer "):
        value = value[7:].strip()
    return value


def extract_account_hint_from_input(raw_value: str) -> dict[str, str]:
    value = str(raw_value or "").strip()
    if not value.startswith(("{", "[")):
        return {"email": "", "plan_type": ""}
    try:
        payload = json.loads(value)
    except Exception:
        return {"email": "", "plan_type": ""}

    def _walk(obj: Any, key_names: set[str], depth: int = 0) -> str:
        if depth > 6 or obj is None:
            return ""
        if isinstance(obj, dict):
            for key, val in obj.items():
                if str(key).strip().lower() in key_names and isinstance(val, (str, int, float)):
                    text = str(val).strip()
                    if text:
                        return text
            for val in obj.values():
                found = _walk(val, key_names, depth + 1)
                if found:
                    return found
        if isinstance(obj, list):
            for item in obj:
                found = _walk(item, key_names, depth + 1)
                if found:
                    return found
        return ""

    email = _walk(payload, {"email", "user_email"})
    plan_type = _walk(payload, {"plantype", "plan_type", "chatgpt_plan_type"}).lower()
    return {"email": email, "plan_type": plan_type}


def _normalize_plan(value: Any) -> str:
    plan = str(value or "pro").strip().lower()
    if plan in {"pro20x", "pro5x"}:
        return "pro"
    if plan in {"pro", "plus"}:
        return plan
    return "pro"


def _normalize_link_mode(value: Any) -> str:
    mode = str(value or "short").strip().lower()
    return mode if mode in ALLOWED_LINK_MODES else "short"


def _build_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": CHATGPT_API_BASE,
        "Referer": f"{CHATGPT_API_BASE}/",
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


def _normalize_checkout_url(raw_url: Any) -> str:
    url = str(raw_url or "").strip()
    if not url or url.lower() in {"none", "null", "undefined", "nan"}:
        return ""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _normalize_openai_hosted_checkout_url(raw_url: Any) -> str:
    url = _normalize_checkout_url(raw_url)
    if not url:
        return ""
    parsed = urlparse(url)
    host = str(parsed.netloc or "").lower()
    if host == "checkout.stripe.com" and str(parsed.path or "").startswith("/c/pay/"):
        return urlunparse(("https", "pay.openai.com", parsed.path, "", parsed.query, parsed.fragment))
    return url


def _extract_checkout_currency_code(config_data: Any) -> str:
    if not isinstance(config_data, dict):
        return ""
    currency_cfg = config_data.get("currency_config", {})
    if isinstance(currency_cfg, dict):
        symbol_code = str(currency_cfg.get("symbol_code", "") or "").strip().upper()
        if len(symbol_code) == 3:
            return symbol_code

        for plan_name in ("business", "plus", "go", "pro", "free", "free_workspace"):
            plan_cfg = currency_cfg.get(plan_name)
            if not isinstance(plan_cfg, dict):
                continue
            for interval_cfg in plan_cfg.values():
                if not isinstance(interval_cfg, dict):
                    continue
                candidate = str(
                    interval_cfg.get("currency", "") or interval_cfg.get("symbol_code", "")
                ).strip().upper()
                if len(candidate) == 3:
                    return candidate

    fallback_currency = str(
        config_data.get("currency", "") or config_data.get("symbol_code", "")
    ).strip().upper()
    return fallback_currency if len(fallback_currency) == 3 else ""


def _normalize_billing_currency_for_country(country_code: str, currency_code: str) -> str:
    country = str(country_code or "").strip().upper()
    currency = str(currency_code or "").strip().upper()
    if country == "AR" and currency == "ARS":
        return "USD"
    return currency


def fetch_checkout_pricing_config(
    *,
    access_token: str,
    country: str,
    proxy: str = "",
) -> dict[str, Any]:
    country_code = str(country or "").strip().upper()
    if not country_code:
        return {"country": "", "currency": "", "raw_response": {}, "error": "country_missing"}
    try:
        resp = curl_requests.get(
            f"{BACKEND_API_BASE}/checkout_pricing_config/configs/{country_code}",
            headers=_build_headers(access_token),
            proxies=_build_proxies(proxy),
            impersonate="chrome",
            timeout=15,
        )
    except Exception as exc:
        return {
            "country": country_code,
            "currency": "",
            "raw_response": {},
            "error": f"checkout_pricing_config_exception:{str(exc)}",
        }

    if int(resp.status_code or 0) != 200:
        return {
            "country": country_code,
            "currency": "",
            "raw_response": {},
            "error": f"checkout_pricing_config_http_{resp.status_code}:{str(getattr(resp, 'text', '') or '')[:200]}",
        }

    try:
        data = resp.json()
    except Exception as exc:
        return {
            "country": country_code,
            "currency": "",
            "raw_response": {},
            "error": f"checkout_pricing_config_json_error:{str(exc)}",
        }

    resolved_country = str(data.get("country_code", "") or country_code).strip().upper() or country_code
    resolved_currency = _extract_checkout_currency_code(data)
    if not resolved_currency:
        return {
            "country": resolved_country,
            "currency": "",
            "raw_response": data,
            "error": "checkout_pricing_config_currency_missing",
        }

    return {
        "country": resolved_country,
        "currency": resolved_currency,
        "raw_response": data,
        "error": "",
    }


def resolve_checkout_billing_details(
    *,
    token_input: str = "",
    access_token: str = "",
    country: str = "",
    currency: str = "",
    proxy: str = "",
) -> dict[str, Any]:
    country_code = str(country or "").strip().upper()
    currency_code = str(currency or "").strip().upper()
    currency_code = _normalize_billing_currency_for_country(country_code, currency_code)

    if country_code and currency_code:
        return {
            "country": country_code,
            "currency": currency_code,
            "source": "manual",
            "raw_response": {},
            "error": "",
        }
    if (not country_code) and currency_code:
        return {
            "country": "",
            "currency": "",
            "source": "auto",
            "raw_response": {},
            "error": "billing_country_missing",
        }
    if not country_code:
        return {
            "country": "",
            "currency": "",
            "source": "auto",
            "raw_response": {},
            "error": "",
        }

    normalized_access_token = str(access_token or "").strip()
    if not normalized_access_token:
        normalized_access_token = extract_access_token_from_input(token_input)
    if not normalized_access_token:
        return {
            "country": "",
            "currency": "",
            "source": "checkout_pricing_config",
            "raw_response": {},
            "error": "access_token_missing_for_currency_resolve",
        }

    config_result = fetch_checkout_pricing_config(
        access_token=normalized_access_token,
        country=country_code,
        proxy=proxy,
    )
    if config_result.get("error"):
        return {
            "country": "",
            "currency": "",
            "source": "checkout_pricing_config",
            "raw_response": config_result.get("raw_response", {}),
            "error": str(config_result.get("error", "unknown_error"))[:280],
        }

    return {
        "country": str(config_result.get("country", "") or "").strip().upper(),
        "currency": _normalize_billing_currency_for_country(
            str(config_result.get("country", "") or "").strip().upper(),
            str(config_result.get("currency", "") or "").strip().upper(),
        ),
        "source": "checkout_pricing_config",
        "raw_response": config_result.get("raw_response", {}),
        "error": "",
    }


def _is_paid_plan(plan_type: str, has_active_subscription: bool) -> bool:
    normalized = str(plan_type or "").strip().lower()
    return bool(has_active_subscription or normalized not in {"", "free", "unknown", "none", "null"})


def _plan_priority(plan_type: str) -> int:
    normalized = str(plan_type or "").strip().lower()
    if normalized == "team":
        return 0
    if normalized == "pro":
        return 1
    if normalized == "plus":
        return 2
    return 9


def _normalize_billing_period(raw_value: Any) -> str:
    if isinstance(raw_value, str):
        return raw_value.strip().lower()
    if isinstance(raw_value, dict):
        interval = str(raw_value.get("interval", "") or "").strip().lower()
        interval_count = int(raw_value.get("interval_count", 1) or 1)
        if interval_count <= 1:
            return interval
        return f"{interval_count}_{interval}"
    return ""


def _period_to_delta(period_text: str) -> tuple[str, int] | None:
    value = str(period_text or "").strip().lower()
    if not value:
        return None

    month_map = {
        "month": 1,
        "monthly": 1,
        "1_month": 1,
        "quarter": 3,
        "quarterly": 3,
        "3_month": 3,
        "semiannual": 6,
        "semi-annually": 6,
        "biannual": 6,
        "6_month": 6,
        "year": 12,
        "yearly": 12,
        "annual": 12,
        "annually": 12,
        "12_month": 12,
    }
    if value in month_map:
        return ("months", month_map[value])
    if value in {"week", "weekly", "1_week"}:
        return ("days", 7)
    if value in {"day", "daily", "1_day"}:
        return ("days", 1)
    return None


def _parse_iso_datetime(raw_value: Any) -> datetime | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _subtract_months(source: datetime, months: int) -> datetime:
    month_index = source.month - 1 - months
    year = source.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source.day, calendar.monthrange(year, month)[1])
    return source.replace(year=year, month=month, day=day)


def _infer_subscription_start_at(
    *,
    billing_period: str,
    renews_at: str,
    expires_at: str,
) -> tuple[str, str]:
    delta_meta = _period_to_delta(billing_period)
    if not delta_meta:
        return ("", "")

    period_kind, period_value = delta_meta
    anchor = _parse_iso_datetime(renews_at)
    source = "renews_at"
    if anchor is None:
        anchor = _parse_iso_datetime(expires_at)
        source = "expires_at"
    if anchor is None:
        return ("", "")

    if period_kind == "months":
        started_at = _subtract_months(anchor, period_value)
    else:
        started_at = anchor - timedelta(days=period_value)
    return (started_at.isoformat(), f"inferred_from_{source}")


def _parse_json_object(resp: Any) -> dict[str, Any]:
    try:
        payload = resp.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_api_error_detail(payload: dict[str, Any], fallback: str = "") -> str:
    if not isinstance(payload, dict):
        return str(fallback or "").strip()
    error_obj = payload.get("error", {})
    if isinstance(error_obj, dict):
        code = str(error_obj.get("code", "") or "").strip()
        message = str(error_obj.get("message", "") or "").strip()
        if code and message:
            return f"{code}:{message}"
        if code:
            return code
        if message:
            return message
    message = str(payload.get("message", "") or "").strip()
    if message:
        return message
    return str(fallback or "").strip()


def _normalize_purchase_origin_platform(raw_value: Any) -> str:
    return str(raw_value or "").strip().lower()


def _guess_channel_from_origin(purchase_origin_platform: str) -> tuple[str, str]:
    normalized_origin = _normalize_purchase_origin_platform(purchase_origin_platform)
    if not normalized_origin:
        return ("unknown", "low")
    guessed = PURCHASE_ORIGIN_CHANNEL_MAP.get(normalized_origin, "unknown")
    if guessed == "unknown":
        return ("unknown", "low")
    return (guessed, "high")


def _finalize_channel_guess(
    *,
    purchase_origin_platform: str,
    channel_guess: str,
    channel_confidence: str,
    has_active_subscription: bool,
    is_paid: bool,
    customer_portal_url: str,
) -> tuple[str, str]:
    normalized_origin = _normalize_purchase_origin_platform(purchase_origin_platform)
    normalized_guess = str(channel_guess or "").strip().lower()
    normalized_confidence = str(channel_confidence or "").strip().lower()

    if normalized_origin and normalized_guess and normalized_guess != "unknown":
        return (
            normalized_guess,
            normalized_confidence or "high",
        )
    if has_active_subscription and str(customer_portal_url or "").strip():
        return ("web_stripe_like", "medium")
    if has_active_subscription:
        return ("active_unknown", "low")
    if is_paid:
        return ("paid_unknown", "low")
    return ("not_purchased", "low")


def _extract_account_candidates(raw: dict[str, Any]) -> list[dict[str, Any]]:
    accounts_map = raw.get("accounts", {})
    if not isinstance(accounts_map, dict) or not accounts_map:
        return []

    ordering = raw.get("account_ordering", [])
    ordered_ids: list[str] = []
    if isinstance(ordering, list):
        ordered_ids.extend([str(item or "").strip() for item in ordering if str(item or "").strip()])
    for aid in accounts_map.keys():
        aid_value = str(aid or "").strip()
        if aid_value and aid_value not in ordered_ids:
            ordered_ids.append(aid_value)

    candidates: list[dict[str, Any]] = []
    for aid in ordered_ids:
        item = accounts_map.get(aid, {})
        if not isinstance(item, dict):
            continue
        account = item.get("account", {}) if isinstance(item.get("account"), dict) else {}
        entitlement = item.get("entitlement", {}) if isinstance(item.get("entitlement"), dict) else {}
        last_active_subscription = (
            item.get("last_active_subscription", {}) if isinstance(item.get("last_active_subscription"), dict) else {}
        )
        plan_type = str(account.get("plan_type", "unknown") or "unknown").strip().lower()
        has_active = bool(entitlement.get("has_active_subscription", False))
        billing_period = _normalize_billing_period(entitlement.get("billing_period"))
        expires_at = str(entitlement.get("expires_at", "") or "").strip()
        renews_at = str(entitlement.get("renews_at", "") or "").strip()
        cancels_at = str(entitlement.get("cancels_at", "") or "").strip()
        purchase_origin_platform = _normalize_purchase_origin_platform(
            last_active_subscription.get("purchase_origin_platform")
        )
        channel_guess, channel_confidence = _guess_channel_from_origin(purchase_origin_platform)
        inferred_start_at, inferred_source = _infer_subscription_start_at(
            billing_period=billing_period,
            renews_at=renews_at,
            expires_at=expires_at,
        )
        candidates.append(
            {
                "account_id": aid,
                "email": str(account.get("email", "") or account.get("user_email", "") or "").strip(),
                "plan_type": plan_type,
                "has_active_subscription": has_active,
                "is_paid": _is_paid_plan(plan_type, has_active),
                "billing_period": billing_period,
                "expires_at": expires_at,
                "renews_at": renews_at,
                "cancels_at": cancels_at,
                "inferred_subscription_start_at": inferred_start_at,
                "inferred_subscription_start_source": inferred_source,
                "is_delinquent": bool(entitlement.get("is_delinquent", False)),
                "billing_currency": str(entitlement.get("billing_currency", "") or "").strip().upper(),
                "purchase_origin_platform": purchase_origin_platform,
                "channel_guess": channel_guess,
                "channel_confidence": channel_confidence,
            }
        )
    return candidates


def _pick_best_account_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {}
    ranked = list(candidates)
    ranked.sort(
        key=lambda item: (
            0 if bool(item.get("has_active_subscription", False)) else 1,
            0 if not bool(item.get("is_delinquent", False)) else 1,
            _plan_priority(str(item.get("plan_type", "") or "")),
            str(item.get("expires_at", "") or ""),
        )
    )
    return ranked[0]


def _fetch_me(access_token: str, proxy: str = "") -> dict[str, Any]:
    try:
        resp = curl_requests.get(
            f"{BACKEND_API_BASE}/me",
            headers=_build_headers(access_token),
            proxies=_build_proxies(proxy),
            impersonate="chrome",
            timeout=20,
        )
    except Exception as exc:
        return {"ok": False, "status_code": 0, "error": f"me_exception:{str(exc)}", "raw_response": {}}

    status_code = int(resp.status_code or 0)
    payload = _parse_json_object(resp)
    if status_code != 200:
        error_detail = _extract_api_error_detail(payload, str(getattr(resp, "text", "") or "")[:220])
        return {
            "ok": False,
            "status_code": status_code,
            "error": f"me_http_{status_code}:{error_detail}",
            "raw_response": payload,
        }
    return {"ok": True, "status_code": status_code, "error": "", "raw_response": payload}


def _fetch_accounts_check(access_token: str, proxy: str = "") -> dict[str, Any]:
    headers = _build_headers(access_token)
    headers["Accept"] = "*/*"
    headers["oai-client-version"] = "prod-eddc2f6ff65fee2d0d6439e379eab94fe3047f72"
    headers["oai-language"] = "zh-CN"
    try:
        resp = curl_requests.get(
            f"{BACKEND_API_BASE}/accounts/check/v4-2023-04-27",
            headers=headers,
            proxies=_build_proxies(proxy),
            impersonate="chrome",
            timeout=20,
        )
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "error": f"accounts_check_exception:{str(exc)}",
            "raw_response": {},
        }

    status_code = int(resp.status_code or 0)
    payload = _parse_json_object(resp)
    if status_code != 200:
        error_detail = _extract_api_error_detail(payload, str(getattr(resp, "text", "") or "")[:220])
        return {
            "ok": False,
            "status_code": status_code,
            "error": f"accounts_check_http_{status_code}:{error_detail}",
            "raw_response": payload,
        }
    return {"ok": True, "status_code": status_code, "error": "", "raw_response": payload}


def _fetch_customer_portal_url(access_token: str, proxy: str = "") -> dict[str, Any]:
    try:
        resp = curl_requests.get(
            f"{BACKEND_API_BASE}/payments/customer_portal",
            headers=_build_headers(access_token),
            proxies=_build_proxies(proxy),
            impersonate="chrome",
            timeout=20,
        )
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "url": "",
            "error": f"customer_portal_exception:{str(exc)}",
            "raw_response": {},
        }

    status_code = int(resp.status_code or 0)
    payload = _parse_json_object(resp)
    if status_code != 200:
        error_detail = _extract_api_error_detail(payload, str(getattr(resp, "text", "") or "")[:220])
        return {
            "ok": False,
            "status_code": status_code,
            "url": "",
            "error": f"customer_portal_http_{status_code}:{error_detail}",
            "raw_response": payload,
        }
    return {
        "ok": True,
        "status_code": status_code,
        "url": str((payload or {}).get("url", "") or "").strip(),
        "error": "",
        "raw_response": payload,
    }


def query_subscription_status_from_token(
    *,
    token_input: str,
    proxy: str = "",
) -> dict[str, Any]:
    access_token = extract_access_token_from_input(token_input)
    if not access_token:
        return {"ok": False, "error": "请填写 access_token", "source": "accounts_check_v4"}

    accounts_result = _fetch_accounts_check(access_token=access_token, proxy=proxy)
    if not accounts_result.get("ok"):
        return {
            "ok": False,
            "error": str(accounts_result.get("error") or "accounts_check_failed"),
            "source": "accounts_check_v4",
        }

    raw = accounts_result.get("raw_response", {}) if isinstance(accounts_result.get("raw_response"), dict) else {}
    candidates = _extract_account_candidates(raw)
    if not candidates:
        return {"ok": False, "error": "accounts_check_empty_accounts", "source": "accounts_check_v4"}
    selected = _pick_best_account_candidate(candidates)

    portal_result = _fetch_customer_portal_url(access_token=access_token, proxy=proxy)
    customer_portal_url = str(portal_result.get("url", "") or "").strip()
    channel_guess, channel_confidence = _finalize_channel_guess(
        purchase_origin_platform=str(selected.get("purchase_origin_platform", "") or ""),
        channel_guess=str(selected.get("channel_guess", "") or ""),
        channel_confidence=str(selected.get("channel_confidence", "") or ""),
        has_active_subscription=bool(selected.get("has_active_subscription", False)),
        is_paid=bool(selected.get("is_paid", False)),
        customer_portal_url=customer_portal_url,
    )

    return {
        "ok": True,
        "account_id": str(selected.get("account_id", "") or ""),
        "email": str(selected.get("email", "") or ""),
        "plan_type": str(selected.get("plan_type", "unknown") or "unknown"),
        "has_active_subscription": bool(selected.get("has_active_subscription", False)),
        "is_delinquent": bool(selected.get("is_delinquent", False)),
        "is_paid": bool(selected.get("is_paid", False)),
        "billing_period": str(selected.get("billing_period", "") or ""),
        "subscription_start_at": str(selected.get("inferred_subscription_start_at", "") or ""),
        "subscription_start_source": str(selected.get("inferred_subscription_start_source", "") or ""),
        "expires_at": str(selected.get("expires_at", "") or ""),
        "renews_at": str(selected.get("renews_at", "") or ""),
        "cancels_at": str(selected.get("cancels_at", "") or ""),
        "billing_currency": str(selected.get("billing_currency", "") or ""),
        "purchase_origin_platform": str(selected.get("purchase_origin_platform", "") or ""),
        "channel_guess": channel_guess,
        "channel_confidence": channel_confidence,
        "customer_portal_url": customer_portal_url,
        "accounts_total": len(candidates),
        "source": "accounts_check_v4",
        "error": str(portal_result.get("error", "") or ""),
    }


def query_me_and_subscription_from_token(
    *,
    token_input: str,
    proxy: str = "",
) -> dict[str, Any]:
    access_token = extract_access_token_from_input(token_input)
    if not access_token:
        return {"ok": False, "error": "请填写 access_token", "source": "me+accounts_check_v4"}

    me_result = _fetch_me(access_token=access_token, proxy=proxy)
    accounts_result = _fetch_accounts_check(access_token=access_token, proxy=proxy)
    portal_result = _fetch_customer_portal_url(access_token=access_token, proxy=proxy)

    me_payload = me_result.get("raw_response", {}) if isinstance(me_result.get("raw_response"), dict) else {}
    accounts_payload = (
        accounts_result.get("raw_response", {}) if isinstance(accounts_result.get("raw_response"), dict) else {}
    )

    candidates = _extract_account_candidates(accounts_payload)
    selected = _pick_best_account_candidate(candidates)
    portal_url = str(portal_result.get("url", "") or "").strip()
    channel_guess, channel_confidence = _finalize_channel_guess(
        purchase_origin_platform=str(selected.get("purchase_origin_platform", "") or ""),
        channel_guess=str(selected.get("channel_guess", "") or ""),
        channel_confidence=str(selected.get("channel_confidence", "") or ""),
        has_active_subscription=bool(selected.get("has_active_subscription", False)),
        is_paid=bool(selected.get("is_paid", False)),
        customer_portal_url=portal_url,
    )

    me_summary = {
        "id": str(me_payload.get("id", "") or ""),
        "email": str(me_payload.get("email", "") or ""),
        "name": str(me_payload.get("name", "") or ""),
        "default_model": str(me_payload.get("default_model", "") or ""),
        "created": str(me_payload.get("created", "") or ""),
        "phone_number": str(me_payload.get("phone_number", "") or ""),
        "chatgpt_plus_user": bool(me_payload.get("chatgpt_plus_user", False)),
        "groups_count": len(me_payload.get("groups", []) if isinstance(me_payload.get("groups"), list) else []),
        "organizations_count": len(
            me_payload.get("organizations", []) if isinstance(me_payload.get("organizations"), list) else []
        ),
    }

    accounts_summary = {
        "accounts_total": len(candidates),
        "selected_account_id": str(selected.get("account_id", "") or ""),
        "selected_email": str(selected.get("email", "") or ""),
        "selected_plan_type": str(selected.get("plan_type", "") or ""),
        "selected_has_active_subscription": bool(selected.get("has_active_subscription", False)),
        "selected_is_delinquent": bool(selected.get("is_delinquent", False)),
        "selected_is_paid": bool(selected.get("is_paid", False)),
        "selected_billing_period": str(selected.get("billing_period", "") or ""),
        "selected_subscription_start_at": str(selected.get("inferred_subscription_start_at", "") or ""),
        "selected_subscription_start_source": str(selected.get("inferred_subscription_start_source", "") or ""),
        "selected_expires_at": str(selected.get("expires_at", "") or ""),
        "selected_renews_at": str(selected.get("renews_at", "") or ""),
        "selected_cancels_at": str(selected.get("cancels_at", "") or ""),
        "selected_billing_currency": str(selected.get("billing_currency", "") or ""),
        "selected_purchase_origin_platform": str(selected.get("purchase_origin_platform", "") or ""),
        "selected_channel_guess": channel_guess,
        "selected_channel_confidence": channel_confidence,
    }

    portal_error = str(portal_result.get("error", "") or "")
    me_error = str(me_result.get("error", "") or "")
    accounts_error = str(accounts_result.get("error", "") or "")

    combined_errors = [item for item in [me_error, accounts_error, portal_error] if item]
    ok = bool(me_result.get("ok") or accounts_result.get("ok"))

    return {
        "ok": ok,
        "source": "me+accounts_check_v4",
        "error": "; ".join(combined_errors)[:800],
        "me": {
            "ok": bool(me_result.get("ok")),
            "status_code": int(me_result.get("status_code") or 0),
            "keys": list(me_payload.keys()),
            "summary": me_summary,
        },
        "accounts_check": {
            "ok": bool(accounts_result.get("ok")),
            "status_code": int(accounts_result.get("status_code") or 0),
            "keys": list(accounts_payload.keys()),
            "summary": accounts_summary,
        },
        "customer_portal": {
            "ok": bool(portal_result.get("ok")),
            "status_code": int(portal_result.get("status_code") or 0),
            "url": portal_url,
            "error": portal_error,
            "keys": list((portal_result.get("raw_response") or {}).keys())
            if isinstance(portal_result.get("raw_response"), dict)
            else [],
        },
    }


def create_checkout_session(
    *,
    access_token: str,
    plan: str,
    checkout_ui_mode: str,
    proxy: str = "",
    billing_country: str = "",
    billing_currency: str = "",
    processor_entity: str = "",
) -> dict[str, Any]:
    normalized_plan = _normalize_plan(plan)
    ui_mode = str(checkout_ui_mode or "custom").strip().lower()
    if ui_mode not in {"custom", "hosted"}:
        ui_mode = "custom"

    if normalized_plan == "plus":
        plan_name = "chatgptplusplan"
    else:
        plan_name = "chatgptpro" if ui_mode == "hosted" else "chatgptprolite"

    payload: dict[str, Any] = {
        "plan_name": plan_name,
        "checkout_ui_mode": ui_mode,
        "entry_point": "all_plans_pricing_modal",
    }
    country = str(billing_country or "").strip().upper()
    currency = str(billing_currency or "").strip().upper()
    if country and currency:
        payload["billing_details"] = {"country": country, "currency": currency}
    normalized_entity = str(processor_entity or "").strip()
    if normalized_entity:
        payload["processor_entity"] = normalized_entity

    try:
        resp = curl_requests.post(
            f"{BACKEND_API_BASE}/payments/checkout",
            headers=_build_headers(access_token),
            json=payload,
            proxies=_build_proxies(proxy),
            impersonate="chrome",
            timeout=20,
        )
    except Exception as exc:
        return {
            "checkout_session_id": "",
            "checkout_url": "",
            "processor_entity": "",
            "source": "standalone_checkout_api",
            "error": str(exc),
        }

    try:
        data = resp.json()
    except Exception:
        data = {}

    if int(resp.status_code or 0) != 200:
        return {
            "checkout_session_id": "",
            "checkout_url": "",
            "processor_entity": "",
            "source": "standalone_checkout_api",
            "error": f"HTTP {resp.status_code}: {str(getattr(resp, 'text', '') or '')[:220]}",
        }

    session_id = str(data.get("checkout_session_id", "") or data.get("session_id", "")).strip()
    entity = str(data.get("processor_entity", "openai_llc") or "openai_llc").strip() or "openai_llc"
    raw_checkout_url = data.get("checkout_url") or data.get("url")
    checkout_url = _normalize_checkout_url(raw_checkout_url)
    if not checkout_url and session_id:
        checkout_url = f"{CHATGPT_API_BASE}/checkout/{entity}/{session_id}"

    return {
        "checkout_session_id": session_id,
        "checkout_url": checkout_url,
        "processor_entity": entity,
        "checkout_plan_name": plan_name,
        "source": "standalone_checkout_api",
        "error": "",
    }


def update_checkout_session_plan(
    *,
    access_token: str,
    checkout_session_id: str,
    processor_entity: str,
    proxy: str = "",
) -> dict[str, Any]:
    session_id = str(checkout_session_id or "").strip()
    entity = str(processor_entity or "openai_llc").strip() or "openai_llc"
    if not session_id:
        return {"ok": False, "error": "checkout_session_id_missing"}
    payload = {
        "checkout_session_id": session_id,
        "processor_entity": entity,
        "plan_name": "chatgptpro",
        "price_interval": "month",
        "seat_quantity": 1,
    }
    headers = _build_headers(access_token)
    headers["Referer"] = f"{CHATGPT_API_BASE}/checkout/{entity}/{session_id}"

    try:
        resp = curl_requests.post(
            f"{BACKEND_API_BASE}/payments/checkout/update",
            headers=headers,
            json=payload,
            proxies=_build_proxies(proxy),
            impersonate="chrome",
            timeout=20,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        data = resp.json()
    except Exception:
        data = {}
    if int(resp.status_code or 0) == 200 and bool(data.get("success", False)):
        return {"ok": True, "error": ""}
    return {"ok": False, "error": f"HTTP {resp.status_code}: {str(getattr(resp, 'text', '') or '')[:220]}"}


def create_stripe_hosted_checkout_url(
    *,
    checkout_session_id: str,
    processor_entity: str,
    proxy: str = "",
) -> dict[str, Any]:
    session_id = str(checkout_session_id or "").strip()
    entity = str(processor_entity or "openai_llc").strip() or "openai_llc"
    if not session_id:
        return {"stripe_checkout_url": "", "error": "checkout_session_id_missing"}

    stripe_key = STRIPE_KEYS.get(entity) or STRIPE_KEYS["openai_llc"]
    fallback_url = f"https://checkout.stripe.com/c/pay/{session_id}"

    try:
        resp = curl_requests.post(
            f"https://api.stripe.com/v1/payment_pages/{session_id}/init",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://checkout.stripe.com",
                "Referer": fallback_url,
            },
            data={
                "key": stripe_key,
                "eid": "NA",
                "browser_locale": "en-US",
                "browser_timezone": "Asia/Shanghai",
                "redirect_type": "stripe_js",
            },
            proxies=_build_proxies(proxy),
            impersonate="chrome",
            timeout=15,
        )
    except Exception as exc:
        return {"stripe_checkout_url": fallback_url, "error": str(exc)}

    try:
        payload = resp.json()
    except Exception:
        payload = {}
    if int(resp.status_code or 0) != 200:
        return {
            "stripe_checkout_url": fallback_url,
            "error": f"stripe_init_http_{resp.status_code}:{str(getattr(resp, 'text', '') or '')[:220]}",
        }

    stripe_url = _normalize_checkout_url(payload.get("stripe_hosted_url") or payload.get("url") or fallback_url)
    return {"stripe_checkout_url": stripe_url or fallback_url, "error": ""}


def _pick_primary_url(link_mode: str, payment_methods: dict[str, str]) -> str:
    selected_mode = _normalize_link_mode(link_mode)
    if selected_mode == "short":
        return str(payment_methods.get("short", "") or "")
    if selected_mode == "hosted":
        return str(payment_methods.get("hosted", "") or payment_methods.get("stripe", "") or "")
    return str(payment_methods.get("stripe", "") or payment_methods.get("hosted", "") or "")


def create_checkout_from_token(
    *,
    token_input: str,
    plan: str,
    link_mode: str,
    proxy: str = "",
    billing_country: str = "",
    billing_currency: str = "",
) -> dict[str, Any]:
    access_token = extract_access_token_from_input(token_input)
    if not access_token:
        return {"ok": False, "error": "请填写 access_token", "source": "standalone_checkout_api"}

    selected_plan = _normalize_plan(plan)
    selected_mode = _normalize_link_mode(link_mode)

    billing_resolved = resolve_checkout_billing_details(
        access_token=access_token,
        country=str(billing_country or ""),
        currency=str(billing_currency or ""),
        proxy=proxy,
    )
    if billing_resolved.get("error"):
        return {
            "ok": False,
            "error": str(billing_resolved.get("error") or "billing_resolve_failed"),
            "source": "checkout_pricing_config",
            "selected_plan": selected_plan,
            "link_mode": selected_mode,
        }
    country = str(billing_resolved.get("country", "") or "").strip().upper()
    currency = str(billing_resolved.get("currency", "") or "").strip().upper()
    billing_source = str(billing_resolved.get("source", "") or "")

    session_result = create_checkout_session(
        access_token=access_token,
        plan=selected_plan,
        checkout_ui_mode="custom",
        proxy=proxy,
        billing_country=country,
        billing_currency=currency,
    )
    if session_result.get("error"):
        return {
            "ok": False,
            "error": str(session_result.get("error") or "checkout_create_failed"),
            "source": str(session_result.get("source", "standalone_checkout_api") or "standalone_checkout_api"),
            "selected_plan": selected_plan,
            "link_mode": selected_mode,
        }

    session_id = str(session_result.get("checkout_session_id", "") or "").strip()
    processor_entity = str(session_result.get("processor_entity", "openai_llc") or "openai_llc").strip() or "openai_llc"
    short_url = str(session_result.get("checkout_url", "") or "").strip()
    if (not short_url) and session_id:
        short_url = f"{CHATGPT_API_BASE}/checkout/{processor_entity}/{session_id}"
    if not short_url:
        return {
            "ok": False,
            "error": "short_url_missing",
            "source": str(session_result.get("source", "standalone_checkout_api") or "standalone_checkout_api"),
            "selected_plan": selected_plan,
            "link_mode": selected_mode,
        }
    if not session_id:
        return {
            "ok": False,
            "error": "checkout_session_id_missing",
            "source": str(session_result.get("source", "standalone_checkout_api") or "standalone_checkout_api"),
            "selected_plan": selected_plan,
            "link_mode": selected_mode,
        }

    if selected_plan == "pro":
        update_result = update_checkout_session_plan(
            access_token=access_token,
            checkout_session_id=session_id,
            processor_entity=processor_entity,
            proxy=proxy,
        )
        if not update_result.get("ok"):
            return {
                "ok": False,
                "error": f"checkout_update_failed:{str(update_result.get('error', 'unknown'))[:220]}",
                "source": str(session_result.get("source", "standalone_checkout_api") or "standalone_checkout_api"),
                "selected_plan": selected_plan,
                "link_mode": selected_mode,
            }

    stripe_result = create_stripe_hosted_checkout_url(
        checkout_session_id=session_id,
        processor_entity=processor_entity,
        proxy=proxy,
    )
    stripe_url = str(stripe_result.get("stripe_checkout_url", "") or "").strip()
    if not stripe_url:
        return {
            "ok": False,
            "error": f"stripe_long_url_missing:{str(stripe_result.get('error', 'missing'))[:220]}",
            "source": str(session_result.get("source", "standalone_checkout_api") or "standalone_checkout_api"),
            "selected_plan": selected_plan,
            "link_mode": selected_mode,
        }

    hosted_url = _normalize_openai_hosted_checkout_url(stripe_url)
    payment_methods = {
        "short": short_url,
        "hosted": hosted_url,
        "stripe": stripe_url,
    }
    primary_url = _pick_primary_url(selected_mode, payment_methods)
    if not primary_url:
        return {
            "ok": False,
            "error": "payment_url_missing",
            "source": str(session_result.get("source", "standalone_checkout_api") or "standalone_checkout_api"),
            "selected_plan": selected_plan,
            "link_mode": selected_mode,
        }

    return {
        "ok": True,
        "checkout_url": primary_url,
        "checkout_short_url": short_url,
        "stripe_checkout_url": stripe_url,
        "payment_methods": payment_methods,
        "link_mode": selected_mode,
        "checkout_session_id": session_id,
        "processor_entity": processor_entity,
        "selected_plan": selected_plan,
        "source": str(session_result.get("source", "standalone_checkout_api") or "standalone_checkout_api"),
        "billing_country": country,
        "billing_currency": currency,
        "billing_source": billing_source,
        "error": str(stripe_result.get("error", "") or ""),
    }
