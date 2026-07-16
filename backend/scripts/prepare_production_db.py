import argparse
import os
import secrets
from dataclasses import dataclass

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import Connection, text

from app.core.security import hash_password, verify_password
from app.db.session import engine

BUSINESS_TABLES = (
    "settlement_items",
    "ledger_entries",
    "settlements",
    "orders",
    "contractor_rates",
    "source_rates",
    "contractors",
    "sources",
    "export_logs",
    "export_templates",
    "refresh_sessions",
    "audit_logs",
)
IDENTITY_TABLES = ("users", "tenants", "members")
EMAIL_ADAPTER = TypeAdapter(EmailStr)


@dataclass(frozen=True)
class OwnerAccount:
    user_id: int
    email: str
    name: str
    tenant_id: int
    tenant_name: str
    member_id: int
    role: str
    user_active: bool
    tenant_active: bool
    member_active: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="清空演示业务数据，并将唯一 OWNER 原位转换为正式管理员",
    )
    parser.add_argument("--admin-email", help="正式管理员邮箱")
    parser.add_argument("--admin-name", help="正式管理员显示名称")
    parser.add_argument("--tenant-name", help="正式账套名称")
    parser.add_argument("--password-env", help="从指定环境变量读取管理员密码；不填写则生成随机密码")
    parser.add_argument("--apply", action="store_true", help="正式执行；默认仅预检")
    parser.add_argument("--confirm", help="正式执行时必须填写脚本提示的确认短语")
    return parser.parse_args()


def load_owner(connection: Connection) -> OwnerAccount:
    rows = connection.execute(
        text(
            """
            SELECT
                u.id AS user_id,
                u.email,
                u.name,
                u.is_active AS user_active,
                t.id AS tenant_id,
                t.name AS tenant_name,
                t.is_active AS tenant_active,
                m.id AS member_id,
                m.role,
                m.is_active AS member_active
            FROM users AS u
            JOIN members AS m ON m.user_id = u.id
            JOIN tenants AS t ON t.id = m.tenant_id
            ORDER BY u.id, m.id
            """
        )
    ).mappings().all()
    if len(rows) != 1:
        raise RuntimeError(f"安全检查失败：预期仅 1 条用户/成员/账套关系，实际为 {len(rows)} 条")

    row = rows[0]
    counts = table_counts(connection, IDENTITY_TABLES)
    if counts != {"users": 1, "tenants": 1, "members": 1}:
        raise RuntimeError(f"安全检查失败：身份表数量不符合唯一管理员前提：{counts}")
    if row["role"] != "OWNER":
        raise RuntimeError(f"安全检查失败：唯一成员角色不是 OWNER，而是 {row['role']}")

    return OwnerAccount(
        user_id=row["user_id"],
        email=row["email"],
        name=row["name"],
        tenant_id=row["tenant_id"],
        tenant_name=row["tenant_name"],
        member_id=row["member_id"],
        role=row["role"],
        user_active=bool(row["user_active"]),
        tenant_active=bool(row["tenant_active"]),
        member_active=bool(row["member_active"]),
    )


def table_counts(connection: Connection, tables: tuple[str, ...]) -> dict[str, int]:
    return {
        table: connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()
        for table in tables
    }


def validate_identity(*, email: str | None, admin_name: str | None, tenant_name: str | None) -> tuple[str, str, str]:
    if not email or not admin_name or not tenant_name:
        raise ValueError("正式执行必须同时提供 --admin-email、--admin-name 和 --tenant-name")
    normalized_email = str(EMAIL_ADAPTER.validate_python(email)).lower()
    normalized_name = admin_name.strip()
    normalized_tenant_name = tenant_name.strip()
    if not 2 <= len(normalized_name) <= 80:
        raise ValueError("管理员名称长度必须为 2 到 80 个字符")
    if not 2 <= len(normalized_tenant_name) <= 100:
        raise ValueError("账套名称长度必须为 2 到 100 个字符")
    return normalized_email, normalized_name, normalized_tenant_name


def print_preflight(owner: OwnerAccount, counts: dict[str, int]) -> None:
    url = engine.url
    print("目标数据库")
    print(f"  驱动: {url.drivername}")
    print(f"  地址: {url.host}:{url.port or 3306}")
    print(f"  数据库: {url.database}")
    print("当前唯一 OWNER")
    print(f"  账号: {owner.email}")
    print(f"  姓名: {owner.name}")
    print(f"  账套: {owner.tenant_name}")
    print("待清理数据")
    for table, count in counts.items():
        print(f"  {table}: {count}")


def clear_business_data(connection: Connection) -> None:
    connection.execute(text("UPDATE ledger_entries SET reversed_entry_id = NULL WHERE reversed_entry_id IS NOT NULL"))
    for table in BUSINESS_TABLES:
        connection.execute(text(f"DELETE FROM `{table}`"))


def convert_owner(
    connection: Connection,
    *,
    owner: OwnerAccount,
    email: str,
    admin_name: str,
    tenant_name: str,
    password: str,
) -> None:
    connection.execute(
        text(
            """
            UPDATE users
            SET email = :email, name = :name, password_hash = :password_hash, is_active = TRUE
            WHERE id = :user_id
            """
        ),
        {
            "email": email,
            "name": admin_name,
            "password_hash": hash_password(password),
            "user_id": owner.user_id,
        },
    )
    connection.execute(
        text("UPDATE tenants SET name = :name, is_active = TRUE WHERE id = :tenant_id"),
        {"name": tenant_name, "tenant_id": owner.tenant_id},
    )
    connection.execute(
        text("UPDATE members SET role = 'OWNER', is_active = TRUE WHERE id = :member_id"),
        {"member_id": owner.member_id},
    )
    connection.execute(text("DELETE FROM members WHERE id <> :member_id"), {"member_id": owner.member_id})
    connection.execute(text("DELETE FROM users WHERE id <> :user_id"), {"user_id": owner.user_id})
    connection.execute(text("DELETE FROM tenants WHERE id <> :tenant_id"), {"tenant_id": owner.tenant_id})


def verify_result(connection: Connection, *, email: str, password: str) -> None:
    owner = load_owner(connection)
    if owner.email != email or not (owner.user_active and owner.tenant_active and owner.member_active):
        raise RuntimeError("清理后管理员身份校验失败")

    password_hash = connection.execute(
        text("SELECT password_hash FROM users WHERE id = :user_id"),
        {"user_id": owner.user_id},
    ).scalar_one()
    if not verify_password(password, password_hash):
        raise RuntimeError("清理后管理员密码校验失败")

    remaining = table_counts(connection, BUSINESS_TABLES)
    non_empty = {table: count for table, count in remaining.items() if count != 0}
    if non_empty:
        raise RuntimeError(f"清理后仍存在业务数据：{non_empty}")


def main() -> None:
    args = parse_args()
    database = engine.url.database or "unknown"
    confirmation = f"CLEAR {database}"

    with engine.connect() as connection:
        owner = load_owner(connection)
        counts = table_counts(connection, BUSINESS_TABLES)
        print_preflight(owner, counts)

    if not args.apply:
        print("当前为只读预检，未修改任何数据。")
        print(f"正式执行需追加 --apply --confirm \"{confirmation}\" 及正式管理员信息。")
        return

    try:
        email, admin_name, tenant_name = validate_identity(
            email=args.admin_email,
            admin_name=args.admin_name,
            tenant_name=args.tenant_name,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.confirm != confirmation:
        raise SystemExit(f"确认短语不匹配；应为：{confirmation}")

    password_from_environment = bool(args.password_env)
    password = os.getenv(args.password_env) if args.password_env else secrets.token_urlsafe(18)
    if password is None:
        raise SystemExit(f"环境变量 {args.password_env} 未设置")
    if not 8 <= len(password) <= 128:
        raise SystemExit("管理员密码长度必须为 8 到 128 个字符")

    with engine.begin() as connection:
        owner = load_owner(connection)
        clear_business_data(connection)
        convert_owner(
            connection,
            owner=owner,
            email=email,
            admin_name=admin_name,
            tenant_name=tenant_name,
            password=password,
        )
        verify_result(connection, email=email, password=password)

    print("远程演示数据已清空，正式管理员已更新。")
    print(f"管理员邮箱: {email}")
    if password_from_environment:
        print("管理员密码已按指定环境变量设置。")
    else:
        print(f"一次性初始密码: {password}")
        print("请立即登录并妥善保存密码；当前系统尚未提供修改密码页面。")


if __name__ == "__main__":
    main()