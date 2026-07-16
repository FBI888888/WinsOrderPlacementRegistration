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
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "business_date": date.today().isoformat(),
            "source_id": source.json()["id"],
            "contractor_type": "LEADER",
            "contractor_id": leader.json()["id"],
            "student_name": "学生1",
            "order_amount": "100",
            "coupon_amount": "20",
            "actual_paid": "70",
            "status": "SUCCESS",
        },
    )
    assert order.status_code == 201, order.text
    return source.json()["id"], leader.json()["id"], order.json()["id"]


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