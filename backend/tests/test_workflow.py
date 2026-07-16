from datetime import date

from fastapi.testclient import TestClient

from tests.conftest import register


def create_business_data(client: TestClient, headers: dict[str, str]) -> tuple[int, int, int]:
    source = client.post(
        "/api/v1/partners/sources",
        headers=headers,
        json={
            "name": "渠道甲",
            "default_basis": "ORDER_AMOUNT",
            "default_discount": "0.9",
            "effective_date": date.today().isoformat(),
        },
    )
    assert source.status_code == 201, source.text
    leader = client.post(
        "/api/v1/partners/contractors",
        headers=headers,
        json={
            "name": "学生组长A",
            "contractor_type": "LEADER",
            "default_commission": "5",
            "effective_date": date.today().isoformat(),
        },
    )
    assert leader.status_code == 201, leader.text
    transaction = client.post(
        "/api/v1/funds/transactions",
        headers=headers,
        json={
            "business_date": date.today().isoformat(),
            "transaction_type": "ADVANCE_TOPUP",
            "amount": "1000",
            "contractor_id": leader.json()["id"],
        },
    )
    assert transaction.status_code == 201, transaction.text
    order = create_order(
        client,
        headers,
        source_id=source.json()["id"],
        leader_id=leader.json()["id"],
        status="SUCCESS",
    )
    return source.json()["id"], leader.json()["id"], order["id"]


def create_order(
    client: TestClient,
    headers: dict[str, str],
    *,
    source_id: int,
    leader_id: int,
    status: str = "DRAFT",
    **overrides,
) -> dict:
    payload = {
        "business_date": date.today().isoformat(),
        "source_id": source_id,
        "contractor_type": "LEADER",
        "contractor_id": leader_id,
        "student_name": "学生1",
        "order_amount": "100",
        "coupon_amount": "20",
        "actual_paid": "70",
        "status": status,
        **overrides,
    }
    response = client.post("/api/v1/orders", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_success_order_posts_ledger_and_profit(client: TestClient, auth_headers: dict[str, str]):
    _, leader_id, order_id = create_business_data(client, auth_headers)

    order = client.get(f"/api/v1/orders/{order_id}", headers=auth_headers).json()
    assert order["settlement_income"] == "90.00"
    assert order["cost"] == "75.00"
    assert order["profit"] == "15.00"

    balances = client.get("/api/v1/funds/balances", headers=auth_headers).json()
    advance = next(
        item
        for item in balances
        if item["account"] == "ADVANCE" and item["counterparty_id"] == leader_id
    )
    commission = next(
        item
        for item in balances
        if item["account"] == "COMMISSION_PAYABLE"
        and item["counterparty_id"] == leader_id
    )
    assert advance["balance"] == "930.00"
    assert commission["balance"] == "5.00"


def test_all_order_statuses_can_be_edited(client: TestClient, auth_headers: dict[str, str]):
    source_id, leader_id, success_id = create_business_data(client, auth_headers)
    order_ids = {
        "DRAFT": create_order(
            client, auth_headers, source_id=source_id, leader_id=leader_id
        )["id"],
        "DISPATCHED": create_order(
            client,
            auth_headers,
            source_id=source_id,
            leader_id=leader_id,
            status="DISPATCHED",
        )["id"],
        "SUCCESS": success_id,
    }
    cancelled = create_order(
        client, auth_headers, source_id=source_id, leader_id=leader_id
    )
    cancelled_response = client.post(
        f"/api/v1/orders/{cancelled['id']}/status",
        headers=auth_headers,
        json={"status": "CANCELLED", "reason": "不再处理"},
    )
    assert cancelled_response.status_code == 200, cancelled_response.text
    order_ids["CANCELLED"] = cancelled["id"]

    reversed_order = create_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        status="SUCCESS",
    )
    reversed_response = client.post(
        f"/api/v1/orders/{reversed_order['id']}/status",
        headers=auth_headers,
        json={"status": "REVERSED", "reason": "信息有误"},
    )
    assert reversed_response.status_code == 200, reversed_response.text
    order_ids["REVERSED"] = reversed_order["id"]

    for status, order_id in order_ids.items():
        updated = client.patch(
            f"/api/v1/orders/{order_id}",
            headers=auth_headers,
            json={"student_name": f"{status}-学生", "note": f"{status}-备注"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == status
        assert updated.json()["student_name"] == f"{status}-学生"
        assert updated.json()["note"] == f"{status}-备注"

    history = client.get(
        f"/api/v1/orders/{success_id}/history", headers=auth_headers
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["action"] == "order.updated"
    assert history.json()[0]["payload"]["note"] == "SUCCESS-备注"


def test_edit_success_order_rebuilds_ledger(client: TestClient, auth_headers: dict[str, str]):
    source_id, leader_id, order_id = create_business_data(client, auth_headers)
    original = client.get(f"/api/v1/orders/{order_id}", headers=auth_headers).json()

    updated = client.patch(
        f"/api/v1/orders/{order_id}",
        headers=auth_headers,
        json={"order_amount": "120", "coupon_amount": "20", "actual_paid": "60"},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["status"] == "SUCCESS"
    assert body["success_at"] == original["success_at"]
    assert body["settlement_income"] == "108.00"
    assert body["cost"] == "65.00"
    assert body["profit"] == "43.00"

    balances = client.get("/api/v1/funds/balances", headers=auth_headers).json()
    advance = next(
        item
        for item in balances
        if item["account"] == "ADVANCE" and item["counterparty_id"] == leader_id
    )
    commission = next(
        item
        for item in balances
        if item["account"] == "COMMISSION_PAYABLE"
        and item["counterparty_id"] == leader_id
    )
    receivable = next(
        item
        for item in balances
        if item["account"] == "SOURCE_RECEIVABLE"
        and item["counterparty_id"] == source_id
    )
    assert advance["balance"] == "940.00"
    assert commission["balance"] == "5.00"
    assert receivable["balance"] == "108.00"


def test_edit_order_can_clear_financial_overrides(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id, leader_id, _ = create_business_data(client, auth_headers)
    order = create_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        settlement_income_override="88",
        income_override_reason="临时结算约定",
        commission_override="8",
        commission_override_reason="临时佣金约定",
    )

    updated = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=auth_headers,
        json={
            "settlement_income_override": None,
            "income_override_reason": None,
            "commission_override": None,
            "commission_override_reason": None,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["settlement_income"] == "90.00"
    assert body["income_overridden"] is False
    assert body["income_override_reason"] is None
    assert body["commission"] == "5.00"
    assert body["commission_overridden"] is False
    assert body["commission_override_reason"] is None


def test_edit_order_allows_current_inactive_partners_only(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id, leader_id, order_id = create_business_data(client, auth_headers)
    inactive_source = client.post(
        "/api/v1/partners/sources",
        headers=auth_headers,
        json={
            "name": "停用渠道",
            "default_basis": "ORDER_AMOUNT",
            "default_discount": "0.8",
            "effective_date": date.today().isoformat(),
        },
    )
    assert inactive_source.status_code == 201, inactive_source.text
    for resource, resource_id in (("sources", source_id), ("contractors", leader_id)):
        response = client.patch(
            f"/api/v1/partners/{resource}/{resource_id}",
            headers=auth_headers,
            json={"is_active": False},
        )
        assert response.status_code == 200, response.text
    disable_target = client.patch(
        f"/api/v1/partners/sources/{inactive_source.json()['id']}",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert disable_target.status_code == 200, disable_target.text

    keep_current = client.patch(
        f"/api/v1/orders/{order_id}", headers=auth_headers, json={"note": "保留历史归属"}
    )
    assert keep_current.status_code == 200, keep_current.text

    switch_inactive = client.patch(
        f"/api/v1/orders/{order_id}",
        headers=auth_headers,
        json={"source_id": inactive_source.json()["id"]},
    )
    assert switch_inactive.status_code == 422


def test_tenant_cannot_read_another_tenants_order(
    client: TestClient, auth_headers: dict[str, str]
):
    _, _, order_id = create_business_data(client, auth_headers)
    other_token = register(client, email="other@example.com", tenant_name="其他账套")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    assert client.get(f"/api/v1/orders/{order_id}", headers=other_headers).status_code == 404
    assert client.get("/api/v1/orders", headers=other_headers).json()["total"] == 0


def test_confirmed_settlement_locks_order(client: TestClient, auth_headers: dict[str, str]):
    source_id, _, order_id = create_business_data(client, auth_headers)
    today = date.today().isoformat()
    settlement = client.post(
        "/api/v1/settlements",
        headers=auth_headers,
        json={
            "settlement_type": "SOURCE",
            "date_from": today,
            "date_to": today,
            "source_id": source_id,
        },
    )
    assert settlement.status_code == 201, settlement.text
    settlement_id = settlement.json()["id"]
    assert (
        client.post(f"/api/v1/settlements/{settlement_id}/confirm", headers=auth_headers).status_code
        == 200
    )

    locked_edit = client.patch(
        f"/api/v1/orders/{order_id}",
        headers=auth_headers,
        json={"note": "结算后修改"},
    )
    assert locked_edit.status_code == 409

    locked = client.post(
        f"/api/v1/orders/{order_id}/status",
        headers=auth_headers,
        json={"status": "REVERSED", "reason": "测试纠错"},
    )
    assert locked.status_code == 409

    assert (
        client.post(
            f"/api/v1/settlements/{settlement_id}/reverse",
            headers=auth_headers,
            json={"reason": "重新核对"},
        ).status_code
        == 200
    )
    reversed_order = client.post(
        f"/api/v1/orders/{order_id}/status",
        headers=auth_headers,
        json={"status": "REVERSED", "reason": "测试纠错"},
    )
    assert reversed_order.status_code == 200, reversed_order.text


def test_dashboard_and_csv_export(client: TestClient, auth_headers: dict[str, str]):
    create_business_data(client, auth_headers)
    today = date.today().isoformat()

    dashboard = client.get(
        "/api/v1/reports/dashboard",
        headers=auth_headers,
        params={"date_from": today, "date_to": today},
    )
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["success_count"] == 1
    assert dashboard.json()["profit"] == "15.00"

    exported = client.get(
        "/api/v1/reports/orders/export",
        headers=auth_headers,
        params=[
            ("export_format", "csv"),
            ("date_from", today),
            ("date_to", today),
            ("fields", "order_no"),
            ("fields", "profit"),
        ],
    )
    assert exported.status_code == 200, exported.text
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert "订单号,利润" in exported.content.decode("utf-8-sig")
    assert len(client.get("/api/v1/reports/export-logs", headers=auth_headers).json()) == 1