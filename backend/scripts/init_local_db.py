import argparse
import getpass
import os
import re
import secrets
from pathlib import Path
from urllib.parse import quote

import pymysql

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
BACKEND_DIR = Path(__file__).resolve().parents[1]


def validate_identifier(value: str, label: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{label}只能包含字母、数字和下划线")
    return value


def build_database_url(*, host: str, port: int, database: str, user: str, password: str) -> str:
    encoded_user = quote(user, safe="")
    encoded_password = quote(password, safe="")
    return (
        f"mysql+pymysql://{encoded_user}:{encoded_password}@{host}:{port}/"
        f"{database}?charset=utf8mb4"
    )


def write_backend_env(
    path: Path,
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
) -> None:
    existing_secret = None
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("JWT_SECRET="):
                existing_secret = line.removeprefix("JWT_SECRET=").strip()
                break
    jwt_secret = existing_secret or secrets.token_urlsafe(48)
    database_url = build_database_url(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )
    path.write_text(
        "\n".join(
            [
                "ENVIRONMENT=development",
                f"DATABASE_URL={database_url}",
                f"JWT_SECRET={jwt_secret}",
                "FRONTEND_ORIGIN=http://localhost:5173",
                "SECURE_COOKIES=false",
                "",
            ]
        ),
        encoding="utf-8",
    )


def initialize_database(
    *,
    host: str,
    port: int,
    admin_user: str,
    admin_password: str,
    database: str,
    app_user: str,
    app_password: str,
) -> None:
    database = validate_identifier(database, "数据库名")
    app_user = validate_identifier(app_user, "开发账号")
    connection = pymysql.connect(
        host=host,
        port=port,
        user=admin_user,
        password=admin_password,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            escaped_user = connection.escape(app_user)
            escaped_password = connection.escape(app_password)
            for account_host in ("localhost", "127.0.0.1"):
                escaped_host = connection.escape(account_host)
                cursor.execute(
                    f"CREATE USER IF NOT EXISTS {escaped_user}@{escaped_host} "
                    f"IDENTIFIED BY {escaped_password}"
                )
                cursor.execute(
                    f"ALTER USER {escaped_user}@{escaped_host} IDENTIFIED BY {escaped_password}"
                )
                cursor.execute(
                    f"GRANT ALL PRIVILEGES ON `{database}`.* TO {escaped_user}@{escaped_host}"
                )
            cursor.execute("FLUSH PRIVILEGES")
    finally:
        connection.close()


def verify_application_connection(
    *, host: str, port: int, database: str, user: str, password: str
) -> None:
    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("本地数据库连接校验失败")
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化本机 MySQL 开发数据库")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--admin-user", default=os.getenv("MYSQL_ADMIN_USER", "root"))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "wins_order_book"))
    parser.add_argument("--app-user", default=os.getenv("MYSQL_APP_USER", "wins"))
    parser.add_argument("--app-password", default=os.getenv("MYSQL_APP_PASSWORD", "wins"))
    parser.add_argument("--skip-env", action="store_true", help="不生成 backend/.env")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    admin_password = os.getenv("MYSQL_ADMIN_PASSWORD")
    if admin_password is None:
        admin_password = getpass.getpass(f"请输入本机 MySQL 管理员 {args.admin_user} 的密码：")
    try:
        initialize_database(
            host=args.host,
            port=args.port,
            admin_user=args.admin_user,
            admin_password=admin_password,
            database=args.database,
            app_user=args.app_user,
            app_password=args.app_password,
        )
        verify_application_connection(
            host=args.host,
            port=args.port,
            database=args.database,
            user=args.app_user,
            password=args.app_password,
        )
    except pymysql.MySQLError as exc:
        raise SystemExit(
            "无法连接或初始化本机 MySQL。请确认 MySQL Server 已启动、端口正确，"
            f"且管理员账号有建库权限。\n原始错误：{exc}"
        ) from exc

    if not args.skip_env:
        write_backend_env(
            BACKEND_DIR / ".env",
            host=args.host,
            port=args.port,
            database=args.database,
            user=args.app_user,
            password=args.app_password,
        )
    print(f"本地数据库 {args.database} 初始化完成")
    if not args.skip_env:
        print(f"开发配置已写入 {BACKEND_DIR / '.env'}")
    print("下一步执行：.venv\\Scripts\\alembic upgrade head")


if __name__ == "__main__":
    main()