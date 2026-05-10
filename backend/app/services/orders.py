from __future__ import annotations

from datetime import datetime
import random
from typing import Any

from sqlalchemy import Select, func, or_, select

from ..database import session_scope
from ..models import ToolOrderLogModel, ToolOrderModel


MAX_PAGE_SIZE = 100
MAX_LOG_LIMIT = 100


def _task_no() -> str:
    prefix = datetime.utcnow().strftime("GT%Y%m%d%H%M%S")
    return f"{prefix}{random.randint(1000, 9999)}"


def create_order(
    *,
    plan_type: str,
    link_mode: str,
    billing_country: str,
    billing_currency: str,
    token_fingerprint: str,
    account_email: str,
    account_plan_type: str,
) -> int:
    with session_scope() as session:
        order = ToolOrderModel(
            task_no=_task_no(),
            plan_type=str(plan_type or "pro5x").strip().lower(),
            link_mode=str(link_mode or "short").strip().lower(),
            status="processing",
            billing_country=str(billing_country or "").strip().upper(),
            billing_currency=str(billing_currency or "").strip().upper(),
            token_fingerprint=str(token_fingerprint or "").strip(),
            account_email=str(account_email or "").strip(),
            account_plan_type=str(account_plan_type or "").strip().lower(),
        )
        session.add(order)
        session.flush()
        order_id = int(order.id)
    return order_id


def add_log(order_id: int, *, level: str, step: str, message: str, metadata: dict[str, Any] | None = None) -> None:
    with session_scope() as session:
        session.add(
            ToolOrderLogModel(
                order_id=int(order_id),
                level=str(level or "info").strip().lower() or "info",
                step=str(step or "log").strip()[:120],
                message=str(message or "").strip()[:2000],
                metadata_json=metadata or {},
            )
        )


def mark_success(order_id: int, payload: dict[str, Any]) -> ToolOrderModel:
    with session_scope() as session:
        order = session.get(ToolOrderModel, int(order_id))
        if order is None:
            raise ValueError("订单不存在")
        order.status = "generated"
        order.checkout_url = str(payload.get("checkout_url", "") or "")
        order.short_url = str(payload.get("checkout_short_url", "") or "")
        order.stripe_checkout_url = str(payload.get("stripe_checkout_url", "") or "")
        order.checkout_session_id = str(payload.get("checkout_session_id", "") or "")
        order.processor_entity = str(payload.get("processor_entity", "") or "")
        order.source = str(payload.get("source", "") or "")
        order.last_error_code = ""
        order.last_error_message = ""
        session.flush()
        session.refresh(order)
        session.expunge(order)
    return order


def mark_failed(order_id: int, *, error_code: str, error_message: str) -> ToolOrderModel:
    with session_scope() as session:
        order = session.get(ToolOrderModel, int(order_id))
        if order is None:
            raise ValueError("订单不存在")
        order.status = "failed"
        order.last_error_code = str(error_code or "generate_failed")[:120]
        order.last_error_message = str(error_message or "").strip()[:2000]
        session.flush()
        session.refresh(order)
        session.expunge(order)
    return order


def _apply_filters(stmt: Select, *, keyword: str, status: str, plan_type: str) -> Select:
    value = stmt
    status_value = str(status or "").strip().lower()
    if status_value:
        value = value.where(ToolOrderModel.status == status_value)
    plan_value = str(plan_type or "").strip().lower()
    if plan_value:
        value = value.where(ToolOrderModel.plan_type == plan_value)

    keyword_value = str(keyword or "").strip()
    if keyword_value:
        like_value = f"%{keyword_value}%"
        value = value.where(
            or_(
                ToolOrderModel.task_no.ilike(like_value),
                ToolOrderModel.account_email.ilike(like_value),
                ToolOrderModel.short_url.ilike(like_value),
                ToolOrderModel.checkout_url.ilike(like_value),
                ToolOrderModel.checkout_session_id.ilike(like_value),
            )
        )
    return value


def list_orders(*, limit: int = 20, offset: int = 0, keyword: str = "", status: str = "", plan_type: str = "") -> dict[str, Any]:
    selected_limit = max(1, min(int(limit or 20), MAX_PAGE_SIZE))
    selected_offset = max(0, int(offset or 0))

    with session_scope() as session:
        count_stmt = _apply_filters(
            select(func.count(ToolOrderModel.id)),
            keyword=keyword,
            status=status,
            plan_type=plan_type,
        )
        total = int(session.execute(count_stmt).scalar() or 0)
        items_stmt = _apply_filters(
            select(ToolOrderModel),
            keyword=keyword,
            status=status,
            plan_type=plan_type,
        ).order_by(ToolOrderModel.created_at.desc(), ToolOrderModel.id.desc())
        items = session.execute(items_stmt.offset(selected_offset).limit(selected_limit)).scalars().all()
        for item in items:
            session.expunge(item)

    return {
        "ok": True,
        "items": items,
        "total": total,
        "limit": selected_limit,
        "offset": selected_offset,
    }


def get_order_detail(order_id: int, *, log_limit: int = 30) -> dict[str, Any]:
    selected_order_id = int(order_id or 0)
    if selected_order_id <= 0:
        raise ValueError("订单 ID 不合法")
    selected_log_limit = max(1, min(int(log_limit or 30), MAX_LOG_LIMIT))

    with session_scope() as session:
        order = session.get(ToolOrderModel, selected_order_id)
        if order is None:
            raise ValueError("订单不存在")
        logs_stmt = (
            select(ToolOrderLogModel)
            .where(ToolOrderLogModel.order_id == order.id)
            .order_by(ToolOrderLogModel.created_at.desc(), ToolOrderLogModel.id.desc())
            .limit(selected_log_limit)
        )
        logs = session.execute(logs_stmt).scalars().all()
        session.expunge(order)
        for log in logs:
            session.expunge(log)

    return {"ok": True, "item": order, "logs": logs}
