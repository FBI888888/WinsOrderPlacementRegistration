from datetime import date

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from app.modules.orders.models import Order, OrderStatus
from app.modules.partners.models import ContractorType, Source


def build_order_filters(
    *,
    tenant_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    order_status: OrderStatus | None = None,
    source_id: int | None = None,
    contractor_id: int | None = None,
    performer_id: int | None = None,
    contractor_type: ContractorType | None = None,
    profit_sign: str | None = None,
    keyword: str | None = None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [Order.tenant_id == tenant_id]
    if date_from:
        filters.append(Order.business_date >= date_from)
    if date_to:
        filters.append(Order.business_date <= date_to)
    if order_status:
        filters.append(Order.status == order_status.value)
    if source_id:
        filters.append(Order.source_id == source_id)
    if contractor_id:
        filters.append(Order.contractor_id == contractor_id)
    if performer_id:
        filters.append(Order.performer_id == performer_id)
    if contractor_type:
        filters.append(Order.contractor_type == contractor_type.value)
    if profit_sign == "positive":
        filters.append(Order.profit > 0)
    elif profit_sign == "negative":
        filters.append(Order.profit < 0)
    elif profit_sign == "zero":
        filters.append(Order.profit == 0)
    normalized_keyword = keyword.strip() if keyword else ""
    if normalized_keyword:
        pattern = f"%{normalized_keyword}%"
        filters.append(
            or_(
                Order.order_no.ilike(pattern),
                Source.name.ilike(pattern),
                Order.contractor_name_snapshot.ilike(pattern),
                Order.performer_name_snapshot.ilike(pattern),
            )
        )
    return filters