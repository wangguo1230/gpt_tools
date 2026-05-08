from __future__ import annotations

import json
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
