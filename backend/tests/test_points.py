from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.modules.orders.models import Order
from app.modules.points.models import PointEntry
from tests.conftest import TestingSession


def create_source(client: TestClient, headers: dict[str, str], name: str = "积分渠道") -> int:
    response = client.post(
        "/api/v1/partners/sources",
        headers=headers,
        json={
            "name": name,
            "default_basis": "ORDER_AMOUNT",
            "default_discount": "0.9",
            "effective_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_leader(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post(
        "/api/v1/partners/contractors",
        headers=headers,
        json={
            "name": name,
            "contractor_type": "LEADER",
            "default_commission": "5",
            "effective_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_student_order(
    client: TestClient,
    headers: dict[str, str],
    *,
    source_id: int,
    leader_id: int,
    student_name: str,
    order_amount: str = "300",
    actual_paid: str | None = None,
    status: str = "SUCCESS",
    save_performer: bool = True,
) -> dict:
    response = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "business_date": date.today().isoformat(),
            "source_id": source_id,
            "contractor_type": "LEADER",
            "contractor_id": leader_id,
            "performer_name": student_name,
            "save_performer": save_performer,
            "order_amount": order_amount,
            "coupon_amount": "0",
            "actual_paid": actual_paid or order_amount,
            "status": status,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_success_order_earns_points_and_coupon_can_be_redeemed(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id = create_source(client, auth_headers)
    leader_id = create_leader(client, auth_headers, "积分头子")
    order = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        student_name="学生甲",
    )

    assert order["point_balance"] == "600.00"
    assert order["available_coupons"] == 1
    performer_id = order["performer_id"]

    redeemed = client.post(
        f"/api/v1/points/performers/{performer_id}/redeem",
        headers=auth_headers,
        json={},
    )
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["balance"] == "0.00"
    assert redeemed.json()["entry"]["amount"] == "-600.00"
    assert redeemed.json()["entry"]["coupon_value"] == "30.00"

    insufficient = client.post(
        f"/api/v1/points/performers/{performer_id}/redeem",
        headers=auth_headers,
        json={},
    )
    assert insufficient.status_code == 409


def test_points_are_calculated_from_actual_paid_amount(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id = create_source(client, auth_headers)
    leader_id = create_leader(client, auth_headers, "实付积分头子")
    order = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        student_name="实付积分学生",
        order_amount="300",
        actual_paid="250",
    )

    assert order["order_amount"] == "300.00"
    assert order["actual_paid"] == "250.00"
    assert order["point_balance"] == "500.00"
    assert order["available_coupons"] == 0


def test_success_order_edit_rebuilds_points_and_reversal_removes_them(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id = create_source(client, auth_headers)
    leader_id = create_leader(client, auth_headers, "重算头子")
    order = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        student_name="学生乙",
        order_amount="100",
    )
    assert order["point_balance"] == "200.00"

    updated = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=auth_headers,
        json={"order_amount": "150", "actual_paid": "120"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["point_balance"] == "240.00"

    entries = client.get(
        "/api/v1/points/entries",
        headers=auth_headers,
        params={"performer_id": order["performer_id"]},
    )
    assert entries.status_code == 200
    assert sum(float(item["amount"]) for item in entries.json()) == 240

    reversed_order = client.post(
        f"/api/v1/orders/{order['id']}/status",
        headers=auth_headers,
        json={"status": "REVERSED", "reason": "订单无效"},
    )
    assert reversed_order.status_code == 200, reversed_order.text
    assert reversed_order.json()["point_balance"] == "0.00"


def test_same_student_name_is_isolated_by_leader(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id = create_source(client, auth_headers)
    first_leader = create_leader(client, auth_headers, "头子一")
    second_leader = create_leader(client, auth_headers, "头子二")

    first = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=first_leader,
        student_name="同名学生",
        order_amount="50",
    )
    second = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=second_leader,
        student_name="同名学生",
        order_amount="80",
    )

    assert first["performer_id"] != second["performer_id"]
    accounts = client.get("/api/v1/points/accounts", headers=auth_headers).json()
    balances = {
        (item["contractor_id"], item["performer_name"]): item["balance"]
        for item in accounts
    }
    assert balances[(first_leader, "同名学生")] == "100.00"
    assert balances[(second_leader, "同名学生")] == "160.00"


def test_unlisted_manual_student_is_reused_and_can_be_promoted(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id = create_source(client, auth_headers)
    leader_id = create_leader(client, auth_headers, "隐藏名单头子")
    hidden_order = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        student_name="临时学生",
        order_amount="10",
        status="DRAFT",
        save_performer=False,
    )

    listed = client.get(
        "/api/v1/partners/performers",
        headers=auth_headers,
        params={"contractor_id": leader_id, "listed_only": True},
    ).json()
    assert listed == []

    promoted_order = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        student_name=" 临时学生 ",
        order_amount="20",
        status="DRAFT",
        save_performer=True,
    )
    assert promoted_order["performer_id"] == hidden_order["performer_id"]

    listed = client.get(
        "/api/v1/partners/performers",
        headers=auth_headers,
        params={"contractor_id": leader_id, "listed_only": True},
    ).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "临时学生"


def test_student_performer_cannot_be_assigned_to_another_leader(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id = create_source(client, auth_headers)
    first_leader = create_leader(client, auth_headers, "归属头子一")
    second_leader = create_leader(client, auth_headers, "归属头子二")
    first_order = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=first_leader,
        student_name="归属学生",
        status="DRAFT",
    )

    invalid = client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={
            "business_date": date.today().isoformat(),
            "source_id": source_id,
            "contractor_type": "LEADER",
            "contractor_id": second_leader,
            "performer_id": first_order["performer_id"],
            "order_amount": "100",
            "coupon_amount": "0",
            "actual_paid": "100",
            "status": "DRAFT",
        },
    )
    assert invalid.status_code == 422


def test_historical_success_without_student_is_pending_until_repaired(
    client: TestClient, auth_headers: dict[str, str]
):
    source_id = create_source(client, auth_headers)
    leader_id = create_leader(client, auth_headers, "待补头子")
    order = create_student_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        student_name="待补学生",
        order_amount="100",
    )

    with TestingSession() as db:
        db.execute(delete(PointEntry).where(PointEntry.order_id == order["id"]))
        stored = db.get(Order, order["id"])
        assert stored is not None
        stored.performer_id = None
        stored.performer_name_snapshot = None
        stored.student_name = None
        stored.point_revision = 0
        db.commit()

    pending = client.get("/api/v1/points/pending-orders", headers=auth_headers)
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()] == [order["id"]]

    repaired = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=auth_headers,
        json={"performer_name": "补录学生", "save_performer": True},
    )
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["performer_name"] == "补录学生"
    assert repaired.json()["point_balance"] == "200.00"
    assert client.get("/api/v1/points/pending-orders", headers=auth_headers).json() == []